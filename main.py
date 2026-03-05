import sys
import json
import os
import gpiod
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QGraphicsView, QGraphicsScene, QDialog,
    QScrollArea, QFrame, QLineEdit,
    QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont

# ─────────────────────────────────────────────
# Config fayli
# ─────────────────────────────────────────────
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

DEFAULT_CONFIG = {
    "services": {
        "KO'PIK":   {"display_name": "KO'PIK",   "price_per_sec": 200, "duration": 60,  "gpio_out": 227},
        "SUV":      {"display_name": "SUV",      "price_per_sec": 150, "duration": 100, "gpio_out": 75},
        "SHAMPUN":  {"display_name": "SHAMPUN",  "price_per_sec": 250, "duration": 80,  "gpio_out": 79},
        "VOSK":     {"display_name": "VOSK",     "price_per_sec": 350, "duration": 70,  "gpio_out": 78},
        "PENA":     {"display_name": "PENA",     "price_per_sec": 300, "duration": 50,  "gpio_out": 71},
        "OSMOS":    {"display_name": "OSMOS",    "price_per_sec": 200, "duration": 90,  "gpio_out": 233},
        "QURITISH": {"display_name": "QURITISH", "price_per_sec": 100, "duration": 120, "gpio_out": 74},
    },
    "admin_pin": "1234",
    "total_earned": 0,
    "sessions": []
}

# Physical pin → GPIO line (input)
INPUT_GPIO_TO_SERVICE = {
    229: "KO'PIK",
    228: "SUV",
    73:  "SHAMPUN",
    70:  "VOSK",
    72:  "PENA",
    231: "OSMOS",
    232: "QURITISH",
    230: "STOP",
}

CHIP_NAME   = "gpiochip0"
LOW_BALANCE = 2000
BLINK_WARN  = 10


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, val in DEFAULT_CONFIG.items():
                if key not in data:
                    data[key] = val
            for svc_name, svc_default in DEFAULT_CONFIG["services"].items():
                if svc_name not in data["services"]:
                    data["services"][svc_name] = svc_default
                    continue
                for k, v in svc_default.items():
                    if k not in data["services"][svc_name]:
                        data["services"][svc_name][k] = v
            return data
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Config saqlashda xato: {e}")


# ─────────────────────────────────────────────
# GPIO Controller
# ─────────────────────────────────────────────
class GPIOController:
    def __init__(self, out_pin_map):
        self.chip      = None
        self.out_lines = {}
        self.in_lines  = {}
        try:
            self.chip = gpiod.Chip(CHIP_NAME)
            for name, pin in out_pin_map.items():
                try:
                    line = self.chip.get_line(pin)
                    line.request(consumer="moyka_out", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])
                    self.out_lines[name] = line
                except Exception as e:
                    print(f"Output GPIO xatosi [{name}={pin}]: {e}")
            for gpio_line in INPUT_GPIO_TO_SERVICE:
                try:
                    line = self.chip.get_line(gpio_line)
                    line.request(consumer="moyka_in", type=gpiod.LINE_REQ_DIR_IN)
                    self.in_lines[gpio_line] = line
                except Exception as e:
                    print(f"Input GPIO xatosi [line={gpio_line}]: {e}")
            print("GPIO tayyor.")
        except Exception as e:
            print(f"GPIO chip xatosi (simulyatsiya rejimida): {e}")
            self.chip = None

    def set_pin(self, name, value):
        if name in self.out_lines:
            try:
                self.out_lines[name].set_value(int(value))
            except Exception as e:
                print(f"GPIO set xatosi [{name}]: {e}")
        else:
            print(f"[SIM] GPIO OUT {name} -> {value}")

    def read_input(self, gpio_line):
        if gpio_line in self.in_lines:
            try:
                return self.in_lines[gpio_line].get_value()
            except Exception:
                return 0
        return 0

    def all_off(self):
        for name in list(self.out_lines.keys()):
            self.set_pin(name, 0)

    def cleanup(self):
        self.all_off()
        if self.chip:
            try:
                self.chip.close()
            except Exception:
                pass


