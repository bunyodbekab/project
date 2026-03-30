import json
import os
from datetime import datetime

from PyQt5.QtCore import QObject, QTimer, QUrl, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import QApplication, QStackedWidget, QVBoxLayout, QWidget

from app.gpio_controller import GPIOController
from app.settings import BASE_DIR, BLINK_WARN, ICONS_DIR, INPUT_GPIO_TO_SERVICE, LOW_BALANCE
from app.storage import load_config, save_config
from app.ui.admin import AdminPanel, PinOverlay


class WebBridge(QObject):
    stateChanged = pyqtSignal(str)

    def __init__(self, ui):
        super().__init__()
        self.ui = ui

    @pyqtSlot(result=str)
    def getState(self):
        return self.ui._state_json()

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


class MoykaUI(QWidget):
    def __init__(self, width, height):
        super().__init__()

        self.w = width
        self.h = height
        self.setFixedSize(width, height)

        self.cfg = load_config()
        relay_map = {name: data["relay_bit"] for name, data in self.cfg["services"].items()}
        shift_cfg = self.cfg.get("shift_register", {"data_pin": 227, "clock_pin": 75, "latch_pin": 79})
        self.gpio = GPIOController(relay_map, shift_cfg)

        self.balance = 0
        self.remaining_sec = 0
        self.active_service = None
        self.is_running = False
        self.pause_mode = False
        self.show_timer_mode = False
        self.session_earned = 0

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

        self.visible_slots = self._build_service_slots()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget(self)
        root.addWidget(self._stack)

        self._web_page = QWidget()
        web_layout = QVBoxLayout(self._web_page)
        web_layout.setContentsMargins(0, 0, 0, 0)
        web_layout.setSpacing(0)

        self.web_view = QWebEngineView(self._web_page)
        self.web_view.setContextMenuPolicy(Qt.NoContextMenu)
        web_layout.addWidget(self.web_view)

        self.bridge = WebBridge(self)
        self.channel = QWebChannel(self.web_view.page())
        self.channel.registerObject("backend", self.bridge)
        self.web_view.page().setWebChannel(self.channel)

        self._stack.addWidget(self._web_page)
        self._admin_panel = None
        self._pin_overlay = None

        html_path = os.path.join(BASE_DIR, "webui", "index.html")
        self.web_view.loadFinished.connect(self._on_web_loaded)
        self.web_view.setUrl(QUrl.fromLocalFile(html_path))

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
                "icon_file": "🌊.png",
                "aliases": ["SUV"],
            },
            {
                "label": "OSMOS",
                "theme": "osmos",
                "icon_file": "💧.png",
                "aliases": ["OSMOS"],
            },
            {
                "label": "AKTIV\nPENA",
                "theme": "aktiv",
                "icon_file": "🧪.png",
                "aliases": ["AKTIV PENA", "AKTIV", "KO'PIK", "KOPIK", "FOAM"],
            },
            {
                "label": "PENA",
                "theme": "pena",
                "icon_file": "🫧.png",
                "aliases": ["PENA"],
            },
            {
                "label": "NANO",
                "theme": "nano",
                "icon_file": "✨.png",
                "aliases": ["NANO", "SHAMPUN", "QURITISH"],
            },
            {
                "label": "VOSK",
                "theme": "vosk",
                "icon_file": "🛡️.png",
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
        for slot in self.visible_slots:
            if slot["service_key"] == service_key:
                return slot["label"].replace("\n", " ")
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

        if self.pause_mode:
            mode = "pause"
            title = "PAUZA"
            main_text = "{:02d}:{:02d}".format(max(0, self.remaining_sec) // 60, max(0, self.remaining_sec) % 60)
        elif self.show_timer_mode and self.is_running and self.active_service:
            mode = "running"
            title = self._display_title_for_service(self.active_service)
            main_text = "{:02d}:{:02d}".format(max(0, self.remaining_sec) // 60, max(0, self.remaining_sec) % 60)
        else:
            balance_text = "{:,}".format(max(0, self.balance)).replace(",", " ")
            main_text = "{}\nSO'M".format(balance_text)

        services = []
        for slot in self.visible_slots:
            key = slot["service_key"]
            svc = self.cfg["services"].get(key)
            if not svc:
                continue
            services.append(
                {
                    "key": key,
                    "label": slot["label"],
                    "theme": slot["theme"],
                    "iconUrl": self._icon_url(slot["icon_file"]),
                }
            )

        return {
            "mode": mode,
            "title": title,
            "mainText": main_text,
            "headerColor": self._header_color(mode),
            "balanceText": "{:,}".format(max(0, self.balance)).replace(",", " "),
            "activeService": self.active_service or "",
            "services": services,
            "pauseIconUrl": self._icon_url("\u26d4.png"),
            "canAddMoney": mode == "idle",
        }

    def _state_json(self):
        return json.dumps(self._state_dict(), ensure_ascii=False)

    def _emit_state(self):
        self.bridge.stateChanged.emit(self._state_json())

    def add_money(self, amount=5000):
        self.balance += amount
        self._emit_state()
        self._check_blink()

    def button_clicked(self, name):
        if name not in self.cfg["services"]:
            return

        svc_data = self.cfg["services"][name]
        cost = max(1, int(svc_data.get("price_per_sec", 0)))

        if self.balance < cost:
            self._flash_low_balance()
            return

        if self.is_running and self.active_service:
            self._deactivate_pin(self.active_service)

        self._pause_hold_timer.stop()
        self._pause_hold_count = 0
        self._stop_hold_source = None

        self.active_service = name
        self.pause_mode = False
        self.remaining_sec = self.balance // cost
        self.is_running = True
        self.show_timer_mode = True
        self.session_earned = 0

        self._activate_pin(name)
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
        if not self.is_running or not self.active_service:
            return

        cost = max(1, int(self.cfg["services"][self.active_service].get("price_per_sec", 0)))
        charge = min(cost, self.balance)
        self.balance -= charge
        self.session_earned += charge
        self.remaining_sec -= 1

        if self.balance <= 0 or self.remaining_sec <= 0:
            self._stop_service()
            return

        self._emit_state()
        self._check_blink()

    def _pause_hold_tick(self):
        self._pause_hold_count += 1
        if self._pause_hold_count >= 5:
            self._pause_hold_timer.stop()
            if self._stop_hold_source is not None and not self.is_running:
                self._show_pin_overlay()
                self._stop_hold_source = None
                self._pause_hold_count = 0

    def _stop_service(self, manual_pause=False):
        self.is_running = False
        self.show_timer_mode = manual_pause
        self.pause_mode = manual_pause and self.balance > 0 and self.remaining_sec > 0
        self.service_timer.stop()
        self.blink_timer.stop()
        self.blink_state = False

        if self.active_service and self.session_earned > 0:
            service_display = self.cfg["services"].get(self.active_service, {}).get("display_name", self.active_service)
            self.cfg["total_earned"] = self.cfg.get("total_earned", 0) + self.session_earned
            self.cfg.setdefault("sessions", []).append(
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

        self.session_earned = 0
        self._emit_state()
        self._check_blink()

    def _check_blink(self):
        should = self.balance < LOW_BALANCE or (self.is_running and self.remaining_sec <= BLINK_WARN)
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
            elif val == 1 and prev == 0:
                self.button_clicked(svc_name)

            self._prev_input[gpio_line] = val

    def _show_pin_overlay(self):
        if self._pin_overlay:
            self._pin_overlay.deleteLater()
        self._pin_overlay = PinOverlay(self.cfg.get("admin_pin", "1234"), self._web_page)
        self._pin_overlay.setGeometry(0, 0, self.w, self.h)
        self._pin_overlay.show()
        self._pin_overlay.raise_()
        self._pin_overlay.accepted.connect(self._open_admin_panel)
        self._pin_overlay.rejected.connect(self._close_pin_overlay)

    def _close_pin_overlay(self):
        if self._pin_overlay:
            self._pin_overlay.hide()
            self._pin_overlay.deleteLater()
            self._pin_overlay = None

    def _build_admin_page(self):
        if self._admin_panel:
            self._stack.removeWidget(self._admin_panel)
            self._admin_panel.deleteLater()
        self._admin_panel = AdminPanel(self.cfg, self.w, self.h, self)
        self._admin_panel.config_changed.connect(self._apply_config)
        self._admin_panel.close_requested.connect(self._close_admin)
        self._stack.addWidget(self._admin_panel)

    def _open_admin_panel(self):
        self._close_pin_overlay()
        self._build_admin_page()
        self._stack.setCurrentIndex(1)

    def _close_admin(self):
        self._stack.setCurrentIndex(0)
        self._emit_state()

    def _apply_config(self, new_cfg):
        self.cfg = new_cfg
        save_config(self.cfg)
        self.visible_slots = self._build_service_slots()
        self._emit_state()

    def _activate_pin(self, name):
        self.gpio.all_off()
        self.gpio.set_pin(name, 1)

    def _deactivate_pin(self, name):
        self.gpio.set_pin(name, 0)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.add_money(5000)

    def closeEvent(self, event):
        self.gpio.cleanup()
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
