import json
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, QRect, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QScrollArea,
    QLineEdit,
    QSizePolicy,
)

from app.settings import app_font


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

        self._bg = QWidget(self)
        self._bg.setStyleSheet("background:rgba(0,0,0,180);")
        self._bg.setGeometry(self.rect())

        self._card = QWidget(self)
        self._card.setStyleSheet("background:#0f172a; border-radius:20px; border:2px solid #334155;")

        card_lay = QVBoxLayout(self._card)
        card_lay.setSpacing(14)
        card_lay.setContentsMargins(28, 28, 28, 28)

        title = QLabel("ADMIN PANEL")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(app_font(20, bold=True))
        title.setStyleSheet("color:#38bdf8; background:transparent; border:none;")
        card_lay.addWidget(title)

        self._pin_lbl = QLabel("")
        self._pin_lbl.setAlignment(Qt.AlignCenter)
        self._pin_lbl.setFont(app_font(32, bold=True))
        self._pin_lbl.setStyleSheet("color:white; background:#1e293b; border-radius:12px; padding:10px; border:none;")
        self._pin_lbl.setMinimumHeight(65)
        card_lay.addWidget(self._pin_lbl)

        self._err_lbl = QLabel("")
        self._err_lbl.setAlignment(Qt.AlignCenter)
        self._err_lbl.setFont(app_font(13))
        self._err_lbl.setStyleSheet("color:#ef4444; background:transparent; border:none;")
        card_lay.addWidget(self._err_lbl)

        kbd = QGridLayout()
        kbd.setSpacing(10)
        keys = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["\u2190", "0", "\u2713"]]
        for ri, row in enumerate(keys):
            for ci, key in enumerate(row):
                b = QPushButton(key)
                b.setFont(app_font(22, bold=True))
                b.setMinimumSize(70, 60)
                b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                if key == "\u2713":
                    b.setStyleSheet("QPushButton{background:#16a34a;color:white;border-radius:12px;border:none;}QPushButton:pressed{background:#15803d;}")
                elif key == "\u2190":
                    b.setStyleSheet("QPushButton{background:#dc2626;color:white;border-radius:12px;border:none;}QPushButton:pressed{background:#991b1b;}")
                else:
                    b.setStyleSheet("QPushButton{background:#1e293b;color:white;border-radius:12px;border:2px solid #334155;}QPushButton:pressed{background:#2563eb;}")
                b.clicked.connect(lambda _, k=key: self._on_key(k))
                kbd.addWidget(b, ri, ci)
        card_lay.addLayout(kbd)

        cancel_btn = QPushButton("Bekor qilish")
        cancel_btn.setFont(app_font(14))
        cancel_btn.setMinimumHeight(46)
        cancel_btn.setStyleSheet("QPushButton{background:#334155;color:white;border-radius:12px;border:none;}QPushButton:pressed{background:#1e293b;}")
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
        self._card.setGeometry((pw - cw) // 2, (ph - ch) // 2, cw, ch)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()

    def _on_key(self, key):
        if key == "\u2190":
            self._pin = self._pin[:-1]
        elif key == "\u2713":
            self._check()
            return
        else:
            if len(self._pin) < 8:
                self._pin += key
        self._pin_lbl.setText("\u25cf" * len(self._pin))

    def _check(self):
        if self._pin == self.correct_pin:
            self.accepted.emit()
        else:
            self._err_lbl.setText("Noto'g'ri PIN!")
            self._pin = ""
            self._pin_lbl.setText("")
            QTimer.singleShot(1500, lambda: self._err_lbl.setText(""))


class AdminPanel(QWidget):
    config_changed = pyqtSignal(dict)
    close_requested = pyqtSignal()

    def __init__(self, cfg, screen_w, screen_h, parent=None):
        super().__init__(parent)
        self.cfg = json.loads(json.dumps(cfg))
        self._fields_order = []
        self._all_edits = []
        self._active_edit = None

        sw = screen_w
        sh = screen_h
        fs = lambda ratio: max(10, int(min(sw, sh) * ratio))

        self.setStyleSheet("background:#0f172a;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setStyleSheet("background:#0c1a2e; border-bottom:2px solid #1e3a5f;")
        header.setFixedHeight(int(sh * 0.08))
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(int(sw * 0.03), 0, int(sw * 0.03), 0)

        title = QLabel("ADMIN PANEL")
        title.setFont(app_font(fs(0.045), bold=True))
        title.setStyleSheet("color:#38bdf8; background:transparent;")
        h_lay.addWidget(title)
        h_lay.addStretch()

        total = self.cfg.get("total_earned", 0)
        earn_lbl = QLabel("Jami: {:,} so'm".format(total).replace(",", " "))
        earn_lbl.setFont(app_font(fs(0.032), bold=True))
        earn_lbl.setStyleSheet("color:#4ade80; background:transparent;")
        h_lay.addWidget(earn_lbl)
        h_lay.addSpacing(int(sw * 0.04))

        close_btn = QPushButton("Yopish")
        close_btn.setFont(app_font(fs(0.028), bold=True))
        close_btn.setMinimumHeight(int(sh * 0.055))
        close_btn.setMinimumWidth(int(sw * 0.18))
        close_btn.setStyleSheet("QPushButton{background:#dc2626;color:white;border-radius:10px;border:none;}QPushButton:pressed{background:#b91c1c;}")
        close_btn.clicked.connect(self.close_requested.emit)
        h_lay.addWidget(close_btn)
        root.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(0)
        body.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:#0f172a;}")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        svc_widget = QWidget()
        svc_widget.setStyleSheet("background:#0f172a;")
        svc_lay = QVBoxLayout(svc_widget)
        svc_lay.setSpacing(int(sh * 0.015))
        svc_lay.setContentsMargins(int(sw * 0.025), int(sh * 0.02), int(sw * 0.015), int(sh * 0.02))

        svc_head = QLabel("XIZMATLAR")
        svc_head.setFont(app_font(fs(0.032), bold=True))
        svc_head.setStyleSheet("color:#94a3b8; background:transparent;")
        svc_lay.addWidget(svc_head)

        hint = QLabel("Qiymatni o'zgartirish uchun to'g'ridan-to'g'ri maydonga bosing")
        hint.setFont(app_font(fs(0.022)))
        hint.setStyleSheet("color:#475569; background:transparent;")
        hint.setWordWrap(True)
        svc_lay.addWidget(hint)

        self.service_widgets = {}
        for svc_name, svc_data in self.cfg["services"].items():
            row = QHBoxLayout()
            row.setSpacing(int(sw * 0.012))

            ne = QLineEdit(svc_data.get("display_name", svc_name))
            ne.setFont(app_font(fs(0.034), bold=True))
            ne.setFixedHeight(int(sh * 0.072))
            ne.setStyleSheet(self._field_idle_style())
            ne.setPlaceholderText("Nom")
            ne.mousePressEvent = lambda e, _ne=ne: self._field_clicked(_ne)

            pe = QLineEdit(str(svc_data["price_per_sec"]))
            pe.setFont(app_font(fs(0.034)))
            pe.setFixedHeight(int(sh * 0.072))
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

        svc_lay.addSpacing(int(sh * 0.015))
        moyka_lbl = QLabel("Moyka nomi (balans 0 da ko'rinadi):")
        moyka_lbl.setFont(app_font(fs(0.028)))
        moyka_lbl.setStyleSheet("color:#94a3b8; background:transparent;")
        svc_lay.addWidget(moyka_lbl)

        moyka_row = QHBoxLayout()
        self.moyka_name_edit = QLineEdit(self.cfg.get("moyka_name", "MOYKA"))
        self.moyka_name_edit.setFont(app_font(fs(0.034), bold=True))
        self.moyka_name_edit.setFixedHeight(int(sh * 0.072))
        self.moyka_name_edit.setStyleSheet(self._field_idle_style())
        self.moyka_name_edit.mousePressEvent = lambda e: self._field_clicked(self.moyka_name_edit)
        moyka_row.addWidget(self.moyka_name_edit, stretch=1)
        svc_lay.addLayout(moyka_row)
        self._all_edits.append(self.moyka_name_edit)

        svc_lay.addStretch()

        save_btn = QPushButton("SAQLASH")
        save_btn.setFont(app_font(fs(0.036), bold=True))
        save_btn.setMinimumHeight(int(sh * 0.08))
        save_btn.setStyleSheet("QPushButton{background:#16a34a;color:white;border-radius:14px;border:none;margin:8px 0;}QPushButton:pressed{background:#15803d;}")
        save_btn.clicked.connect(self._save_and_close)
        svc_lay.addWidget(save_btn)

        scroll.setWidget(svc_widget)
        body.addWidget(scroll, stretch=5)

        rep_widget = QWidget()
        rep_widget.setStyleSheet("background:#0a111e; border-left:2px solid #1e293b;")
        r_lay = QVBoxLayout(rep_widget)
        r_lay.setSpacing(int(sh * 0.012))
        r_lay.setContentsMargins(int(sw * 0.02), int(sh * 0.025), int(sw * 0.025), int(sh * 0.02))

        rep_head = QLabel("HISOBOT")
        rep_head.setFont(app_font(fs(0.032), bold=True))
        rep_head.setStyleSheet("color:#38bdf8; background:transparent;")
        r_lay.addWidget(rep_head)

        today = datetime.now().strftime("%Y-%m-%d")
        sessions = self.cfg.get("sessions", [])
        today_earned = sum(s.get("earned", 0) for s in sessions if s.get("date", "").startswith(today))

        today_lbl = QLabel("Bugun: {:,} so'm".format(today_earned).replace(",", " "))
        today_lbl.setFont(app_font(fs(0.028), bold=True))
        today_lbl.setStyleSheet("color:#22c55e; background:transparent;")
        r_lay.addWidget(today_lbl)

        total_lbl = QLabel("Jami: {:,} so'm".format(self.cfg.get("total_earned", 0)).replace(",", " "))
        total_lbl.setFont(app_font(fs(0.026)))
        total_lbl.setStyleSheet("color:#4ade80; background:transparent;")
        r_lay.addWidget(total_lbl)

        count_lbl = QLabel("Sessiyalar: {}".format(len(sessions)))
        count_lbl.setFont(app_font(fs(0.024)))
        count_lbl.setStyleSheet("color:#94a3b8; background:transparent;")
        r_lay.addWidget(count_lbl)

        r_lay.addSpacing(int(sh * 0.02))

        recent_head = QLabel("Oxirgi 10 ta:")
        recent_head.setFont(app_font(fs(0.022)))
        recent_head.setStyleSheet("color:#64748b; background:transparent;")
        r_lay.addWidget(recent_head)

        if sessions:
            for s in reversed(sessions[-10:]):
                shown = s.get("service_name") or s.get("service", "?")
                sl = QLabel("- {}  {:,} so'm".format(shown, s.get("earned", 0)).replace(",", " "))
                sl.setFont(app_font(fs(0.02)))
                sl.setStyleSheet("color:#cbd5e1; background:transparent;")
                r_lay.addWidget(sl)
        r_lay.addStretch()
        body.addWidget(rep_widget, stretch=2)

        root.addLayout(body, stretch=1)

        kbd_widget = QWidget()
        kbd_widget.setStyleSheet("background:#0c1a2e; border-top:2px solid #1e3a5f;")
        kbd_widget.setFixedHeight(int(sh * 0.38))
        kbd_lay = QVBoxLayout(kbd_widget)
        kbd_lay.setContentsMargins(int(sw * 0.02), int(sh * 0.01), int(sw * 0.02), int(sh * 0.01))
        kbd_lay.setSpacing(int(sh * 0.008))

        self._active_label = QLabel("Tahrirlash uchun maydonga bosing")
        self._active_label.setAlignment(Qt.AlignCenter)
        self._active_label.setFont(app_font(fs(0.026)))
        self._active_label.setStyleSheet("color:#64748b; background:transparent;")
        kbd_lay.addWidget(self._active_label)

        self._kbd_grid = QGridLayout()
        self._kbd_grid.setSpacing(int(min(sw, sh) * 0.012))
        self._build_keyboard(self._kbd_grid, fs)
        kbd_lay.addLayout(self._kbd_grid)

        root.addWidget(kbd_widget)

        self._sh = sh

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
        rows = [
            ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
            ["A", "S", "D", "F", "G", "H", "J", "K", "L"],
            ["Z", "X", "C", "V", "B", "N", "M", "'", "-"],
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
            ["Bo'sh", "\u2190", "KEYINGI", "\u2713"],
        ]
        btn_h = int(self._sh * 0.062)
        fsize = fs(0.026)
        for ri, row in enumerate(rows):
            ci = 0
            for key in row:
                b = QPushButton(key)
                b.setFont(app_font(fsize, bold=key in ("\u2190", "\u2713", "KEYINGI")))
                b.setFixedHeight(btn_h)
                b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                span = 1
                if key == "Bo'sh":
                    span = 2
                    b.setStyleSheet("QPushButton{background:#334155;color:white;border-radius:8px;border:none;}QPushButton:pressed{background:#1e293b;}")
                elif key == "KEYINGI":
                    span = 2
                    b.setStyleSheet("QPushButton{background:#0369a1;color:white;border-radius:8px;border:none;}QPushButton:pressed{background:#075985;}")
                elif key == "\u2713":
                    b.setStyleSheet("QPushButton{background:#16a34a;color:white;border-radius:8px;border:none;}QPushButton:pressed{background:#15803d;}")
                elif key == "\u2190":
                    b.setStyleSheet("QPushButton{background:#dc2626;color:white;border-radius:8px;border:none;}QPushButton:pressed{background:#991b1b;}")
                else:
                    b.setStyleSheet("QPushButton{background:#1e293b;color:white;border-radius:8px;border:1px solid #334155;}QPushButton:pressed{background:#2563eb;}")
                b.clicked.connect(lambda _, k=key: self._kbd_input(k))
                grid.addWidget(b, ri, ci, 1, span)
                ci += span

    def _field_clicked(self, field):
        for ne, pe in self._fields_order:
            ne.setStyleSheet(self._field_idle_style())
            pe.setStyleSheet(self._field_idle_style("#38bdf8"))
        self.moyka_name_edit.setStyleSheet(self._field_idle_style())

        if field == self.moyka_name_edit:
            field.setStyleSheet(self._field_active_style())
            self._active_edit = field
            self._active_label.setText("Moyka nomi tahrirlanmoqda")
            self._active_label.setStyleSheet("color:#38bdf8; background:transparent;")
        else:
            for svc_name, w in self.service_widgets.items():
                if w["name_edit"] == field:
                    field.setStyleSheet(self._field_active_style())
                    self._active_edit = field
                    self._active_label.setText("{} nomi tahrirlanmoqda".format(svc_name))
                    self._active_label.setStyleSheet("color:#38bdf8; background:transparent;")
                    break
                if w["price_edit"] == field:
                    field.setStyleSheet(self._field_active_style("#38bdf8"))
                    self._active_edit = field
                    self._active_label.setText("{} narxi tahrirlanmoqda (so'm/s)".format(svc_name))
                    self._active_label.setStyleSheet("color:#38bdf8; background:transparent;")
                    break
        field.setFocus()

    def _kbd_input(self, key):
        if self._active_edit is None:
            return

        edit = self._active_edit
        txt = edit.text()

        is_num = any(w["price_edit"] == edit for w in self.service_widgets.values())

        if key == "\u2190":
            edit.setText(txt[:-1])
        elif key == "\u2713":
            self._save_and_close()
        elif key == "KEYINGI":
            all_fields = []
            for ne, pe in self._fields_order:
                all_fields.extend([ne, pe])
            all_fields.append(self.moyka_name_edit)
            if edit in all_fields:
                idx = all_fields.index(edit)
                self._field_clicked(all_fields[(idx + 1) % len(all_fields)])
        elif key == "Bo'sh":
            if not is_num and len(txt) < 20:
                edit.setText(txt + " ")
        else:
            if is_num:
                if key.isdigit() and len(txt) < 6:
                    edit.setText(txt + key)
            else:
                if len(txt) < 20:
                    edit.setText(txt + key)

    def _save_and_close(self):
        for svc, w in self.service_widgets.items():
            d_name = w["name_edit"].text().strip()
            p_txt = w["price_edit"].text().strip()
            if d_name:
                self.cfg["services"][svc]["display_name"] = d_name
            try:
                p = int(p_txt)
                self.cfg["services"][svc]["price_per_sec"] = max(1, p)
            except ValueError:
                pass

        mn = self.moyka_name_edit.text().strip()
        if mn:
            self.cfg["moyka_name"] = mn

        self.config_changed.emit(self.cfg)
        self.close_requested.emit()