# ─────────────────────────────────────────────
# Virtual Keyboard (raqamli)
# ─────────────────────────────────────────────
class VirtualKeyboard(QWidget):
    key_pressed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QGridLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)
        keys = [
            ["7", "8", "9"],
            ["4", "5", "6"],
            ["1", "2", "3"],
            [u"\u2190", "0", u"\u2713"],
        ]
        for row_i, row in enumerate(keys):
            for col_i, key in enumerate(row):
                btn = QPushButton(key)
                btn.setFont(QFont("Arial", 22, QFont.Bold))
                btn.setMinimumSize(80, 65)
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                if key == u"\u2713":
                    btn.setStyleSheet("QPushButton{background:#16a34a;color:white;border-radius:14px;border:2px solid #22c55e;}QPushButton:pressed{background:#15803d;}")
                elif key == u"\u2190":
                    btn.setStyleSheet("QPushButton{background:#dc2626;color:white;border-radius:14px;border:2px solid #ef4444;}QPushButton:pressed{background:#b91c1c;}")
                else:
                    btn.setStyleSheet("QPushButton{background:#1e293b;color:white;border-radius:14px;border:2px solid #334155;}QPushButton:hover{background:#2563eb;}QPushButton:pressed{background:#1d4ed8;}")
                btn.clicked.connect(lambda _, k=key: self.key_pressed.emit(k))
                layout.addWidget(btn, row_i, col_i)


class AdminVirtualKeyboard(QWidget):
    key_pressed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QGridLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)

        rows = [
            ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
            ["A", "S", "D", "F", "G", "H", "J", "K", "L"],
            ["Z", "X", "C", "V", "B", "N", "M", "_", "-"],
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
            ["SPACE", u"\u2190", u"\u2713"],
        ]

        for row_i, row in enumerate(rows):
            col_i = 0
            for key in row:
                btn = QPushButton(key if key != "SPACE" else "Bo'shliq")
                btn.setFont(QFont("Arial", 11, QFont.Bold))
                btn.setMinimumHeight(46)
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                span = 1

                if key == "SPACE":
                    span = 3
                    btn.setStyleSheet("QPushButton{background:#475569;color:white;border-radius:10px;border:1px solid #64748b;}QPushButton:pressed{background:#334155;}")
                elif key == u"\u2713":
                    btn.setStyleSheet("QPushButton{background:#16a34a;color:white;border-radius:10px;border:1px solid #22c55e;}QPushButton:pressed{background:#15803d;}")
                elif key == u"\u2190":
                    btn.setStyleSheet("QPushButton{background:#dc2626;color:white;border-radius:10px;border:1px solid #ef4444;}QPushButton:pressed{background:#b91c1c;}")
                else:
                    btn.setStyleSheet("QPushButton{background:#1e293b;color:white;border-radius:10px;border:1px solid #334155;}QPushButton:pressed{background:#0f172a;}")

                btn.clicked.connect(lambda _, k=key: self.key_pressed.emit(k))
                layout.addWidget(btn, row_i, col_i, 1, span)
                col_i += span


# ─────────────────────────────────────────────
# Admin PIN kirish modali
# ─────────────────────────────────────────────
class PinDialog(QDialog):
    def __init__(self, correct_pin, parent=None):
        super().__init__(parent)
        self.correct_pin  = correct_pin
        self.accepted_pin = False
        self._pin         = ""
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setStyleSheet("background:#0f172a; border-radius:20px;")
        self.setMinimumWidth(360)

        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        lay.setContentsMargins(28, 28, 28, 28)

        title = QLabel("ADMIN PANEL")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Arial", 20, QFont.Bold))
        title.setStyleSheet("color:#38bdf8;")
        lay.addWidget(title)

        self.pin_display = QLabel("")
        self.pin_display.setAlignment(Qt.AlignCenter)
        self.pin_display.setFont(QFont("Arial", 32, QFont.Bold))
        self.pin_display.setStyleSheet("color:white;background:#1e293b;border-radius:12px;padding:10px;")
        self.pin_display.setMinimumHeight(65)
        lay.addWidget(self.pin_display)

        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setFont(QFont("Arial", 13))
        self.error_label.setStyleSheet("color:#ef4444;")
        lay.addWidget(self.error_label)

        self.keyboard = VirtualKeyboard()
        self.keyboard.key_pressed.connect(self._on_key)
        lay.addWidget(self.keyboard)

        cancel_btn = QPushButton("Bekor qilish")
        cancel_btn.setFont(QFont("Arial", 14))
        cancel_btn.setMinimumHeight(48)
        cancel_btn.setStyleSheet("QPushButton{background:#334155;color:white;border-radius:12px;border:2px solid #475569;}QPushButton:pressed{background:#1e293b;}")
        cancel_btn.clicked.connect(self.reject)
        lay.addWidget(cancel_btn)

    def _on_key(self, key):
        if key == u"\u2190":
            self._pin = self._pin[:-1]
        elif key == u"\u2713":
            self._check_pin()
            return
        else:
            if len(self._pin) < 8:
                self._pin += key
        self.pin_display.setText(u"\u25cf" * len(self._pin))

    def _check_pin(self):
        if self._pin == self.correct_pin:
            self.accepted_pin = True
            self.accept()
        else:
            self.error_label.setText("Noto'g'ri PIN!")
            self._pin = ""
            self.pin_display.setText("")
            QTimer.singleShot(1500, lambda: self.error_label.setText(""))


