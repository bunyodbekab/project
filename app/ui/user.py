import json
import math
import os
import threading
import time
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler

from PyQt6.QtCore import QObject, QTimer, QUrl, Qt, pyqtSignal, pyqtSlot, QRectF
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QStackedWidget, QVBoxLayout, QWidget, QGraphicsView, QGraphicsScene, QFrame
from PyQt6.QtGui import QTransform

from app.gpio_controller import GPIOController
from app.settings import BASE_DIR, BLINK_WARN, ICONS_DIR, INPUT_GPIO_TO_SERVICE, LOW_BALANCE, DEBUG, DEFAULT_CONFIG
from app.storage import load_config, save_config, add_session


class WebBridge(QObject):
    stateChanged = pyqtSignal(str)

    def __init__(self, ui):
        super().__init__()
        self.ui = ui

    @pyqtSlot(result=str)
    def getState(self):
        return self.ui._state_json()

    @pyqtSlot(result=str)
    def getSettings(self):
        return json.dumps(self.ui._settings_payload(), ensure_ascii=False)

    @pyqtSlot()
    def addMoney(self):
        self.ui.add_money(5000)

    @pyqtSlot(str)
    def selectService(self, service_name):
        self.ui.button_clicked(service_name)

    @pyqtSlot()
    def stopPressed(self):
        self.ui._on_stop_pressed("web")

    @pyqtSlot()
    def stopReleased(self):
        self.ui._on_stop_released("web")

    @pyqtSlot("QVariant")
    def updateFrontSettings(self, settings):
        self.ui.update_front_settings(settings)

    @pyqtSlot(result=str)
    def resetConfigToDefaults(self):
        self.ui.reset_config_to_defaults()
        return json.dumps(self.ui._settings_payload(), ensure_ascii=False)


