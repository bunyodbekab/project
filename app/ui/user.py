import json
import math
import os
import threading
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler

from PyQt5.QtCore import QObject, QTimer, QUrl, Qt, pyqtSignal, pyqtSlot, QRectF
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import QApplication, QStackedWidget, QVBoxLayout, QWidget, QGraphicsView, QGraphicsScene, QFrame
from PyQt5.QtGui import QTransform

from app.gpio_controller import GPIOController
from app.settings import BASE_DIR, BLINK_WARN, ICONS_DIR, INPUT_GPIO_TO_SERVICE, LOW_BALANCE
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


class RotatedContainer(QGraphicsView):
    def __init__(self, inner_widget, angle_deg, parent=None, fallback_size=None):
        super().__init__(parent)
        self._inner = inner_widget
        self._angle = angle_deg
        self._fallback_size = fallback_size or (0, 0)

        self.setStyleSheet("background: transparent; border: none;")
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setAlignment(Qt.AlignCenter)

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
        self._pause_hold_timer.setInterval(1000)
        self._pause_hold_timer.timeout.connect(self._pause_hold_tick)
        self._stop_hold_source = None

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
        self.web_view.setContextMenuPolicy(Qt.NoContextMenu)
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

    def _normalize_front_settings(self, raw):
        if not isinstance(raw, dict):
            return None

        services = raw.get("services") or []
        norm_services = []
        for idx, svc in enumerate(services):
            seconds = int(svc.get("secondsPer5000") or svc.get("seconds_per_5000") or 60)
            seconds = max(1, seconds)
            key_val = svc.get("key") or svc.get("name") or f"service-{idx+1}"
            label_val = (
                svc.get("label")
                or svc.get("display_name")
                or svc.get("name")
                or svc.get("key")
                or f"Tugma {idx+1}"
            )
            norm_services.append(
                {
                    "key": key_val,
                    "name": svc.get("name") or key_val,
                    "label": label_val,
                    "theme": svc.get("theme") or "suv",
                    "icon": svc.get("icon") or "",
                    "iconUrl": svc.get("iconUrl") or "",
                    "showIcon": svc.get("showIcon", True),
                    "active": svc.get("active", True),
                    "secondsPer5000": seconds,
                }
            )

        pause_cfg = raw.get("pause") or {}
        free_sec = max(
            0,
            int(
                pause_cfg.get("freeSeconds")
                or raw.get("freePause")
                or raw.get("free_pause")
                or 0
            ),
        )
        paid_sec = max(
            1,
            int(
                pause_cfg.get("paidSecondsPer5000")
                or raw.get("paidPause")
                or raw.get("paid_pause")
                or 60
            ),
        )

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

        total_buttons = 7

        show_icons = raw.get("showIcons")
        if show_icons is None:
            show_icons = raw.get("show_icons", True)

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
            total = max(1, self.front_settings.get("totalButtons") or len(raw) or 1)
            used = set()
            for svc in raw:
                if not svc.get("active", True):
                    continue
                if len(services) >= total:
                    break
                hw_key = self._map_to_hw_service(svc, used)
                front_key = svc.get("key")
                price_map[front_key] = max(1, math.ceil(5000 / max(1, svc.get("secondsPer5000", 60))))
                services.append(
                    {
                        "front_key": front_key,
                        "label": svc.get("label") or front_key,
                        "theme": svc.get("theme") or "suv",
                        "icon_file": svc.get("icon") or "",
                        "icon_url": svc.get("iconUrl") or "",
                        "hw_key": hw_key,
                    }
                )
                fk_to_hw[front_key] = hw_key
                if hw_key:
                    hw_to_fk[hw_key] = front_key
        else:
            legacy_slots = self._build_service_slots()
            for slot in legacy_slots:
                key = slot["service_key"]
                svc_cfg = self.cfg["services"].get(key, {})
                price_map[key] = max(1, int(svc_cfg.get("price_per_sec", 1)))
                services.append(
                    {
                        "front_key": key,
                        "label": slot["label"],
                        "theme": slot["theme"],
                        "icon_file": slot.get("icon_file", ""),
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
        aliases = []
        label = (svc.get("label") or "").strip()
        key = (svc.get("key") or svc.get("name") or "").strip()
        theme = (svc.get("theme") or "").strip().upper()
        name_field = (svc.get("name") or "").strip()

        # Hard map common front labels/keys to backend service names first
        canonical = {
            "SUV": "SUV",
            "OSMOS": "OSMOS",
            "AKTIV": "KO'PIK",
            "AKTIV PENA": "KO'PIK",
            "PENA": "PENA",
            "NANO": "SHAMPUN",
            "VOSK": "VOSK",
            "QURITISH": "QURITISH",
        }
        for candidate in (label, key, name_field):
            c_up = candidate.upper()
            if c_up in canonical:
                mapped = canonical[c_up]
                if mapped in self.cfg["services"] and mapped not in used:
                    print(f"[MAP] canonical match {candidate} -> {mapped}")
                    used.add(mapped)
                    return mapped

        if label:
            aliases.append(label)
        if key:
            aliases.append(key)
        if name_field:
            aliases.append(name_field)
        if theme:
            aliases.append(theme)

        theme_aliases = {
            "SUV": ["SUV"],
            "OSMOS": ["OSMOS"],
            "AKTIV": ["AKTIV", "KO'PIK", "KOPIK", "FOAM"],
            "PENA": ["PENA"],
            "NANO": ["NANO", "SHAMPUN", "QURITISH"],
            "VOSK": ["VOSK"],
            "QURITISH": ["QURITISH"],
        }
        for alias in theme_aliases.get(theme, []):
            aliases.append(alias)

        picked = self._pick_service_for_aliases(aliases, used)
        if picked:
            print(f"[MAP] alias match {aliases} -> {picked}")
            used.add(picked)
            return picked

        for candidate in (name_field, label, key):
            if candidate and candidate in self.cfg["services"] and candidate not in used:
                print(f"[MAP] direct name match {candidate}")
                used.add(candidate)
                return candidate

        for fallback in self.cfg["services"].keys():
            if fallback not in used:
                print(f"[MAP] fallback -> {fallback}")
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

        # persist service settings (label -> display_name, secondsPer5000 -> price_per_sec)
        for svc in norm.get("services", []):
            key = svc.get("name") or svc.get("key")
            if not key or key not in self.cfg["services"]:
                continue
            seconds = max(1, int(svc.get("secondsPer5000", 60)))
            price_per_sec = max(1, math.ceil(5000 / seconds))
            display_name = svc.get("label") or svc.get("display_name") or self.cfg["services"][key].get("display_name", key)
            self.cfg["services"][key]["price_per_sec"] = price_per_sec
            self.cfg["services"][key]["duration"] = max(1, int(svc.get("duration", seconds)))
            self.cfg["services"][key]["display_name"] = display_name
            # keep gpio_out untouched

        save_config(self.cfg)
        self._rebuild_front_services()
        self._emit_state()

    def _on_web_loaded(self, ok):
        if not ok:
            print("Web UI yuklanmadi: webui/index.html topilmadi yoki xato bor.")
        self._emit_state()

    def _icon_url(self, icon_file):
        if not icon_file:
            return ""
        icon_path = os.path.join(ICONS_DIR, icon_file)
        if not os.path.exists(icon_path):
            return ""
        return QUrl.fromLocalFile(icon_path).toString()

    def _match_services_for_slots(self, slots):
        by_display = {k: v.get("display_name", k).upper() for k, v in self.cfg["services"].items()}
        used = set()
        matched = []

        for slot in slots:
            target = slot.upper()
            found = None
            for key, disp in by_display.items():
                if key in used:
                    continue
                if target in disp:
                    found = key
                    break
            if found is None:
                for key in self.cfg["services"].keys():
                    if key not in used:
                        found = key
                        break
            if found:
                used.add(found)
                matched.append(found)
        return matched

    def _pick_service_for_aliases(self, aliases, used):
        by_display = {k: v.get("display_name", k).upper() for k, v in self.cfg["services"].items()}

        for alias in aliases:
            alias_upper = alias.upper()
            for key, disp in by_display.items():
                if key in used:
                    continue
                if alias_upper in disp or alias_upper in key.upper():
                    return key

        for key in self.cfg["services"].keys():
            if key not in used:
                return key
        return None

    def _build_service_slots(self):
        slot_defs = [
            {
                "label": "SUV",
                "theme": "suv",
                "icon_file": "suv.png",
                "aliases": ["SUV"],
            },
            {
                "label": "OSMOS",
                "theme": "osmos",
                "icon_file": "osmos.png",
                "aliases": ["OSMOS"],
            },
            {
                "label": "AKTIV\nPENA",
                "theme": "aktiv",
                "icon_file": "aktiv.png",
                "aliases": ["AKTIV PENA", "AKTIV", "KO'PIK", "KOPIK", "FOAM"],
            },
            {
                "label": "PENA",
                "theme": "pena",
                "icon_file": "pena.png",
                "aliases": ["PENA"],
            },
            {
                "label": "NANO",
                "theme": "nano",
                "icon_file": "nano.png",
                "aliases": ["NANO", "SHAMPUN", "QURITISH"],
            },
            {
                "label": "VOSK",
                "theme": "vosk",
                "icon_file": "vosk.png",
                "aliases": ["VOSK"],
            },
        ]

        used = set()
        slots = []
        for slot in slot_defs:
            picked = self._pick_service_for_aliases(slot["aliases"], used)
            if not picked:
                continue
            used.add(picked)
            slots.append(
                {
                    "service_key": picked,
                    "label": slot["label"],
                    "theme": slot["theme"],
                    "icon_file": slot["icon_file"],
                }
            )
        return slots

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
                    "label": slot["label"],
                    "theme": slot["theme"],
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
        }

    def _settings_payload(self):
        return {
            "pin": self.cfg.get("admin_pin", "1234"),
            "pin2": self.cfg.get("admin_pin_alt", "5678"),
            "bonus": self.cfg.get("bonus", {}),
            "pause": self.cfg.get("pause", {}),
            "services": [
                {
                    "name": key,
                    "display_name": svc.get("display_name", key),
                    "price_per_sec": svc.get("price_per_sec", 1),
                    "secondsPer5000": max(1, math.ceil(5000 / max(1, svc.get("price_per_sec", 1)))),
                    "duration": svc.get("duration", 60),
                    "gpio_out": svc.get("gpio_out"),
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
        self._pause_hold_count = 0
        self._pause_hold_timer.start()
        if self.is_running:
            self._stop_service(manual_pause=True)

    def _on_stop_released(self, source="touch"):
        self._pause_hold_timer.stop()
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
        self._pause_hold_count += 1
        if self._pause_hold_count >= 2:
            self._pause_hold_timer.stop()
            if self._stop_hold_source is not None and not self.is_running:
                # PIN modal now handled by HTML/JS in index.html
                self._stop_hold_source = None
                self._pause_hold_count = 0

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
                        key = svc.get("name")
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
        if event.key() == Qt.Key_Escape:
            QApplication.quit()
