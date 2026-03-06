import sys
import json
import os
import gpiod
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QGraphicsView, QGraphicsScene, QDialog,
    QScrollArea, QFrame, QLineEdit, QSizePolicy,
    QStackedWidget
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QRect
from PyQt5.QtGui import QFont, QPainter, QColor, QPen
from datetime import datetime

# ?????????????????????????????????????????????
# Config
# ?????????????????????????????????????????????
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

DEFAULT_CONFIG = {
    "services": {
        "KO'PIK":   {"display_name": "KO'PIK",   "price_per_sec": 200, "duration": 60,  "gpio_out": 227},
        "SUV":      {"display_name": "SUV",       "price_per_sec": 150, "duration": 100, "gpio_out": 75},
        "SHAMPUN":  {"display_name": "SHAMPUN",   "price_per_sec": 250, "duration": 80,  "gpio_out": 79},
        "VOSK":     {"display_name": "VOSK",      "price_per_sec": 350, "duration": 70,  "gpio_out": 78},
        "PENA":     {"display_name": "PENA",      "price_per_sec": 300, "duration": 50,  "gpio_out": 71},
        "OSMOS":    {"display_name": "OSMOS",     "price_per_sec": 200, "duration": 90,  "gpio_out": 233},
        "QURITISH": {"display_name": "QURITISH",  "price_per_sec": 100, "duration": 120, "gpio_out": 74},
    },
    "moyka_name": "MOYKA",
    "admin_pin":  "1234",
    "total_earned": 0,
    "sessions": []
}

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

CHIP_NAME   = "gpiochip1"
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
                    data["services"][svc_name] = dict(svc_default)
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
        print(f"Config xatosi: {e}")


# ?????????????????????????????????????????????
# GPIO
# ?????????????????????????????????????????????
class GPIOController:
    def __init__(self, out_pin_map):
        self.chip = None
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
                    print(f"Out GPIO [{name}={pin}]: {e}")
            for gpio_line in INPUT_GPIO_TO_SERVICE:
                try:
                    line = self.chip.get_line(gpio_line)
                    line.request(consumer="moyka_in", type=gpiod.LINE_REQ_DIR_IN)
                    self.in_lines[gpio_line] = line
                except Exception as e:
                    print(f"In GPIO [line={gpio_line}]: {e}")
            print("GPIO tayyor.")
        except Exception as e:
            print(f"GPIO chip xatosi (sim): {e}")
            self.chip = None

    def set_pin(self, name, value):
        if name in self.out_lines:
            try:
                self.out_lines[name].set_value(int(value))
            except Exception as e:
                print(f"GPIO set [{name}]: {e}")
        else:
            print(f"[SIM] {name} -> {value}")

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