# ─────────────────────────────────────────────
# Admin Panel
# ─────────────────────────────────────────────
class AdminPanel(QDialog):
    config_changed = pyqtSignal(dict)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg         = json.loads(json.dumps(cfg))
        self._active_svc   = None
        self._active_edit  = None
        self._active_order = []
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setStyleSheet("background:#0f172a;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet("background:#1e3a5f;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(20, 14, 20, 14)
        title = QLabel("ADMIN PANEL")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        title.setStyleSheet("color:#38bdf8;")
        h_lay.addWidget(title)
        h_lay.addStretch()
        close_btn = QPushButton("X")
        close_btn.setFont(QFont("Arial", 16, QFont.Bold))
        close_btn.setFixedSize(42, 42)
        close_btn.setStyleSheet("QPushButton{background:#dc2626;color:white;border-radius:21px;border:none;}QPushButton:pressed{background:#b91c1c;}")
        close_btn.clicked.connect(self.reject)
        h_lay.addWidget(close_btn)
        root.addWidget(header)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:#0f172a;}")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setStyleSheet("background:#0f172a;")
        c_lay = QVBoxLayout(content)
        c_lay.setSpacing(10)
        c_lay.setContentsMargins(20, 18, 20, 18)

        # Hisobot
        rep_frame = QFrame()
        rep_frame.setStyleSheet("background:#0c2340;border-radius:14px;border:1px solid #1e3a5f;")
        r_lay = QVBoxLayout(rep_frame)
        r_lay.setContentsMargins(16, 14, 16, 14)
        r_lay.setSpacing(6)

        rep_title = QLabel("MOLIYAVIY HISOBOT")
        rep_title.setFont(QFont("Arial", 14, QFont.Bold))
        rep_title.setStyleSheet("color:#38bdf8;border:none;")
        r_lay.addWidget(rep_title)

        total    = self.cfg.get("total_earned", 0)
        sessions = self.cfg.get("sessions", [])

        earned_lbl = QLabel("Jami tushum: {:,} so'm".format(total).replace(",", " "))
        earned_lbl.setFont(QFont("Arial", 15, QFont.Bold))
        earned_lbl.setStyleSheet("color:#4ade80;border:none;")
        r_lay.addWidget(earned_lbl)

        sess_lbl = QLabel("Sessiyalar soni: {}".format(len(sessions)))
        sess_lbl.setFont(QFont("Arial", 12))
        sess_lbl.setStyleSheet("color:#94a3b8;border:none;")
        r_lay.addWidget(sess_lbl)

        if sessions:
            last_lbl = QLabel("Oxirgi sessiyalar:")
            last_lbl.setFont(QFont("Arial", 11, QFont.Bold))
            last_lbl.setStyleSheet("color:#cbd5e1;border:none;margin-top:6px;")
            r_lay.addWidget(last_lbl)
            for s in reversed(sessions[-5:]):
                shown_name = s.get("service_name") or s.get("service", "?")
                s_lbl = QLabel("  {}  -  {:,} so'm".format(shown_name, s.get("earned",0)).replace(",", " "))
                s_lbl.setFont(QFont("Arial", 11))
                s_lbl.setStyleSheet("color:#94a3b8;border:none;")
                r_lay.addWidget(s_lbl)

        c_lay.addWidget(rep_frame)

        # Xizmatlar
        svc_title = QLabel("XIZMATLAR SOZLAMASI")
        svc_title.setFont(QFont("Arial", 14, QFont.Bold))
        svc_title.setStyleSheet("color:#f8fafc;margin-top:10px;")
        c_lay.addWidget(svc_title)

        self.service_widgets = {}
        for svc_name, svc_data in self.cfg["services"].items():
            frame = QFrame()
            frame.setStyleSheet("background:#1e293b;border-radius:14px;border:1px solid #334155;")
            f_lay = QVBoxLayout(frame)
            f_lay.setContentsMargins(14, 12, 14, 12)
            f_lay.setSpacing(8)

            # Nom satri
            name_row = QHBoxLayout()
            nl = QLabel("Nom:")
            nl.setFont(QFont("Arial", 11))
            nl.setStyleSheet("color:#94a3b8;border:none;")
            nl.setFixedWidth(130)
            name_edit = QLineEdit(svc_data.get("display_name", svc_name))
            name_edit.setFont(QFont("Arial", 13))
            name_edit.setStyleSheet("QLineEdit{background:#0f172a;color:white;border-radius:8px;border:1px solid #475569;padding:6px 10px;}")
            name_edit.setReadOnly(True)
            name_row.addWidget(nl)
            name_row.addWidget(name_edit)
            f_lay.addLayout(name_row)

            # Narx satr
            price_row = QHBoxLayout()
            pl = QLabel("Narx/s (so'm):")
            pl.setFont(QFont("Arial", 11))
            pl.setStyleSheet("color:#94a3b8;border:none;")
            pl.setFixedWidth(130)
            price_edit = QLineEdit(str(svc_data["price_per_sec"]))
            price_edit.setFont(QFont("Arial", 13))
            price_edit.setStyleSheet("QLineEdit{background:#0f172a;color:#38bdf8;border-radius:8px;border:1px solid #475569;padding:6px 10px;}")
            price_edit.setReadOnly(True)
            price_row.addWidget(pl)
            price_row.addWidget(price_edit)
            f_lay.addLayout(price_row)

            # Vaqt satr
            dur_row = QHBoxLayout()
            dl = QLabel("Vaqt (soniya):")
            dl.setFont(QFont("Arial", 11))
            dl.setStyleSheet("color:#94a3b8;border:none;")
            dl.setFixedWidth(130)
            dur_edit = QLineEdit(str(svc_data["duration"]))
            dur_edit.setFont(QFont("Arial", 13))
            dur_edit.setStyleSheet("QLineEdit{background:#0f172a;color:#a78bfa;border-radius:8px;border:1px solid #475569;padding:6px 10px;}")
            dur_edit.setReadOnly(True)
            dur_row.addWidget(dl)
            dur_row.addWidget(dur_edit)
            f_lay.addLayout(dur_row)

            # Tahrirlash tugmasi
            edit_btn = QPushButton("Tahrirlash")
            edit_btn.setFont(QFont("Arial", 12))
            edit_btn.setMinimumHeight(42)
            edit_btn.setStyleSheet("QPushButton{background:#2563eb;color:white;border-radius:10px;border:none;}QPushButton:pressed{background:#1d4ed8;}")
            edit_btn.clicked.connect(lambda _, n=svc_name, ne=name_edit, pe=price_edit, de=dur_edit: self._start_edit(n, ne, pe, de))
            f_lay.addWidget(edit_btn)

            c_lay.addWidget(frame)
            self.service_widgets[svc_name] = {
                "name_edit": name_edit,
                "price_edit": price_edit,
                "dur_edit": dur_edit,
            }

        # Saqlash
        save_btn = QPushButton("SAQLASH VA CHIQISH")
        save_btn.setFont(QFont("Arial", 15, QFont.Bold))
        save_btn.setMinimumHeight(56)
        save_btn.setStyleSheet("QPushButton{background:#16a34a;color:white;border-radius:14px;border:none;margin-top:10px;}QPushButton:pressed{background:#15803d;}")
        save_btn.clicked.connect(self._save_and_close)
        c_lay.addWidget(save_btn)

        scroll.setWidget(content)
        root.addWidget(scroll)

        # Virtual keyboard pastda
        kbd_container = QWidget()
        kbd_container.setStyleSheet("background:#1e293b;border-top:1px solid #334155;")
        kbd_outer = QVBoxLayout(kbd_container)
        kbd_outer.setContentsMargins(20, 12, 20, 12)
        self.vkb = AdminVirtualKeyboard()
        self.vkb.key_pressed.connect(self._kbd_input)
        kbd_outer.addWidget(self.vkb)
        root.addWidget(kbd_container)

    def _start_edit(self, svc_name, name_edit, price_edit, dur_edit):
        # Avvalgi editni yoping
        if self._active_svc and self._active_svc in self.service_widgets:
            nw = self.service_widgets[self._active_svc]["name_edit"]
            pw = self.service_widgets[self._active_svc]["price_edit"]
            dw = self.service_widgets[self._active_svc]["dur_edit"]
            nw.setReadOnly(True)
            nw.setStyleSheet("QLineEdit{background:#0f172a;color:white;border-radius:8px;border:1px solid #475569;padding:6px 10px;}")
            pw.setReadOnly(True)
            pw.setStyleSheet("QLineEdit{background:#0f172a;color:#38bdf8;border-radius:8px;border:1px solid #475569;padding:6px 10px;}")
            dw.setReadOnly(True)
            dw.setStyleSheet("QLineEdit{background:#0f172a;color:#a78bfa;border-radius:8px;border:1px solid #475569;padding:6px 10px;}")

        self._active_svc  = svc_name
        self._active_edit = name_edit
        self._active_order = [name_edit, price_edit, dur_edit]
        name_edit.setReadOnly(False)
        name_edit.setStyleSheet("QLineEdit{background:#0c2340;color:white;border-radius:8px;border:2px solid #e2e8f0;padding:6px 10px;}")
        price_edit.setReadOnly(False)
        price_edit.setStyleSheet("QLineEdit{background:#0c2340;color:#38bdf8;border-radius:8px;border:2px solid #38bdf8;padding:6px 10px;}")
        dur_edit.setReadOnly(False)
        dur_edit.setStyleSheet("QLineEdit{background:#0c2340;color:#a78bfa;border-radius:8px;border:2px solid #a78bfa;padding:6px 10px;}")

    def _kbd_input(self, key):
        if self._active_edit is None:
            return
        if self._active_edit.isReadOnly():
            return

        name_edit = self.service_widgets.get(self._active_svc, {}).get("name_edit")
        is_name_field = (self._active_edit == name_edit)
        txt = self._active_edit.text()

        if key == u"\u2190":
            self._active_edit.setText(txt[:-1])
        elif key == u"\u2713":
            if self._active_order:
                idx = self._active_order.index(self._active_edit)
                self._active_edit = self._active_order[(idx + 1) % len(self._active_order)]
        else:
            if not is_name_field and (not key.isdigit()):
                return
            char = " " if key == "SPACE" else key
            limit = 20 if is_name_field else 6
            if len(txt) < limit:
                self._active_edit.setText(txt + char)

    def _save_and_close(self):
        for svc, w in self.service_widgets.items():
            try:
                display_name = w["name_edit"].text().strip()
                p = int(w["price_edit"].text())
                d = int(w["dur_edit"].text())
                self.cfg["services"][svc]["display_name"] = display_name if display_name else svc
                self.cfg["services"][svc]["price_per_sec"] = max(1, p)
                self.cfg["services"][svc]["duration"]      = max(1, d)
            except ValueError:
                pass
        self.config_changed.emit(self.cfg)
        self.accept()


# ─────────────────────────────────────────────
# Asosiy UI
# ─────────────────────────────────────────────
class MoykaUI(QWidget):
    def __init__(self, width, height):
        super().__init__()
        self.w = width
        self.h = height
        self.setFixedSize(width, height)

        self.cfg = load_config()

        out_pins = {n: d["gpio_out"] for n, d in self.cfg["services"].items()}
        self.gpio = GPIOController(out_pins)

        self.balance         = 0
        self.remaining_sec   = 0
        self.cost_per_sec    = 0
        self.active_service  = None
        self.is_running      = False
        self.blink_state     = False
        self.show_timer_mode = False
        self.session_earned  = 0

        # Pause uzoq ushlab turish
        self._pause_hold_count = 0
        self._pause_hold_timer = QTimer(self)
        self._pause_hold_timer.setInterval(1000)
        self._pause_hold_timer.timeout.connect(self._pause_hold_tick)
        self._stop_hold_source = None
        self._admin_opened_by_hold = False
        self._stop_gpio_hold_ms = 0

        self.service_timer = QTimer(self)
        self.service_timer.setInterval(1000)
        self.service_timer.timeout.connect(self._tick)

        self.blink_timer = QTimer(self)
        self.blink_timer.setInterval(400)
        self.blink_timer.timeout.connect(self._blink)

        # GPIO input polling (100ms)
        self.input_timer = QTimer(self)
        self.input_timer.setInterval(100)
        self.input_timer.timeout.connect(self._poll_inputs)
        self._prev_input = {gl: 0 for gl in INPUT_GPIO_TO_SERVICE}
        self.input_timer.start()

        self.setStyleSheet("QWidget{background-color:#0f172a;} QLabel{color:white;}")

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(24, 16, 24, 16)

        self.header_label = QLabel("0 so'm")
        self.header_label.setAlignment(Qt.AlignCenter)
        self.header_label.setFont(QFont("Arial", int(height * 0.075), QFont.Bold))
        self.header_label.setStyleSheet("color:#38bdf8;")
        main_layout.addWidget(self.header_label)

        self.service_label = QLabel("")
        self.service_label.setAlignment(Qt.AlignCenter)
        self.service_label.setFont(QFont("Arial", int(height * 0.026)))
        self.service_label.setStyleSheet("color:#94a3b8;")
        main_layout.addWidget(self.service_label)

        self.grid = QGridLayout()
        self.grid.setSpacing(12)

        svc_names  = list(self.cfg["services"].keys())
        all_names  = svc_names + ["STOP"]
        positions  = [(i, j) for i in range(4) for j in range(2)]
        btn_h      = int(height * 0.13)
        name_fs    = int(height * 0.027)
        price_fs   = int(height * 0.021)

        self.btn_widgets = {}

        for pos, name in zip(positions, all_names):
            container = QWidget()
            container.setStyleSheet("background:transparent;")
            v = QVBoxLayout(container)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(2)

            btn = QPushButton(name)
            btn.setFont(QFont("Arial", name_fs, QFont.Bold))
            btn.setMinimumHeight(btn_h)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            if name == "STOP":
                btn.setStyleSheet(self._stop_style())
            else:
                btn.setStyleSheet(self._normal_style())

            if name == "STOP":
                btn.pressed.connect(self._on_stop_pressed)
                btn.released.connect(self._on_stop_released)
            else:
                btn.clicked.connect(lambda checked, n=name: self.button_clicked(n))

            price_lbl = None
            if name != "STOP":
                p = self.cfg["services"][name]["price_per_sec"]
                btn.setText(self.cfg["services"][name].get("display_name", name))
                price_lbl = QLabel("{} so'm/s".format(p))
                price_lbl.setAlignment(Qt.AlignCenter)
                price_lbl.setFont(QFont("Arial", price_fs))
                price_lbl.setStyleSheet("color:#64748b;")
                v.addWidget(btn)
                v.addWidget(price_lbl)
            else:
                v.addWidget(btn)

            self.grid.addWidget(container, *pos)
            self.btn_widgets[name] = {"btn": btn, "price_lbl": price_lbl}

        main_layout.addLayout(self.grid)
        self._update_header()

    # ── Stil metodlar ──
    def _normal_style(self):
        return "QPushButton{background:#1e293b;color:white;border-radius:20px;border:2px solid #334155;}QPushButton:hover{background:#2563eb;border:2px solid #3b82f6;}QPushButton:pressed{background:#1d4ed8;}"

    def _active_style(self):
        return "QPushButton{background:#0369a1;color:#7dd3fc;border-radius:20px;border:3px solid #38bdf8;}"

    def _stop_style(self):
        return "QPushButton{background:#7f1d1d;color:white;border-radius:20px;border:2px solid #ef4444;}QPushButton:hover{background:#991b1b;}QPushButton:pressed{background:#450a0a;}"

    # ── Enter = 5000 so'm ──
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.balance += 5000
            self._update_header()
            self._check_blink()

    # ── GPIO input polling ──
    def _poll_inputs(self):
        for gpio_line, svc_name in INPUT_GPIO_TO_SERVICE.items():
            val  = self.gpio.read_input(gpio_line)
            prev = self._prev_input.get(gpio_line, 0)
            if svc_name == "STOP":
                if val == 1 and prev == 0:
                    self._on_stop_pressed("gpio")
                    self._stop_gpio_hold_ms = 0
                elif val == 1 and prev == 1:
                    self._stop_gpio_hold_ms += self.input_timer.interval()
                elif val == 0 and prev == 1:
                    self._on_stop_released("gpio")
                    self._stop_gpio_hold_ms = 0
            elif val == 1 and prev == 0:   # rising edge
                self.button_clicked(svc_name)
            self._prev_input[gpio_line] = val

    # ── Tugma bosildi ──
    def button_clicked(self, name):
        if name not in self.cfg["services"]:
            return

        svc_data = self.cfg["services"][name]
        cost     = svc_data["price_per_sec"]
        duration = svc_data["duration"]

        if self.balance < cost:
            self._flash_low_balance()
            return

        if self.is_running and self.active_service:
            self._deactivate_pin(self.active_service)
            self._set_btn_style(self.active_service, "normal")

        self.active_service  = name
        self.cost_per_sec    = cost
        self.remaining_sec   = duration
        self.is_running      = True
        self.show_timer_mode = True
        self.session_earned  = 0

        self._activate_pin(name)
        self._set_btn_style(name, "active")
        display_name = svc_data.get("display_name", name)
        self.service_label.setText("{}  |  {} so'm/s  |  {} s".format(display_name, cost, duration))
        self.service_timer.start()
        self._update_header()
        self._check_blink()

    def _on_stop_pressed(self, source="touch"):
        self._stop_hold_source = source
        self._admin_opened_by_hold = False
        self._pause_hold_count = 0
        self._pause_hold_timer.start()
        self._stop_service()

    def _on_stop_released(self, source="touch"):
        if self._stop_hold_source == source:
            self._pause_hold_timer.stop()
            self._pause_hold_count = 0
            self._stop_hold_source = None

    # ── Har 1 soniyada ──
    def _tick(self):
        if not self.is_running:
            return

        cost = self.cfg["services"][self.active_service]["price_per_sec"]

        charge              = min(cost, self.balance)
        self.balance       -= charge
        self.session_earned += charge
        self.remaining_sec  -= 1

        if self.balance <= 0 or self.remaining_sec <= 0:
            self._stop_service()
            return

        self._update_header()
        self._check_blink()

    # ── Pause hold ──
    def _pause_hold_tick(self):
        self._pause_hold_count += 1
        if self._pause_hold_count >= 5:
            self._pause_hold_timer.stop()
            self._admin_opened_by_hold = True
            self._open_admin()

    # ── Stop ──
    def _stop_service(self):
        self.is_running      = False
        self.show_timer_mode = False
        self.service_timer.stop()
        self.blink_timer.stop()
        self.blink_state     = False

        if self.active_service and self.session_earned > 0:
            display_name = self.cfg["services"].get(self.active_service, {}).get("display_name", self.active_service)
            self.cfg["total_earned"] = self.cfg.get("total_earned", 0) + self.session_earned
            self.cfg.setdefault("sessions", []).append({
                "service": self.active_service,
                "service_name": display_name,
                "earned":  self.session_earned
            })
            save_config(self.cfg)

        if self.active_service:
            self._deactivate_pin(self.active_service)
            self._set_btn_style(self.active_service, "normal")
            self.active_service = None

        self.session_earned = 0
        self.service_label.setText("")
        self._update_header()
        self._reset_header_color()

    # ── Admin panel ──
    def _open_admin(self):
        pin_dlg = PinDialog(self.cfg.get("admin_pin", "1234"), self)
        pin_dlg.adjustSize()
        geom = self.geometry()
        pin_dlg.move(
            geom.x() + (geom.width()  - pin_dlg.width())  // 2,
            geom.y() + (geom.height() - pin_dlg.height()) // 2,
        )
        if pin_dlg.exec_() == QDialog.Accepted and pin_dlg.accepted_pin:
            admin = AdminPanel(self.cfg, self)
            admin.config_changed.connect(self._apply_config)
            admin.showMaximized()
            admin.exec_()

    def _apply_config(self, new_cfg):
        self.cfg = new_cfg
        save_config(self.cfg)
        for svc_name, w in self.btn_widgets.items():
            if svc_name == "STOP" or w["price_lbl"] is None:
                continue
            svc = self.cfg["services"].get(svc_name, {})
            p = svc.get("price_per_sec", 0)
            w["btn"].setText(svc.get("display_name", svc_name))
            w["price_lbl"].setText("{} so'm/s".format(p))

    # ── Header ──
    def _update_header(self):
        if self.show_timer_mode and self.is_running:
            mins = self.remaining_sec // 60
            secs = self.remaining_sec % 60
            self.header_label.setText("{:02d}:{:02d}".format(mins, secs))
        else:
            self.header_label.setText("{:,} so'm".format(self.balance).replace(",", " "))

    # ── Tugma stil ──
    def _set_btn_style(self, name, mode):
        w = self.btn_widgets.get(name)
        if not w:
            return
        if mode == "active":
            w["btn"].setStyleSheet(self._active_style())
            if w["price_lbl"]:
                w["price_lbl"].setStyleSheet("color:#38bdf8;font-weight:bold;")
        else:
            if name == "STOP":
                w["btn"].setStyleSheet(self._stop_style())
            else:
                w["btn"].setStyleSheet(self._normal_style())
            if w["price_lbl"]:
                w["price_lbl"].setStyleSheet("color:#64748b;")

    # ── Blink ──
    def _check_blink(self):
        should = (
            self.balance < LOW_BALANCE or
            (self.is_running and self.remaining_sec <= BLINK_WARN)
        )
        if should and not self.blink_timer.isActive():
            self.blink_timer.start()
        elif not should and self.blink_timer.isActive():
            self.blink_timer.stop()
            self._reset_header_color()

    def _blink(self):
        self.blink_state = not self.blink_state
        self.header_label.setStyleSheet("color:{};background:transparent;".format(
            "#ff2222" if self.blink_state else "white"
        ))

    def _reset_header_color(self):
        self.header_label.setStyleSheet("color:#38bdf8;")

    def _flash_low_balance(self):
        self.header_label.setStyleSheet("color:#ff2222;")
        QTimer.singleShot(700, self._reset_header_color)

    def _activate_pin(self, name):
        self.gpio.all_off()
        self.gpio.set_pin(name, 1)

    def _deactivate_pin(self, name):
        self.gpio.set_pin(name, 0)

    def closeEvent(self, event):
        self.gpio.cleanup()
        super().closeEvent(event)


# ─────────────────────────────────────────────
# Aylantiruvchi oyna
# ─────────────────────────────────────────────
class RotatedWindow(QGraphicsView):
    def __init__(self):
        super().__init__()
        sg = QApplication.primaryScreen().geometry()
        sw = sg.width()
        sh = sg.height()

        self.setScene(QGraphicsScene(self))
        self.setStyleSheet("background-color:#0f172a; border:none;")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(0)

        self.ui    = MoykaUI(sh, sw)
        self.proxy = self.scene().addWidget(self.ui)

        cx = sh / 2
        cy = sw / 2
        self.proxy.setTransformOriginPoint(cx, cy)
        self.proxy.setRotation(-90)
        self.proxy.setPos((sw - sh) / 2, (sh - sw) / 2)

    def show_ui(self):
        self.showFullScreen()

    def keyPressEvent(self, event):
        self.ui.keyPressEvent(event)


# ─────────────────────────────────────────────
if __name__ == "__main__":
    app    = QApplication(sys.argv)
    window = RotatedWindow()
    window.show_ui()
    sys.exit(app.exec_())