class RotatedContainer(QGraphicsView):
    def __init__(self, inner_widget, angle_deg, parent=None, fallback_size=None):
        super().__init__(parent)
        self._inner = inner_widget
        self._angle = angle_deg
        self._fallback_size = fallback_size or (0, 0)

        self.setStyleSheet("background: transparent; border: none;")
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._scene = QGraphicsScene(self)
        self._proxy = self._scene.addWidget(inner_widget)
        self._proxy.setTransform(QTransform().rotate(self._angle))
        self._scene.addItem(self._proxy)
        self.setScene(self._scene)

        # keep scaling stable; rotate only
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

        self._update_scene_rect(force_fallback=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scene_rect()

    def _update_scene_rect(self, force_fallback=False):
        rect = self._proxy.boundingRect()
        if force_fallback or rect.width() <= 1 or rect.height() <= 1:
            fw, fh = self._fallback_size
            if fw and fh:
                rect = QRectF(0, 0, fw, fh)
            else:
                vp = self.viewport().rect()
                rect = QRectF(0, 0, max(1, vp.width()), max(1, vp.height()))
        self._scene.setSceneRect(rect)
        self.centerOn(rect.center())


class MoykaUI(QWidget):
    def __init__(self, width, height):
        super().__init__()

        self.w = width
        self.h = height
        self.setFixedSize(width, height)

        self.cfg = load_config()
        relay_map = {name: data.get("gpio_out", data.get("relay_bit", idx)) for idx, (name, data) in enumerate(self.cfg["services"].items())}
        self.gpio = GPIOController(relay_map)

        self.front_settings = None
        self.front_services = []
        self.front_key_to_hw = {}
        self.hw_to_front = {}
        self.price_per_sec = {}
        self.pause_free_default = 0
        self.pause_paid_rate = 1
        self.pause_free_left = 0
        self.pause_stage = "off"

        self.balance = 0
        self.remaining_sec = 0
        self.active_service = None
        self.active_front_key = None
        self.is_running = False
        self.pause_mode = False
        self.show_timer_mode = False
        self.session_earned = 0
        self._bonus_awarded = False

        self.blink_state = False
        self._low_balance_flash = False

        self._pause_hold_count = 0
        self._pause_hold_timer = QTimer(self)
        self._pause_hold_timer.setSingleShot(True)
        self._pause_hold_timer.setInterval(2000)  # long-press threshold (ms)
        self._pause_hold_timer.timeout.connect(self._pause_hold_tick)
        self._stop_hold_source = None
        self._stop_hold_started = None
        self._pending_pin_modal = False
        self.web_ready = False

        self.service_timer = QTimer(self)
        self.service_timer.setInterval(1000)
        self.service_timer.timeout.connect(self._tick)

        self.blink_timer = QTimer(self)
        self.blink_timer.setInterval(400)
        self.blink_timer.timeout.connect(self._blink)

        self.input_timer = QTimer(self)
        self.input_timer.setInterval(100)
        self.input_timer.timeout.connect(self._poll_inputs)
        self._prev_input = {line: 0 for line in INPUT_GPIO_TO_SERVICE}
        self.input_timer.start()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget(self)
        root.addWidget(self._stack)

        self._web_page = QWidget()
        web_layout = QVBoxLayout(self._web_page)
        web_layout.setContentsMargins(0, 0, 0, 0)
        web_layout.setSpacing(0)
        self._web_page.setFixedSize(self.w, self.h)

        self.web_view = QWebEngineView(self._web_page)
        self.web_view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.web_view.setZoomFactor(1.0)  # avoid OS DPI scaling skew in WebEngine
        web_layout.addWidget(self.web_view)

        self.bridge = WebBridge(self)
        self.channel = QWebChannel(self.web_view.page())
        self.channel.registerObject("backend", self.bridge)
        self.web_view.page().setWebChannel(self.channel)

        # WebEngineView cannot be embedded in QGraphicsScene reliably; keep it unrotated here
        self._stack.addWidget(self._web_page)

        html_path = os.path.join(BASE_DIR, "webui", "index.html")
        self.web_view.loadFinished.connect(self._on_web_loaded)
        self.web_view.setUrl(QUrl.fromLocalFile(html_path))

        self._rebuild_front_services()
        self._start_http_server()

    def _deepcopy_default_config(self):
        return json.loads(json.dumps(DEFAULT_CONFIG))

    def reset_config_to_defaults(self):
        self.cfg = self._deepcopy_default_config()
        self.front_settings = None
        save_config(self.cfg)
        self._rebuild_front_services()
        self._emit_state()

    def _normalize_front_settings(self, raw):
        if not isinstance(raw, dict):
            return None

        services_raw = raw.get("services") or []
        if isinstance(services_raw, dict):
            services_raw = [{"name": name, **(svc or {})} for name, svc in services_raw.items()]
        if not isinstance(services_raw, list):
            services_raw = []

        norm_services = []
        seen = set()
        for idx, svc in enumerate(services_raw):
            if not isinstance(svc, dict):
                continue

            key_val = str(svc.get("name") or svc.get("key") or f"XIZMAT{idx + 1}")
            if key_val in seen:
                continue
            seen.add(key_val)

            cfg_svc = self.cfg.get("services", {}).get(key_val, {})
            price_per_sec = svc.get("price_per_sec") or svc.get("pricePerSec") or cfg_svc.get("price_per_sec", 0)
            sec_from_price = None
            try:
                if price_per_sec:
                    sec_from_price = math.ceil(5000 / max(1, int(price_per_sec)))
            except Exception:
                sec_from_price = None

            seconds = max(
                1,
                int(
                    svc.get("secondsPer5000")
                    or svc.get("seconds_per_5000")
                    or sec_from_price
                    or svc.get("duration")
                    or cfg_svc.get("duration", 60)
                ),
            )

            norm_services.append(
                {
                    "key": key_val,
                    "name": key_val,
                    "label": str(svc.get("label") or svc.get("display_name") or cfg_svc.get("display_name", key_val)),
                    "theme": str(svc.get("theme") or cfg_svc.get("theme") or "suv"),
                    "icon": str(svc.get("icon") or svc.get("icon_file") or cfg_svc.get("icon") or ""),
                    "iconUrl": str(svc.get("iconUrl") or svc.get("icon_url") or ""),
                    "showIcon": bool(svc.get("showIcon", True)),
                    "active": bool(svc.get("active", cfg_svc.get("active", True))),
                    "secondsPer5000": seconds,
                }
            )

        for key, cfg_svc in self.cfg.get("services", {}).items():
            if key in seen:
                continue
            seconds = max(1, math.ceil(5000 / max(1, int(cfg_svc.get("price_per_sec", 1)))))
            norm_services.append(
                {
                    "key": key,
                    "name": key,
                    "label": str(cfg_svc.get("display_name", key)),
                    "theme": str(cfg_svc.get("theme", "suv")),
                    "icon": str(cfg_svc.get("icon", "")),
                    "iconUrl": "",
                    "showIcon": True,
                    "active": bool(cfg_svc.get("active", True)),
                    "secondsPer5000": seconds,
                }
            )

        pause_cfg = raw.get("pause") if isinstance(raw.get("pause"), dict) else {}
        free_value = pause_cfg.get("freeSeconds")
        if free_value is None:
            free_value = raw.get("freePause")
        if free_value is None:
            free_value = raw.get("free_pause")
        if free_value is None:
            free_value = (self.cfg.get("pause") or {}).get("freeSeconds", 0)
        paid_value = pause_cfg.get("paidSecondsPer5000")
        if paid_value is None:
            paid_value = raw.get("paidPause")
        if paid_value is None:
            paid_value = raw.get("paid_pause")
        if paid_value is None:
            paid_value = (self.cfg.get("pause") or {}).get("paidSecondsPer5000", 60)

        free_sec = max(0, int(free_value or 0))
        paid_sec = max(1, int(paid_value or 60))

        pin1 = str(raw.get("pin") or self.cfg.get("admin_pin", "1234"))
        pin2 = str(
            raw.get("pin2")
            or raw.get("pin_alt")
            or raw.get("admin_pin_alt")
            or raw.get("adminPinAlt")
            or self.cfg.get("admin_pin_alt", "5678")
        )

        bonus_percent = int(
            raw.get("bonusPercent")
            or raw.get("bonus_percent")
            or (raw.get("bonus") or {}).get("percent", 0)
            or self.cfg.get("bonus", {}).get("percent", 0)
        )
        bonus_threshold = int(
            raw.get("bonusThreshold")
            or raw.get("bonus_threshold")
            or (raw.get("bonus") or {}).get("threshold", 0)
            or self.cfg.get("bonus", {}).get("threshold", 0)
        )

        total_buttons = raw.get("totalButtons") or raw.get("buttonCount") or len(norm_services) or len(self.cfg.get("services", {})) or 1

        show_icons = raw.get("showIcons")
        if show_icons is None:
            show_icons = raw.get("show_icons", self.cfg.get("show_icons", True))

        return {
            "pin": pin1,
            "pin2": pin2,
            "totalButtons": int(total_buttons),
            "showIcons": bool(show_icons),
            "pause": {"freeSeconds": free_sec, "paidSecondsPer5000": paid_sec},
            "services": norm_services,
            "bonus": {"percent": bonus_percent, "threshold": bonus_threshold},
        }

    def _apply_pause_settings(self):
        pause_cfg = None
        if self.front_settings:
            pause_cfg = self.front_settings.get("pause", {})
        if not pause_cfg:
            pause_cfg = (self.cfg.get("pause") or {})

        self.pause_free_default = max(0, int((pause_cfg or {}).get("freeSeconds", 0)))
        paid_sec = max(1, int((pause_cfg or {}).get("paidSecondsPer5000", 60)))
        self.pause_paid_rate = max(1, math.ceil(5000 / paid_sec))

    def _rebuild_front_services(self):
        services = []
        price_map = {}
        fk_to_hw = {}
        hw_to_fk = {}

        if self.front_settings:
            raw = self.front_settings.get("services", [])
            total = max(1, self.front_settings.get("totalButtons") or len(raw) or len(self.cfg.get("services", {})) or 1)
            used = set()
            for svc in raw:
                if not svc.get("active", True):
                    continue
                if len(services) >= total:
                    break
                hw_key = self._map_to_hw_service(svc, used)
                if not hw_key:
                    continue
                front_key = svc.get("key") or svc.get("name") or hw_key
                seconds = max(1, int(svc.get("secondsPer5000", 60)))
                price_map[front_key] = max(1, math.ceil(5000 / seconds))
                cfg_svc = self.cfg["services"].get(hw_key, {})
                services.append(
                    {
                        "front_key": front_key,
                        "label": svc.get("label") or cfg_svc.get("display_name", front_key),
                        "theme": svc.get("theme") or cfg_svc.get("theme", "suv"),
                        "icon_file": svc.get("icon") or cfg_svc.get("icon", ""),
                        "icon_url": svc.get("iconUrl") or "",
                        "hw_key": hw_key,
                    }
                )
                fk_to_hw[front_key] = hw_key
                if hw_key:
                    hw_to_fk[hw_key] = front_key
        else:
            for key, svc_cfg in self.cfg.get("services", {}).items():
                if not svc_cfg.get("active", True):
                    continue
                price_map[key] = max(1, int(svc_cfg.get("price_per_sec", 1)))
                services.append(
                    {
                        "front_key": key,
                        "label": svc_cfg.get("display_name", key),
                        "theme": svc_cfg.get("theme", "suv"),
                        "icon_file": svc_cfg.get("icon", ""),
                        "icon_url": "",
                        "hw_key": key,
                    }
                )
                fk_to_hw[key] = key
                hw_to_fk[key] = key

        self.front_services = services
        self.price_per_sec = price_map
        self.front_key_to_hw = fk_to_hw
        self.hw_to_front = hw_to_fk
        self._apply_pause_settings()
        try:
            print("[MAP] Front -> HW mapping:")
            for slot in self.front_services:
                print(
                    f"  front_key={slot.get('front_key')} label={slot.get('label')} theme={slot.get('theme')} hw_key={slot.get('hw_key')} price={self.price_per_sec.get(slot.get('front_key'))}"
                )
        except Exception as e:
            print(f"[MAP] print failed: {e}")

    def _map_to_hw_service(self, svc, used):
        requested = (svc.get("name") or svc.get("key") or "").strip()
        if requested and requested in self.cfg.get("services", {}) and requested not in used:
            used.add(requested)
            return requested

        for fallback in self.cfg.get("services", {}).keys():
            if fallback not in used:
                used.add(fallback)
                return fallback

        return None

    def update_front_settings(self, settings):
        norm = self._normalize_front_settings(settings)
        if not norm:
            return
        self.front_settings = norm
        # sync PIN to backend config for admin overlay
        self.cfg["admin_pin"] = norm.get("pin", self.cfg.get("admin_pin", "1234"))
        self.cfg["admin_pin_alt"] = norm.get("pin2", self.cfg.get("admin_pin_alt", "5678"))
        self.cfg["show_icons"] = bool(norm.get("showIcons", self.cfg.get("show_icons", True)))
        bonus_cfg = norm.get("bonus", {}) or {}
        self.cfg["bonus"] = {
            "percent": int(bonus_cfg.get("percent", 0) or 0),
            "threshold": int(bonus_cfg.get("threshold", 0) or 0),
        }
        pause_cfg = norm.get("pause", {}) or {}
        self.cfg["pause"] = {
            "freeSeconds": int(pause_cfg.get("freeSeconds", 0) or 0),
            "paidSecondsPer5000": int(pause_cfg.get("paidSecondsPer5000", 60) or 60),
        }

        # Persist service settings while keeping hardware mapping fields (gpio_out) unchanged.
        for svc in norm.get("services", []):
            key = svc.get("name") or svc.get("key")
            if not key or key not in self.cfg["services"]:
                continue
            seconds = max(1, int(svc.get("secondsPer5000", 60)))
            price_per_sec = max(1, math.ceil(5000 / seconds))
            display_name = svc.get("label") or svc.get("display_name") or self.cfg["services"][key].get("display_name", key)
            target = self.cfg["services"][key]
            target["price_per_sec"] = price_per_sec
            target["duration"] = max(1, int(svc.get("duration", seconds)))
            target["display_name"] = display_name
            if "icon" in svc:
                target["icon"] = str(svc.get("icon") or target.get("icon", ""))
            if "theme" in svc:
                target["theme"] = str(svc.get("theme") or target.get("theme", "suv"))
            target["active"] = bool(svc.get("active", target.get("active", True)))

        save_config(self.cfg)
        self._rebuild_front_services()
        self._emit_state()

    def _on_web_loaded(self, ok):
        if not ok:
            print("Web UI yuklanmadi: webui/index.html topilmadi yoki xato bor.")
        self.web_ready = bool(ok)
        if self.web_ready and self._pending_pin_modal:
            self._open_pin_modal()
            self._pending_pin_modal = False
        self._emit_state()

    def _open_pin_modal(self):
        if not self.web_ready:
            self._pending_pin_modal = True
            return
        try:
            page = self.web_view.page()
            page.runJavaScript("window.openPinModal && window.openPinModal();")
        except Exception as e:
            print(f"[PIN] failed to open modal: {e}")

    def _icon_url(self, icon_file):
        if not icon_file:
            return ""
        icon_path = os.path.join(ICONS_DIR, icon_file)
        if not os.path.exists(icon_path):
            return ""
        return QUrl.fromLocalFile(icon_path).toString()

    def _display_title_for_service(self, service_key):
        for slot in self.front_services:
            if slot.get("hw_key") == service_key or slot.get("front_key") == service_key:
                return str(slot.get("label", "")).replace("\n", " ")
        return self.cfg["services"].get(service_key, {}).get("display_name", service_key).upper()

    def _header_color(self, mode):
        if self._low_balance_flash:
            return "#ff4d4d"
        if self.blink_timer.isActive() and self.blink_state:
            return "#ff4d4d"
        if mode == "pause":
            return "#ff4d4d"
        return "#ffffff"

    def _state_dict(self):
        mode = "idle"
        title = ""
        main_text = ""

        pause_state = {
            "status": "off",
            "remainingText": "",
            "label": "",
            "iconUrl": self._icon_url("\u26d4.png"),
        }

        if self.pause_mode:
            mode = "pause"
            remaining = max(0, self.remaining_sec)
            pause_state["status"] = "free" if self.pause_stage == "free" else "paid"
            pause_state["label"] = "TEKIN PAUZA" if self.pause_stage == "free" else "PAUZA"
            pause_state["remainingText"] = "{:02d}:{:02d}".format(remaining // 60, remaining % 60)
            title = pause_state["label"]
            main_text = pause_state["remainingText"]
        elif self.show_timer_mode and self.is_running and self.active_service:
            mode = "running"
            title = self._display_title_for_service(self.active_service)
            main_text = "{:02d}:{:02d}".format(max(0, self.remaining_sec) // 60, max(0, self.remaining_sec) % 60)
        else:
            balance_value = max(0, self.balance)
            balance_text = "{:,}".format(balance_value).replace(",", " ")
            if balance_value <= 0:
                title = "XUSH KELIBSIZ"
                main_text = self.cfg.get("moyka_name", "MOYKA")
            else:
                title = "BALANS"
                main_text = "{}\nSO'M".format(balance_text)

        services = []
        for slot in self.front_services:
            if not slot.get("front_key"):
                continue
            services.append(
                {
                    "key": slot["front_key"],
                    "name": slot["front_key"],
                    "label": slot["label"],
                    "theme": slot["theme"],
                    "icon": slot.get("icon_file", ""),
                    "iconUrl": slot.get("icon_url") or self._icon_url(slot.get("icon_file")),
                }
            )

        return {
            "mode": mode,
            "title": title,
            "mainText": main_text,
            "headerColor": self._header_color(mode),
            "balanceText": "{:,}".format(max(0, self.balance)).replace(",", " "),
            "activeService": self.active_front_key or "",
            "services": services,
            "pauseIconUrl": self._icon_url("\u26d4.png"),
            "pauseState": pause_state,
            "canAddMoney": mode == "idle",
            "total_earned": self.cfg.get("total_earned", 0),
            "admin_pins": [self.cfg.get("admin_pin", "1234"), self.cfg.get("admin_pin_alt", "5678")],
            "bonus": self.cfg.get("bonus", {}),
            "debug": bool(DEBUG),
        }

    def _settings_payload(self):
        return {
            "pin": self.cfg.get("admin_pin", "1234"),
            "pin2": self.cfg.get("admin_pin_alt", "5678"),
            "showIcons": bool(self.cfg.get("show_icons", True)),
            "show_icons": bool(self.cfg.get("show_icons", True)),
            "bonus": self.cfg.get("bonus", {}),
            "pause": self.cfg.get("pause", {}),
            "totalButtons": len(self.cfg.get("services", {})),
            "services": [
                {
                    "name": key,
                    "key": key,
                    "label": svc.get("display_name", key),
                    "display_name": svc.get("display_name", key),
                    "price_per_sec": svc.get("price_per_sec", 1),
                    "secondsPer5000": max(1, math.ceil(5000 / max(1, svc.get("price_per_sec", 1)))),
                    "duration": svc.get("duration", 60),
                    "gpio_out": svc.get("gpio_out"),
                    "icon": svc.get("icon", ""),
                    "theme": svc.get("theme", "suv"),
                    "active": bool(svc.get("active", True)),
                }
                for key, svc in self.cfg.get("services", {}).items()
            ],
            "moyka_name": self.cfg.get("moyka_name", "MOYKA"),
        }

    def _state_json(self):
        return json.dumps(self._state_dict(), ensure_ascii=False)

    def _emit_state(self):
        self.bridge.stateChanged.emit(self._state_json())

    def add_money(self, amount=5000):
        self.balance += amount
        self._apply_bonus_if_needed()
        self._emit_state()
        self._check_blink()

    def _apply_bonus_if_needed(self):
        bonus_cfg = self.cfg.get("bonus", {}) or {}
        pct = max(0, int(bonus_cfg.get("percent", 0)))
        threshold = max(0, int(bonus_cfg.get("threshold", 0)))
        if pct <= 0 or threshold <= 0:
            return
        if self._bonus_awarded:
            return
        if self.balance >= threshold:
            extra = int((self.balance * pct) / 100)
            if extra > 0:
                self.balance += extra
                self._bonus_awarded = True

    def button_clicked(self, front_key):
        front_key = front_key or ""
        hw_key = self.front_key_to_hw.get(front_key, front_key)
        price = self.price_per_sec.get(front_key)
        print(f"[CLICK] front_key={front_key} hw_key={hw_key} price={price} balance={self.balance}")
        if hw_key not in self.cfg["services"]:
            print(f"[CLICK] hw_key {hw_key} not in services")
            return

        cost = max(1, int(price or self.cfg["services"][hw_key].get("price_per_sec", 1)))

        if self.balance < cost:
            self._flash_low_balance()
            return

        if self.pause_mode:
            self._stop_pause()

        if self.is_running and self.active_service:
            self._deactivate_pin(self.active_service)

        self._pause_hold_timer.stop()
        self._pause_hold_count = 0
        self._stop_hold_source = None

        self.active_service = hw_key
        self.active_front_key = front_key
        self.pause_mode = False
        self.pause_stage = "off"
        self.pause_free_left = 0
        self.remaining_sec = math.ceil(self.balance / cost)
        self.is_running = True
        self.show_timer_mode = True
        self.session_earned = 0

        self._activate_pin(hw_key)
        self.service_timer.start()
        self._emit_state()
        self._check_blink()

    def _on_stop_pressed(self, source="touch"):
        self._stop_hold_source = source
        self._stop_hold_started = time.monotonic()
        self._pause_hold_timer.start()
        if self.is_running:
            self._stop_service(manual_pause=True)

    def _on_stop_released(self, source="touch"):
        self._pause_hold_timer.stop()
        hold_ms = None
        if self._stop_hold_started:
            hold_ms = (time.monotonic() - self._stop_hold_started) * 1000
        self._stop_hold_started = None
        if self._stop_hold_source is not None and not self.is_running and hold_ms is not None and hold_ms >= 1900:
            self._open_pin_modal()
        self._pause_hold_count = 0
        self._stop_hold_source = None

    def _tick(self):
        if self.pause_mode:
            self._tick_pause()
            return

        if not self.is_running or not self.active_service:
            return

        cost = max(1, int(self.price_per_sec.get(self.active_front_key) or self.cfg["services"][self.active_service].get("price_per_sec", 1)))

        if self.balance <= 0:
            self._stop_service()
            return

        charge = min(cost, self.balance)
        self.balance -= charge
        self.session_earned += charge
        self.remaining_sec = math.ceil(self.balance / cost) if self.balance > 0 else 0

        if self.balance <= 0:
            self._stop_service()
            return

        self._emit_state()
        self._check_blink()

    def _tick_pause(self):
        if not self.pause_mode:
            return

        if self.pause_stage == "free" and self.pause_free_left > 0:
            self.pause_free_left -= 1
            self.remaining_sec = self.pause_free_left
            if self.pause_free_left <= 0:
                self.pause_stage = "paid"
                self.remaining_sec = math.ceil(self.balance / self.pause_paid_rate) if self.balance > 0 else 0
            self._emit_state()
            return

        cost = max(1, int(self.pause_paid_rate))
        if self.balance <= 0:
            self._stop_pause()
            return

        charge = min(cost, self.balance)
        self.balance -= charge
        self.session_earned += charge
        self.remaining_sec = math.ceil(self.balance / cost) if self.balance > 0 else 0

        if self.balance <= 0:
            self._stop_pause()
            return

        self._emit_state()
        self._check_blink()

    def _stop_pause(self):
        self.pause_mode = False
        self.pause_stage = "off"
        self.pause_free_left = 0
        self.service_timer.stop()
        if self.session_earned > 0:
            self.cfg["total_earned"] = self.cfg.get("total_earned", 0) + self.session_earned
            add_session(
                {
                    "service": "PAUSE",
                    "service_name": "PAUZA",
                    "earned": self.session_earned,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            save_config(self.cfg)
        self.session_earned = 0
        self._bonus_awarded = False
        self._emit_state()
        self._check_blink()

    def _pause_hold_tick(self):
        self._pause_hold_timer.stop()
        if self._stop_hold_source is not None and not self.is_running:
            # Trigger PIN modal in the WebView when STOP/pause is held
            self._open_pin_modal()
            self._stop_hold_source = None

    def _stop_service(self, manual_pause=False):
        self.is_running = False
        self.show_timer_mode = manual_pause
        self.pause_mode = manual_pause and self.balance > 0
        self.service_timer.stop()
        self.blink_timer.stop()
        self.blink_state = False

        if self.active_service and self.session_earned > 0:
            service_display = self.cfg["services"].get(self.active_service, {}).get("display_name", self.active_service)
            self.cfg["total_earned"] = self.cfg.get("total_earned", 0) + self.session_earned
            add_session(
                {
                    "service": self.active_service,
                    "service_name": service_display,
                    "earned": self.session_earned,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            save_config(self.cfg)

        if self.active_service:
            self._deactivate_pin(self.active_service)
            self.active_service = None
            self.active_front_key = None

        if self.balance <= 0:
            self._bonus_awarded = False

        if self.pause_mode:
            self.pause_stage = "free" if self.pause_free_default > 0 else "paid"
            self.pause_free_left = self.pause_free_default
            if self.pause_stage == "free":
                self.remaining_sec = self.pause_free_left
            else:
                self.remaining_sec = math.ceil(self.balance / self.pause_paid_rate) if self.balance > 0 else 0
            self.session_earned = 0
            self.service_timer.start()
        else:
            self.session_earned = 0
            self.pause_stage = "off"
            self.pause_free_left = 0
            self.pause_mode = False

        self._emit_state()
        self._check_blink()

    def _check_blink(self):
        should = (self.is_running or self.pause_mode) and (self.balance < LOW_BALANCE or self.remaining_sec <= BLINK_WARN)
        if should and not self.blink_timer.isActive():
            self.blink_timer.start()
            self._emit_state()
        elif not should and self.blink_timer.isActive():
            self.blink_timer.stop()
            self.blink_state = False
            self._emit_state()

    def _blink(self):
        self.blink_state = not self.blink_state
        self._emit_state()

    def _flash_low_balance(self):
        self._low_balance_flash = True
        self._emit_state()

        def reset_flash():
            self._low_balance_flash = False
            self._emit_state()

        QTimer.singleShot(700, reset_flash)

    def _poll_inputs(self):
        for gpio_line, svc_name in INPUT_GPIO_TO_SERVICE.items():
            val = self.gpio.read_input(gpio_line)
            prev = self._prev_input.get(gpio_line, 0)

            if svc_name == "STOP":
                if val == 1 and prev == 0:
                    self._on_stop_pressed("gpio")
                elif val == 0 and prev == 1:
                    self._on_stop_released("gpio")
            elif svc_name == "PUL":
                if val == 1 and prev == 0:
                    self.add_money(1000)
            elif val == 1 and prev == 0:
                front_key = self.hw_to_front.get(svc_name, svc_name)
                self.button_clicked(front_key)

            self._prev_input[gpio_line] = val
    def _start_http_server(self, port=8080):
        web_root = os.path.join(BASE_DIR, "webui")
        ui_ref = self

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=web_root, **kwargs)

            def log_message(self, fmt, *args):
                return

            def _send_json(self, payload, status=200):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_GET(self):
                if self.path.startswith("/api/state"):
                    return self._send_json(ui_ref._state_dict())
                if self.path.startswith("/api/config"):
                    return self._send_json(ui_ref.cfg)
                return super().do_GET()

            def do_POST(self):
                if self.path.startswith("/api/config/reset"):
                    ui_ref.reset_config_to_defaults()
                    return self._send_json({"ok": True, "config": ui_ref.cfg, "settings": ui_ref._settings_payload()})
                if self.path.startswith("/api/config"):
                    length = int(self.headers.get("Content-Length", "0") or 0)
                    data = {}
                    if length > 0:
                        try:
                            raw = self.rfile.read(length)
                            data = json.loads(raw.decode("utf-8"))
                        except Exception:
                            data = {}
                    ui_ref._update_config_from_api(data)
                    return self._send_json({"ok": True, "config": ui_ref.cfg})
                return self._send_json({"error": "Not found"}, status=404)

        def runner():
            try:
                srv = HTTPServer(("0.0.0.0", port), Handler)
                self._http_server = srv
                print(f"[API] HTTP server http://0.0.0.0:{port}")
                srv.serve_forever()
            except Exception as e:
                print(f"[API] start xato: {e}")

        t = threading.Thread(target=runner, daemon=True)
        t.start()
        self._http_thread = t

    def _update_config_from_api(self, data):
        if not isinstance(data, dict):
            return
        if "admin_pin" in data:
            self.cfg["admin_pin"] = str(data.get("admin_pin") or self.cfg.get("admin_pin", "1234"))
        if "admin_pin_alt" in data or "pin2" in data:
            self.cfg["admin_pin_alt"] = str(data.get("admin_pin_alt") or data.get("pin2") or self.cfg.get("admin_pin_alt", "5678"))
        if "showIcons" in data or "show_icons" in data:
            self.cfg["show_icons"] = bool(data.get("showIcons", data.get("show_icons", True)))
        if "bonus" in data and isinstance(data["bonus"], dict):
            bonus = data["bonus"]
            self.cfg["bonus"] = {
                "percent": int(bonus.get("percent", 0) or 0),
                "threshold": int(bonus.get("threshold", 0) or 0),
            }
        if "pause" in data and isinstance(data["pause"], dict):
            pause = data["pause"]
            self.cfg["pause"] = {
                "freeSeconds": int(pause.get("freeSeconds", 0) or 0),
                "paidSecondsPer5000": int(pause.get("paidSecondsPer5000", 60) or 60),
            }
        if "moyka_name" in data:
            self.cfg["moyka_name"] = str(data.get("moyka_name") or self.cfg.get("moyka_name", "MOYKA"))
        if "services" in data:
            if isinstance(data["services"], dict):
                for key, svc in data["services"].items():
                    if key in self.cfg["services"] and isinstance(svc, dict):
                        self._update_service_from_api(key, svc)
            elif isinstance(data["services"], list):
                for svc in data["services"]:
                    if isinstance(svc, dict):
                        key = svc.get("name") or svc.get("key")
                        if key and key in self.cfg["services"]:
                            self._update_service_from_api(key, svc)
        save_config(self.cfg)
        self._rebuild_front_services()
        self._emit_state()

    def _update_service_from_api(self, key, svc):
        target = self.cfg["services"].get(key, {})
        display_name = svc.get("display_name") or svc.get("label")
        if display_name:
            target["display_name"] = display_name
        if "duration" in svc:
            try:
                target["duration"] = max(1, int(svc["duration"]))
            except Exception:
                pass
        # price can come as price_per_sec or secondsPer5000
        if "price_per_sec" in svc:
            try:
                target["price_per_sec"] = max(1, int(svc["price_per_sec"]))
            except Exception:
                pass
        if "secondsPer5000" in svc:
            try:
                secs = max(1, int(svc["secondsPer5000"]))
                target["price_per_sec"] = max(1, math.ceil(5000 / secs))
            except Exception:
                pass
        if "icon" in svc:
            target["icon"] = str(svc.get("icon") or target.get("icon", ""))
        if "theme" in svc:
            target["theme"] = str(svc.get("theme") or target.get("theme", "suv"))
        if "active" in svc:
            target["active"] = bool(svc.get("active"))
        # do not overwrite gpio_out here


    def _open_admin_panel(self):
        # Navigate WebView to admin page (loads admin.html)
        admin_path = os.path.join(BASE_DIR, "webui", "admin.html")
        self.web_view.setUrl(QUrl.fromLocalFile(admin_path))

    def _return_to_main(self):
        # Navigate WebView back to main page (index.html)
        html_path = os.path.join(BASE_DIR, "webui", "index.html")
        self.web_view.setUrl(QUrl.fromLocalFile(html_path))
        self._emit_state()

    def _activate_pin(self, name):
        if not name:
            return
        self.gpio.all_off()
        self.gpio.set_pin(name, 1)

    def _deactivate_pin(self, name):
        if not name:
            return
        self.gpio.set_pin(name, 0)

    def closeEvent(self, event):
        self.gpio.cleanup()
        if getattr(self, "_http_server", None):
            try:
                self._http_server.shutdown()
            except Exception:
                pass
        super().closeEvent(event)


class RotatedWindow(QWidget):
    def __init__(self):
        super().__init__()
        sg = QApplication.primaryScreen().geometry()
        sw = sg.width()
        sh = sg.height()

        self.setStyleSheet("background:#081433;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.ui = MoykaUI(sw, sh)
        layout.addWidget(self.ui)

    def show_ui(self):
        self.showFullScreen()

    def keyPressEvent(self, event):
        self.ui.keyPressEvent(event)
        if event.key() == Qt.Key.Key_Escape:
            QApplication.quit()