# ?????????????????????????????????????????????
# Xizmat tugmasi ? nom + narx ichida
# ?????????????????????????????????????????????
class ServiceButton(QPushButton):
    """Nomi va narxi tugma ichida, bir xil height."""
    def __init__(self, display_name, price, parent=None):
        super().__init__(parent)
        self._display_name = display_name
        self._price        = price
        self.setFlat(False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._name_ratio  = 0.18
        self._price_ratio = 0.13

    def set_info(self, display_name, price):
        self._display_name = display_name
        self._price        = price
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        h = r.height()
        w = r.width()

        name_fs  = max(12, int(h * self._name_ratio))
        price_fs = max(10, int(h * self._price_ratio))

        # Moyka nomi
        name_font = QFont("Arial", name_fs, QFont.Bold)
        p.setFont(name_font)
        p.setPen(QColor("white"))
        name_rect = QRect(4, 0, w - 8, int(h * 0.62))
        p.drawText(name_rect, Qt.AlignBottom | Qt.AlignHCenter, self._display_name)

        # Narxi
        if self._price > 0:
            price_text = "{} so'm/s".format(self._price)
            price_color = QColor("#94a3b8")
        else:
            price_text = ""
            price_color = QColor("#94a3b8")

        if price_text:
            price_font = QFont("Arial", price_fs)
            p.setFont(price_font)
            p.setPen(price_color)
            price_rect = QRect(4, int(h * 0.62), w - 8, int(h * 0.38))
            p.drawText(price_rect, Qt.AlignTop | Qt.AlignHCenter, price_text)

        p.end()


# ?????????????????????????????????????????????
# PIN Modal ? asosiy ekranda overlay
# ?????????????????????????????????????????????
class PinOverlay(QWidget):
    accepted = pyqtSignal()
    rejected = pyqtSignal()

    def __init__(self, correct_pin, parent=None):
        super().__init__(parent)
        self.correct_pin = correct_pin
        self._pin = ""
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAutoFillBackground(False)
        if parent:
            self.setGeometry(parent.rect())

        # Yarim shaffof qatlam
        self._bg = QWidget(self)
        self._bg.setStyleSheet("background:rgba(0,0,0,180);")
        self._bg.setGeometry(self.rect())

        # Markaziy karta
        self._card = QWidget(self)
        self._card.setStyleSheet(
            "background:#0f172a; border-radius:20px; border:2px solid #334155;"
        )

        card_lay = QVBoxLayout(self._card)
        card_lay.setSpacing(14)
        card_lay.setContentsMargins(28, 28, 28, 28)

        title = QLabel("ADMIN PANEL")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Arial", 20, QFont.Bold))
        title.setStyleSheet("color:#38bdf8; background:transparent; border:none;")
        card_lay.addWidget(title)

        self._pin_lbl = QLabel("")
        self._pin_lbl.setAlignment(Qt.AlignCenter)
        self._pin_lbl.setFont(QFont("Arial", 32, QFont.Bold))
        self._pin_lbl.setStyleSheet(
            "color:white; background:#1e293b; border-radius:12px; padding:10px; border:none;"
        )
        self._pin_lbl.setMinimumHeight(65)
        card_lay.addWidget(self._pin_lbl)

        self._err_lbl = QLabel("")
        self._err_lbl.setAlignment(Qt.AlignCenter)
        self._err_lbl.setFont(QFont("Arial", 13))
        self._err_lbl.setStyleSheet("color:#ef4444; background:transparent; border:none;")
        card_lay.addWidget(self._err_lbl)

        # Raqamli klaviatura (telefon tartibida)
        kbd = QGridLayout()
        kbd.setSpacing(10)
        keys = [
            ["1","2","3"],
            ["4","5","6"],
            ["7","8","9"],
            [u"\u2190","0",u"\u2713"],
        ]
        for ri, row in enumerate(keys):
            for ci, key in enumerate(row):
                b = QPushButton(key)
                b.setFont(QFont("Arial", 22, QFont.Bold))
                b.setMinimumSize(70, 60)
                b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                if key == u"\u2713":
                    b.setStyleSheet("QPushButton{background:#16a34a;color:white;border-radius:12px;border:none;}QPushButton:pressed{background:#15803d;}")
                elif key == u"\u2190":
                    b.setStyleSheet("QPushButton{background:#dc2626;color:white;border-radius:12px;border:none;}QPushButton:pressed{background:#991b1b;}")
                else:
                    b.setStyleSheet("QPushButton{background:#1e293b;color:white;border-radius:12px;border:2px solid #334155;}QPushButton:pressed{background:#2563eb;}")
                b.clicked.connect(lambda _, k=key: self._on_key(k))
                kbd.addWidget(b, ri, ci)
        card_lay.addLayout(kbd)

        cancel_btn = QPushButton("Bekor qilish")
        cancel_btn.setFont(QFont("Arial", 14))
        cancel_btn.setMinimumHeight(46)
        cancel_btn.setStyleSheet(
            "QPushButton{background:#334155;color:white;border-radius:12px;border:none;}"
            "QPushButton:pressed{background:#1e293b;}"
        )
        cancel_btn.clicked.connect(self.rejected.emit)
        card_lay.addWidget(cancel_btn)

        self._reposition()

    def _reposition(self):
        if self.parent():
            self.setGeometry(self.parent().rect())
            self._bg.setGeometry(self.rect())
        pw = self.width()
        ph = self.height()
        cw = min(400, int(pw * 0.9))
        ch = min(560, int(ph * 0.92))
        self._card.setGeometry(
            (pw - cw) // 2,
            (ph - ch) // 2,
            cw, ch
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()

    def _on_key(self, key):
        if key == u"\u2190":
            self._pin = self._pin[:-1]
        elif key == u"\u2713":
            self._check()
            return
        else:
            if len(self._pin) < 8:
                self._pin += key
        self._pin_lbl.setText(u"\u25cf" * len(self._pin))

    def _check(self):
        if self._pin == self.correct_pin:
            self.accepted.emit()
        else:
            self._err_lbl.setText("Noto'g'ri PIN!")
            self._pin = ""
            self._pin_lbl.setText("")
            QTimer.singleShot(1500, lambda: self._err_lbl.setText(""))


# ?????????????????????????????????????????????
# Admin Panel ? to'liq ekran, asosiy stack ichida
# ?????????????????????????????????????????????
class AdminPanel(QWidget):
    config_changed = pyqtSignal(dict)
    close_requested = pyqtSignal()

    def __init__(self, cfg, screen_w, screen_h, parent=None):
        super().__init__(parent)
        self.cfg = json.loads(json.dumps(cfg))
        self._active_svc   = None
        self._active_idx   = 0   # 0=nom, 1=narx
        self._fields_order = []  # [(name_edit, price_edit), ...]
        self._all_edits    = []
        self._active_edit  = None

        sw = screen_w
        sh = screen_h
        fs  = lambda ratio: max(10, int(min(sw, sh) * ratio))

        self.setStyleSheet("background:#0f172a;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ?? Header ??
        header = QWidget()
        header.setStyleSheet("background:#0c1a2e; border-bottom:2px solid #1e3a5f;")
        header.setFixedHeight(int(sh * 0.08))
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(int(sw*0.03), 0, int(sw*0.03), 0)

        title = QLabel("ADMIN PANEL")
        title.setFont(QFont("Arial", fs(0.045), QFont.Bold))
        title.setStyleSheet("color:#38bdf8; background:transparent;")
        h_lay.addWidget(title)
        h_lay.addStretch()

        total = self.cfg.get("total_earned", 0)
        earn_lbl = QLabel("Jami: {:,} so'm".format(total).replace(",", " "))
        earn_lbl.setFont(QFont("Arial", fs(0.032), QFont.Bold))
        earn_lbl.setStyleSheet("color:#4ade80; background:transparent;")
        h_lay.addWidget(earn_lbl)
        h_lay.addSpacing(int(sw * 0.04))

        close_btn = QPushButton("Yopish")
        close_btn.setFont(QFont("Arial", fs(0.028), QFont.Bold))
        close_btn.setMinimumHeight(int(sh * 0.055))
        close_btn.setMinimumWidth(int(sw * 0.18))
        close_btn.setStyleSheet(
            "QPushButton{background:#dc2626;color:white;border-radius:10px;border:none;}"
            "QPushButton:pressed{background:#b91c1c;}"
        )
        close_btn.clicked.connect(self.close_requested.emit)
        h_lay.addWidget(close_btn)
        root.addWidget(header)

        # ?? Asosiy kontent (chap: mahsulotlar | o'ng: hisobot) ??
        body = QHBoxLayout()
        body.setSpacing(0)
        body.setContentsMargins(0, 0, 0, 0)

        # ?? Chap: mahsulotlar (scroll) ??
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:#0f172a;}")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        svc_widget = QWidget()
        svc_widget.setStyleSheet("background:#0f172a;")
        svc_lay = QVBoxLayout(svc_widget)
        svc_lay.setSpacing(int(sh * 0.015))
        svc_lay.setContentsMargins(int(sw*0.025), int(sh*0.02), int(sw*0.015), int(sh*0.02))

        svc_head = QLabel("XIZMATLAR")
        svc_head.setFont(QFont("Arial", fs(0.032), QFont.Bold))
        svc_head.setStyleSheet("color:#94a3b8; background:transparent;")
        svc_lay.addWidget(svc_head)

        hint = QLabel("Qiymatni o'zgartirish uchun to'g'ridan-to'g'ri maydonga bosing")
        hint.setFont(QFont("Arial", fs(0.022)))
        hint.setStyleSheet("color:#475569; background:transparent;")
        hint.setWordWrap(True)
        svc_lay.addWidget(hint)

        self.service_widgets = {}
        for svc_name, svc_data in self.cfg["services"].items():
            row = QHBoxLayout()
            row.setSpacing(int(sw * 0.012))

            # Nom field
            ne = QLineEdit(svc_data.get("display_name", svc_name))
            ne.setFont(QFont("Arial", fs(0.034), QFont.Bold))
            ne.setFixedHeight(int(sh * 0.072))
            ne.setReadOnly(False)
            ne.setStyleSheet(self._field_idle_style())
            ne.setPlaceholderText("Nom")
            ne.mousePressEvent = lambda e, _ne=ne: self._field_clicked(_ne)

            # Narx field
            pe = QLineEdit(str(svc_data["price_per_sec"]))
            pe.setFont(QFont("Arial", fs(0.034)))
            pe.setFixedHeight(int(sh * 0.072))
            pe.setReadOnly(False)
            pe.setStyleSheet(self._field_idle_style("#38bdf8"))
            pe.setPlaceholderText("so'm/s")
            pe.setFixedWidth(int(sw * 0.18))
            pe.mousePressEvent = lambda e, _pe=pe: self._field_clicked(_pe)

            row.addWidget(ne, stretch=3)
            row.addWidget(pe, stretch=0)
            svc_lay.addLayout(row)
            self.service_widgets[svc_name] = {"name_edit": ne, "price_edit": pe}
            self._fields_order.append((ne, pe))
            self._all_edits.extend([ne, pe])

        # Moyka nomi
        svc_lay.addSpacing(int(sh * 0.015))
        moyka_lbl = QLabel("Moyka nomi (balans 0 da ko'rinadi):")
        moyka_lbl.setFont(QFont("Arial", fs(0.028)))
        moyka_lbl.setStyleSheet("color:#94a3b8; background:transparent;")
        svc_lay.addWidget(moyka_lbl)

        moyka_row = QHBoxLayout()
        self.moyka_name_edit = QLineEdit(self.cfg.get("moyka_name", "MOYKA"))
        self.moyka_name_edit.setFont(QFont("Arial", fs(0.034), QFont.Bold))
        self.moyka_name_edit.setFixedHeight(int(sh * 0.072))
        self.moyka_name_edit.setReadOnly(False)
        self.moyka_name_edit.setStyleSheet(self._field_idle_style())
        self.moyka_name_edit.mousePressEvent = lambda e: self._field_clicked(self.moyka_name_edit)
        moyka_row.addWidget(self.moyka_name_edit, stretch=1)
        svc_lay.addLayout(moyka_row)
        self._all_edits.append(self.moyka_name_edit)

        svc_lay.addStretch()

        # Saqlash tugmasi
        save_btn = QPushButton("??  SAQLASH")
        save_btn.setFont(QFont("Arial", fs(0.036), QFont.Bold))
        save_btn.setMinimumHeight(int(sh * 0.08))
        save_btn.setStyleSheet(
            "QPushButton{background:#16a34a;color:white;border-radius:14px;border:none;margin:8px 0;}"
            "QPushButton:pressed{background:#15803d;}"
        )
        save_btn.clicked.connect(self._save_and_close)
        svc_lay.addWidget(save_btn)

        scroll.setWidget(svc_widget)
        body.addWidget(scroll, stretch=5)

        # ?? O'ng: hisobot ??
        rep_widget = QWidget()
        rep_widget.setStyleSheet("background:#0a111e; border-left:2px solid #1e293b;")
        r_lay = QVBoxLayout(rep_widget)
        r_lay.setSpacing(int(sh * 0.012))
        r_lay.setContentsMargins(int(sw*0.02), int(sh*0.025), int(sw*0.025), int(sh*0.02))

        rep_head = QLabel("HISOBOT")
        rep_head.setFont(QFont("Arial", fs(0.032), QFont.Bold))
        rep_head.setStyleSheet("color:#38bdf8; background:transparent;")
        r_lay.addWidget(rep_head)

        # Bugungi daromad hisoblash
        today = datetime.now().strftime("%Y-%m-%d")
        sessions = self.cfg.get("sessions", [])
        today_earned = sum(s.get("earned", 0) for s in sessions if s.get("date", "").startswith(today))
        
        today_lbl = QLabel("Bugun: {:,} so'm".format(today_earned).replace(",", " "))
        today_lbl.setFont(QFont("Arial", fs(0.028), QFont.Bold))
        today_lbl.setStyleSheet("color:#22c55e; background:transparent;")
        r_lay.addWidget(today_lbl)
        
        total_lbl = QLabel("Jami: {:,} so'm".format(self.cfg.get("total_earned", 0)).replace(",", " "))
        total_lbl.setFont(QFont("Arial", fs(0.026)))
        total_lbl.setStyleSheet("color:#4ade80; background:transparent;")
        r_lay.addWidget(total_lbl)
        
        count_lbl = QLabel("Sessiyalar: {}".format(len(sessions)))
        count_lbl.setFont(QFont("Arial", fs(0.024)))
        count_lbl.setStyleSheet("color:#94a3b8; background:transparent;")
        r_lay.addWidget(count_lbl)
        
        r_lay.addSpacing(int(sh * 0.02))
        
        recent_head = QLabel("Oxirgi 10 ta:")
        recent_head.setFont(QFont("Arial", fs(0.022)))
        recent_head.setStyleSheet("color:#64748b; background:transparent;")
        r_lay.addWidget(recent_head)

        if sessions:
            for s in reversed(sessions[-10:]):
                shown = s.get("service_name") or s.get("service", "?")
                sl = QLabel("• {}  {:,} so'm".format(shown, s.get("earned", 0)).replace(",", " "))
                sl.setFont(QFont("Arial", fs(0.02)))
                sl.setStyleSheet("color:#cbd5e1; background:transparent;")
                r_lay.addWidget(sl)
        r_lay.addStretch()
        body.addWidget(rep_widget, stretch=2)

        root.addLayout(body, stretch=1)

        # ?? Virtual klaviatura ??
        kbd_widget = QWidget()
        kbd_widget.setStyleSheet("background:#0c1a2e; border-top:2px solid #1e3a5f;")
        kbd_widget.setFixedHeight(int(sh * 0.38))
        kbd_lay = QVBoxLayout(kbd_widget)
        kbd_lay.setContentsMargins(int(sw*0.02), int(sh*0.01), int(sw*0.02), int(sh*0.01))
        kbd_lay.setSpacing(int(sh * 0.008))

        # Faol field ko'rsatish
        self._active_label = QLabel("Tahrirlash uchun maydonga bosing")
        self._active_label.setAlignment(Qt.AlignCenter)
        self._active_label.setFont(QFont("Arial", fs(0.026)))
        self._active_label.setStyleSheet("color:#64748b; background:transparent;")
        kbd_lay.addWidget(self._active_label)

        self._kbd_grid = QGridLayout()
        self._kbd_grid.setSpacing(int(min(sw, sh) * 0.012))
        self._build_keyboard(self._kbd_grid, fs)
        kbd_lay.addLayout(self._kbd_grid)

        root.addWidget(kbd_widget)

        self._sw = sw
        self._sh = sh
        self._fs = fs

    def _field_idle_style(self, color="white"):
        return (
            "QLineEdit{{background:#1e293b;color:{};border-radius:10px;"
            "border:1px solid #334155;padding:6px 14px;}}"
            "QLineEdit:focus{{border:2px solid #38bdf8;}}"
        ).format(color)

    def _field_active_style(self, color="white"):
        return (
            "QLineEdit{{background:#0c2340;color:{};border-radius:10px;"
            "border:2px solid #38bdf8;padding:6px 14px;}}"
        ).format(color)

    def _build_keyboard(self, grid, fs):
        # QWERTY layout (5 qator)
        rows = [
            ["Q","W","E","R","T","Y","U","I","O","P"],
            ["A","S","D","F","G","H","J","K","L"],
            ["Z","X","C","V","B","N","M","'","-"],
            ["1","2","3","4","5","6","7","8","9","0"],
            ["Bo'sh",u"\u2190","KEYINGI",u"\u2713"],
        ]
        btn_h = int(self._sh * 0.062) if hasattr(self, "_sh") else 50
        fsize = fs(0.026)
        for ri, row in enumerate(rows):
            ci = 0
            for key in row:
                b = QPushButton(key)
                b.setFont(QFont("Arial", fsize, QFont.Bold if key in (u"\u2190", u"\u2713", "KEYINGI") else QFont.Normal))
                b.setFixedHeight(btn_h)
                b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                span = 1
                if key == "Bo'sh":
                    span = 2
                    b.setStyleSheet("QPushButton{background:#334155;color:white;border-radius:8px;border:none;}QPushButton:pressed{background:#1e293b;}")
                elif key == "KEYINGI":
                    span = 2
                    b.setStyleSheet("QPushButton{background:#0369a1;color:white;border-radius:8px;border:none;}QPushButton:pressed{background:#075985;}")
                elif key == u"\u2713":
                    b.setStyleSheet("QPushButton{background:#16a34a;color:white;border-radius:8px;border:none;}QPushButton:pressed{background:#15803d;}")
                elif key == u"\u2190":
                    b.setStyleSheet("QPushButton{background:#dc2626;color:white;border-radius:8px;border:none;}QPushButton:pressed{background:#991b1b;}")
                else:
                    b.setStyleSheet("QPushButton{background:#1e293b;color:white;border-radius:8px;border:1px solid #334155;}QPushButton:pressed{background:#2563eb;}")
                b.clicked.connect(lambda _, k=key: self._kbd_input(k))
                grid.addWidget(b, ri, ci, 1, span)
                ci += span

    def _field_clicked(self, field):
        # Barcha fieldlarni idle qilish
        for ne, pe in self._fields_order:
            ne.setStyleSheet(self._field_idle_style())
            if pe:
                pe.setStyleSheet(self._field_idle_style("#38bdf8"))
        self.moyka_name_edit.setStyleSheet(self._field_idle_style())
        
        # Bosilgan fieldni active qilish
        if field == self.moyka_name_edit:
            field.setStyleSheet(self._field_active_style())
            self._active_edit = field
            self._active_label.setText("✏  Moyka nomi tahrirlanmoqda")
            self._active_label.setStyleSheet("color:#38bdf8; background:transparent;")
        else:
            # Qaysi xizmatga tegishli ekanini aniqlash
            is_price = False
            for svc_name, w in self.service_widgets.items():
                if w["name_edit"] == field:
                    field.setStyleSheet(self._field_active_style())
                    self._active_edit = field
                    self._active_label.setText("✏  {} nomi tahrirlanmoqda".format(svc_name))
                    self._active_label.setStyleSheet("color:#38bdf8; background:transparent;")
                    break
                elif w["price_edit"] == field:
                    field.setStyleSheet(self._field_active_style("#38bdf8"))
                    self._active_edit = field
                    is_price = True
                    self._active_label.setText("✏  {} narxi tahrirlanmoqda (so'm/s)".format(svc_name))
                    self._active_label.setStyleSheet("color:#38bdf8; background:transparent;")
                    break
        field.setFocus()
        # Default mousePressEvent ni chaqirish
        QLineEdit.mousePressEvent(field, type('Event', (), {'button': lambda: Qt.LeftButton})())

    def _kbd_input(self, key):
        if not hasattr(self, "_active_edit") or self._active_edit is None:
            return

        edit = self._active_edit
        txt = edit.text()
        
        # Raqamli maydon yoki matn maydon?
        is_num = False
        for svc_name, w in self.service_widgets.items():
            if w["price_edit"] == edit:
                is_num = True
                break

        if key == u"\u2190":
            edit.setText(txt[:-1])
        elif key == u"\u2713":
            # Saqlash va yopish
            self._save_and_close()
        elif key == "KEYINGI":
            # Keyingi fieldga o'tish
            all_fields = []
            for ne, pe in self._fields_order:
                all_fields.append(ne)
                all_fields.append(pe)
            all_fields.append(self.moyka_name_edit)
            
            try:
                idx = all_fields.index(edit)
                next_idx = (idx + 1) % len(all_fields)
                self._field_clicked(all_fields[next_idx])
            except ValueError:
                pass
        elif key == "Bo'sh":
            if not is_num:
                if len(txt) < 20:
                    edit.setText(txt + " ")
        else:
            if is_num:
                if key.isdigit() and len(txt) < 6:
                    edit.setText(txt + key)
            else:
                if len(txt) < 20:
                    edit.setText(txt + key)

    def _save_and_close(self):
        # Servislar
        for svc, w in self.service_widgets.items():
            d_name = w["name_edit"].text().strip()
            p_txt  = w["price_edit"].text().strip()
            if d_name:
                self.cfg["services"][svc]["display_name"] = d_name
            try:
                p = int(p_txt)
                self.cfg["services"][svc]["price_per_sec"] = max(1, p)
            except ValueError:
                pass
        # Moyka nomi
        mn = self.moyka_name_edit.text().strip()
        if mn:
            self.cfg["moyka_name"] = mn
        self.config_changed.emit(self.cfg)
        self.close_requested.emit()


# ?????????????????????????????????????????????
# Asosiy UI
# ?????????????????????????????????????????????
class MoykaUI(QWidget):
    def __init__(self, width, height):
        super().__init__()
        self.w = width
        self.h = height
        self.setFixedSize(width, height)

        self.cfg = load_config()
        out_pins = {n: d["gpio_out"] for n, d in self.cfg["services"].items()}
        self.gpio = GPIOController(out_pins)

        self.balance          = 0
        self.remaining_sec    = 0
        self.active_service   = None
        self.is_running       = False
        self.blink_state      = False
        self.show_timer_mode  = False
        self.session_earned   = 0

        self._pause_hold_count = 0
        self._pause_hold_timer = QTimer(self)
        self._pause_hold_timer.setInterval(1000)
        self._pause_hold_timer.timeout.connect(self._pause_hold_tick)
        self._stop_hold_source = None
        self._stop_gpio_hold_ms = 0

        self.service_timer = QTimer(self)
        self.service_timer.setInterval(1000)
        self.service_timer.timeout.connect(self._tick)

        self.blink_timer = QTimer(self)
        self.blink_timer.setInterval(400)
        self.blink_timer.timeout.connect(self._blink)

        self.input_timer = QTimer(self)
        self.input_timer.setInterval(100)
        self.input_timer.timeout.connect(self._poll_inputs)
        self._prev_input = {gl: 0 for gl in INPUT_GPIO_TO_SERVICE}
        self.input_timer.start()

        self.setStyleSheet("QWidget{background-color:#0f172a;} QLabel{color:white;}")

        # ?? Stack: 0=asosiy, 1=admin ??
        self._stack = QStackedWidget(self)
        self._stack.setGeometry(0, 0, width, height)

        # ?? Asosiy sahifa ??
        self._main_page = QWidget()
        self._main_page.setStyleSheet("background:#0f172a;")
        ml = QVBoxLayout(self._main_page)
        ml.setSpacing(0)
        ml.setContentsMargins(int(width*0.05), int(height*0.04),
                               int(width*0.05), int(height*0.03))

        self.header_label = QLabel(self.cfg.get("moyka_name", "MOYKA"))
        self.header_label.setAlignment(Qt.AlignCenter)
        self.header_label.setFont(QFont("Arial", int(height * 0.059), QFont.Bold))
        self.header_label.setStyleSheet("color:#38bdf8;")
        ml.addWidget(self.header_label)

        self.service_label = QLabel("")
        self.service_label.setAlignment(Qt.AlignCenter)
        self.service_label.setFont(QFont("Arial", int(height * 0.022)))
        self.service_label.setStyleSheet("color:#94a3b8;")
        ml.addWidget(self.service_label)
        ml.addSpacing(int(height * 0.015))

        self.grid = QGridLayout()
        self.grid.setSpacing(int(min(width, height) * 0.02))

        svc_names = list(self.cfg["services"].keys())
        all_names = svc_names + ["STOP"]
        positions = [(i, j) for i in range(4) for j in range(2)]
        btn_h     = int(height * 0.11)

        self.btn_widgets = {}
        for pos, name in zip(positions, all_names):
            if name == "STOP":
                btn = QPushButton("STOP")
                btn.setFont(QFont("Arial", int(height * 0.036), QFont.Bold))
                btn.setMinimumHeight(btn_h)
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                btn.setStyleSheet(self._stop_style())
                btn.pressed.connect(self._on_stop_pressed)
                btn.released.connect(self._on_stop_released)
                self.grid.addWidget(btn, *pos)
                self.btn_widgets["STOP"] = {"btn": btn, "svc_btn": None}
            else:
                svc_data = self.cfg["services"][name]
                p = svc_data["price_per_sec"]
                dn = svc_data.get("display_name", name)
                svc_btn = ServiceButton(dn, p)
                svc_btn.setMinimumHeight(btn_h)
                svc_btn.setStyleSheet(self._normal_style())
                svc_btn.clicked.connect(lambda _, n=name: self.button_clicked(n))
                self.grid.addWidget(svc_btn, *pos)
                self.btn_widgets[name] = {"btn": svc_btn, "svc_btn": svc_btn}

        ml.addLayout(self.grid, stretch=3)
        self._stack.addWidget(self._main_page)

        # ?? Admin sahifasi (keyinchalik qo'shiladi) ??
        self._admin_panel = None
        self._pin_overlay = None

    def _build_admin_page(self):
        if self._admin_panel:
            self._stack.removeWidget(self._admin_panel)
            self._admin_panel.deleteLater()
        self._admin_panel = AdminPanel(self.cfg, self.w, self.h, self)
        self._admin_panel.config_changed.connect(self._apply_config)
        self._admin_panel.close_requested.connect(self._close_admin)
        self._stack.addWidget(self._admin_panel)

    # ?? Stil ??
    def _normal_style(self):
        return (
            "QPushButton{background:#1e293b;color:white;border-radius:18px;border:2px solid #334155;}"
            "QPushButton:pressed{background:#1d4ed8;}"
        )

    def _active_style(self):
        return "QPushButton{background:#0c4a6e;color:#7dd3fc;border-radius:18px;border:3px solid #38bdf8;}"

    def _stop_style(self):
        return (
            "QPushButton{background:#7f1d1d;color:white;border-radius:18px;border:2px solid #ef4444;}"
            "QPushButton:pressed{background:#450a0a;}"
        )

    # ?? Enter = 5000 so'm ??
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.balance += 5000
            self._update_header()
            self._check_blink()

    # ?? GPIO polling ??
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
            elif val == 1 and prev == 0:
                self.button_clicked(svc_name)
            self._prev_input[gpio_line] = val

    # ?? Tugma ??
    def button_clicked(self, name):
        if name not in self.cfg["services"]:
            return
        svc_data = self.cfg["services"][name]
        cost     = svc_data["price_per_sec"]
        if self.balance < cost:
            self._flash_low_balance()
            return
        if self.is_running and self.active_service:
            self._deactivate_pin(self.active_service)
            self._set_btn_style(self.active_service, "normal")
        # Yangi xizmat boshlanganda STOP timer to'xtatish
        self._pause_hold_timer.stop()
        self._pause_hold_count = 0
        self._stop_hold_source = None
        
        self.active_service  = name
        self.remaining_sec   = self.balance // cost
        self.is_running      = True
        self.show_timer_mode = True
        self.session_earned  = 0
        self._activate_pin(name)
        self._set_btn_style(name, "active")
        dn = svc_data.get("display_name", name)
        self.service_label.setText("{}  {}so'm/s".format(dn, cost))
        self.service_timer.start()
        self._update_header()
        self._check_blink()

    def _on_stop_pressed(self, source="touch"):
        self._stop_hold_source = source
        self._pause_hold_count = 0
        self._pause_hold_timer.start()
        # Faqat service ishlayotgan bo'lsa to'xtatish
        if self.is_running:
            self._stop_service()

    def _on_stop_released(self, source="touch"):
        # Har qanday released signal kelsa timer to'xtatish (xavfsizlik uchun)
        self._pause_hold_timer.stop()
        self._pause_hold_count = 0
        self._stop_hold_source = None

    def _tick(self):
        if not self.is_running:
            return
        cost = self.cfg["services"][self.active_service]["price_per_sec"]
        charge = min(cost, self.balance)
        self.balance -= charge
        self.session_earned += charge
        self.remaining_sec  -= 1
        if self.balance <= 0:
            self._stop_service()
            return
        self._update_header()
        self._check_blink()

    def _pause_hold_tick(self):
        self._pause_hold_count += 1
        if self._pause_hold_count >= 5:
            self._pause_hold_timer.stop()
            # Faqat tugma hali ushlab turilgan va service to'xtagan bo'lsa admin ochish
            if self._stop_hold_source is not None and not self.is_running:
                self._show_pin_overlay()
                self._stop_hold_source = None
                self._pause_hold_count = 0

    def _stop_service(self):
        self.is_running      = False
        self.show_timer_mode = False
        self.service_timer.stop()
        self.blink_timer.stop()
        self.blink_state = False
        if self.active_service and self.session_earned > 0:
            dn = self.cfg["services"].get(self.active_service, {}).get("display_name", self.active_service)
            self.cfg["total_earned"] = self.cfg.get("total_earned", 0) + self.session_earned
            self.cfg.setdefault("sessions", []).append({
                "service": self.active_service,
                "service_name": dn,
                "earned": self.session_earned,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

    # ?? PIN overlay ??
    def _show_pin_overlay(self):
        if self._pin_overlay:
            self._pin_overlay.deleteLater()
        self._pin_overlay = PinOverlay(self.cfg.get("admin_pin", "1234"), self._main_page)
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

    def _open_admin_panel(self):
        self._close_pin_overlay()
        self._build_admin_page()
        self._stack.setCurrentIndex(1)

    def _close_admin(self):
        self._stack.setCurrentIndex(0)

    def _apply_config(self, new_cfg):
        self.cfg = new_cfg
        save_config(self.cfg)
        for svc_name, w in self.btn_widgets.items():
            if svc_name == "STOP":
                continue
            svc = self.cfg["services"].get(svc_name, {})
            p  = svc.get("price_per_sec", 0)
            dn = svc.get("display_name", svc_name)
            sb = w.get("svc_btn")
            if sb:
                sb.set_info(dn, p)
        # Header nomi
        if not self.is_running and self.balance == 0:
            self.header_label.setText(self.cfg.get("moyka_name", "MOYKA"))

    def _update_header(self):
        if self.show_timer_mode and self.is_running:
            mins = self.remaining_sec // 60
            secs = self.remaining_sec % 60
            self.header_label.setText("{:02d}:{:02d}".format(mins, secs))
        elif self.balance == 0:
            self.header_label.setText(self.cfg.get("moyka_name", "MOYKA"))
        else:
            self.header_label.setText("{:,} so'm".format(self.balance).replace(",", " "))

    def _set_btn_style(self, name, mode):
        w = self.btn_widgets.get(name)
        if not w:
            return
        btn = w["btn"]
        sb  = w.get("svc_btn")
        if mode == "active":
            btn.setStyleSheet(self._active_style())
            if sb:
                sb._name_ratio  = 0.16
                sb._price_ratio = 0.11
                sb.update()
        else:
            if name == "STOP":
                btn.setStyleSheet(self._stop_style())
            else:
                btn.setStyleSheet(self._normal_style())
                if sb:
                    sb._name_ratio  = 0.18
                    sb._price_ratio = 0.13
                    sb.update()

    def _check_blink(self):
        should = self.balance < LOW_BALANCE or (self.is_running and self.remaining_sec <= BLINK_WARN)
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


# ?????????????????????????????????????????????
# Rotated window
# ?????????????????????????????????????????????
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


if __name__ == "__main__":
    app    = QApplication(sys.argv)
    window = RotatedWindow()
    window.show_ui()
    sys.exit(app.exec_())
