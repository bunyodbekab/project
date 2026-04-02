"""Admin UI dialogs."""

import math
from functools import partial

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QIcon, QIntValidator
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app.settings import DEFAULT_CONFIG, app_font
from .common import THEME_COLORS, _format_money, _icon_path, _to_int


class PinDialog(QDialog):
    def __init__(self, allowed_pins, parent=None):
        super().__init__(parent)
        self.allowed_pins = [str(p) for p in allowed_pins if str(p)]
        self._pin_value = ""

        self.setModal(True)
        self.setWindowTitle("Admin PIN")
        self.setFont(app_font(12, bold=True))
        self.setStyleSheet(
            """
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0c183b, stop:1 #0f1f4a);
                color: #f8fafc;
            }
            QLabel {
                color: #f8fafc;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4c88ff, stop:1 #3a6fd4);
                color: #f8fafc;
                border: 1px solid rgba(76, 136, 255, 0.5);
                border-radius: 10px;
                font-size: 20px;
                font-weight: 800;
                padding: 10px;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3a6fd4, stop:1 #2d5cb3);
            }
            QPushButton#SubmitBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4c88ff, stop:1 #3a6fd4);
            }
            QPushButton#ClearBtn {
                background: rgba(76, 136, 255, 0.08);
                border-color: rgba(76, 136, 255, 0.3);
                color: #a8d5ff;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 26, 26, 26)
        root.setSpacing(14)

        title = QLabel("PIN kiriting")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 30px; font-weight: 800;")
        root.addWidget(title)

        self.pin_dots = QLabel("o o o o o o")
        self.pin_dots.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_dots.setStyleSheet("font-size: 26px; font-weight: 800;")
        root.addWidget(self.pin_dots)

        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setStyleSheet("color: #ff9a9a; font-size: 18px; min-height: 24px;")
        root.addWidget(self.error_label)

        keypad = QGridLayout()
        keypad.setSpacing(8)
        digits = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
        for idx, digit in enumerate(digits):
            row = idx // 3
            col = idx % 3
            btn = QPushButton(digit)
            btn.clicked.connect(partial(self._add_digit, digit))
            keypad.addWidget(btn, row, col)

        zero_btn = QPushButton("0")
        zero_btn.clicked.connect(partial(self._add_digit, "0"))
        keypad.addWidget(zero_btn, 3, 1)

        root.addLayout(keypad)

        actions = QHBoxLayout()
        actions.setSpacing(10)

        cancel_btn = QPushButton("Bekor qilish")
        cancel_btn.clicked.connect(self.reject)

        clear_btn = QPushButton("Tozalash")
        clear_btn.setObjectName("ClearBtn")
        clear_btn.clicked.connect(self._clear)

        submit_btn = QPushButton("Kirish")
        submit_btn.setObjectName("SubmitBtn")
        submit_btn.clicked.connect(self._submit)

        actions.addWidget(cancel_btn)
        actions.addWidget(clear_btn)
        actions.addWidget(submit_btn)
        root.addLayout(actions)

    def _add_digit(self, digit):
        if len(self._pin_value) >= 6:
            return
        self._pin_value += str(digit)
        self.error_label.setText("")
        self._refresh_dots()

    def _clear(self):
        self._pin_value = ""
        self.error_label.setText("")
        self._refresh_dots()

    def _refresh_dots(self):
        dots = []
        for idx in range(6):
            dots.append("O" if idx < len(self._pin_value) else "o")
        self.pin_dots.setText(" ".join(dots))

    def _submit(self):
        if self._pin_value in self.allowed_pins:
            self.accept()
            return
        self.error_label.setText("Noto'g'ri PIN")
        self._pin_value = ""
        self._refresh_dots()


class AdminDialog(QDialog):
    def __init__(self, ui_ref, parent=None):
        super().__init__(parent)
        self.ui_ref = ui_ref
        self._active_input = None
        self._service_rows = []

        self.icon_options = []
        for svc in DEFAULT_CONFIG.get("services", {}).values():
            icon_name = svc.get("icon")
            if icon_name and icon_name not in self.icon_options:
                self.icon_options.append(icon_name)

        self.setModal(True)
        self.setWindowTitle("Admin sozlamalar")
        self.setFont(app_font(12, bold=True))
        self.setStyleSheet(
            """
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0c183b, stop:1 #0f1f4a);
                color: #f8fafc;
            }
            QLabel {
                color: #f8fafc;
            }
            QLabel#StatusLabel {
                font-size: 16px;
                color: #60a5fa;
            }
            QLineEdit, QComboBox {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                color: #f8fafc;
                padding: 8px 10px;
                font-size: 18px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #4c88ff;
            }
            QTableWidget {
                background: rgba(10, 34, 78, 0.6);
                border: 1px solid rgba(126, 174, 248, 0.28);
                gridline-color: rgba(126, 174, 248, 0.28);
                font-size: 17px;
            }
            QHeaderView::section {
                background: rgba(126, 174, 248, 0.18);
                color: #e2e8f0;
                font-size: 16px;
                font-weight: 800;
                border: 1px solid rgba(126, 174, 248, 0.28);
                padding: 8px;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4c88ff, stop:1 #3a6fd4);
                border: 1px solid rgba(76, 136, 255, 0.5);
                border-radius: 10px;
                color: #ffffff;
                padding: 10px 16px;
                font-size: 18px;
                font-weight: 800;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3a6fd4, stop:1 #2d5cb3);
            }
            QPushButton#SaveBtn {
                background: #2d6bd8;
            }
            QPushButton#ResetBtn {
                background: #274f99;
                border-color: #6fa1f5;
            }
            QPushButton#CloseBtn {
                background: #20478f;
                border-color: #7eaef8;
            }
            QCheckBox {
                font-size: 18px;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_col = QVBoxLayout()

        title_eyebrow = QLabel("Admin panel")
        title_eyebrow.setStyleSheet("font-size: 12px; color: #b6cdf5; font-weight: 700;")
        title = QLabel("Sozlamalar")
        title.setStyleSheet("font-size: 30px; font-weight: 800; color: #cfe1ff;")
        title_col.addWidget(title_eyebrow)
        title_col.addWidget(title)

        header.addLayout(title_col)
        header.addStretch(1)

        self.total_label = QLabel("")
        self.total_label.setStyleSheet(
            "font-size: 18px; font-weight: 800; color: #e9f2ff;"
            "background: rgba(126, 174, 248, 0.2); border: 1px solid rgba(126, 174, 248, 0.45);"
            "border-radius: 8px; padding: 8px 12px;"
        )
        header.addWidget(self.total_label)

        close_top = QPushButton("Yopish")
        close_top.setObjectName("CloseBtn")
        close_top.clicked.connect(self.accept)
        header.addWidget(close_top)

        root.addLayout(header)

        settings_card = QFrame()
        settings_card.setStyleSheet(
            "QFrame { background: rgba(10,34,78,0.55); border: 1px solid rgba(126,174,248,0.28); border-radius: 12px; }"
        )
        settings_layout = QGridLayout(settings_card)
        settings_layout.setContentsMargins(12, 12, 12, 12)
        settings_layout.setHorizontalSpacing(18)
        settings_layout.setVerticalSpacing(12)

        self.pin_edit = self._new_text_edit(max_len=6, digits_only=True)
        self.pin2_edit = self._new_text_edit(max_len=6, digits_only=True)
        self.show_icons_check = QCheckBox("Iconlar")
        self.free_pause_edit = self._new_number_edit(0)
        self.paid_pause_edit = self._new_number_edit(1)
        self.bonus_percent_edit = self._new_number_edit(0)
        self.bonus_threshold_edit = self._new_number_edit(0)

        self._add_labeled_field(settings_layout, 0, 0, "PIN", self.pin_edit)
        self._add_labeled_field(settings_layout, 0, 1, "PIN 2", self.pin2_edit)
        self._add_labeled_field(settings_layout, 0, 2, "Tekin pauza (s)", self.free_pause_edit)
        self._add_labeled_field(settings_layout, 0, 3, "Pauza 5000 so'm (s)", self.paid_pause_edit)
        self._add_labeled_field(settings_layout, 1, 0, "Bonus %", self.bonus_percent_edit)
        self._add_labeled_field(settings_layout, 1, 1, "Bonus threshold (so'm)", self.bonus_threshold_edit)
        settings_layout.addWidget(self.show_icons_check, 1, 2, 1, 2)

        root.addWidget(settings_card)

        services_card = QFrame()
        services_card.setStyleSheet(
            "QFrame { background: rgba(10,34,78,0.55); border: 1px solid rgba(126,174,248,0.28); border-radius: 12px; }"
        )
        services_layout = QVBoxLayout(services_card)
        services_layout.setContentsMargins(12, 12, 12, 12)
        services_layout.setSpacing(10)

        services_title = QLabel("Xizmatlar")
        services_title.setStyleSheet("font-size: 22px; font-weight: 800;")
        services_layout.addWidget(services_title)

        self.service_table = QTableWidget(0, 5)
        self.service_table.setHorizontalHeaderLabels(["Nomi", "Icon", "Rang", "Vaqt (s)", "Faol"])
        self.service_table.verticalHeader().setVisible(False)
        self.service_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.service_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.service_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.service_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.service_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.service_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.service_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        services_layout.addWidget(self.service_table)

        root.addWidget(services_card, 1)

        keyboard_card = QFrame()
        keyboard_card.setStyleSheet(
            "QFrame { background: rgba(10,34,78,0.58); border: 1px solid rgba(126,174,248,0.28); border-radius: 12px; }"
        )
        keyboard_layout = QVBoxLayout(keyboard_card)
        keyboard_layout.setContentsMargins(10, 10, 10, 10)
        keyboard_layout.setSpacing(8)

        keyboard_label = QLabel("Virtual klaviatura")
        keyboard_label.setStyleSheet("font-size: 16px; color: #b6cdf5; font-weight: 700;")
        keyboard_layout.addWidget(keyboard_label)

        self.keyboard_display = QLabel("Fokus: yo'q")
        self.keyboard_display.setStyleSheet("font-size: 18px; color: #dbe9ff; font-weight: 800;")
        keyboard_layout.addWidget(self.keyboard_display)

        key_rows = [
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE", "CLEAR"],
            ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
            ["A", "S", "D", "F", "G", "H", "J", "K", "L"],
            ["Z", "X", "C", "V", "B", "N", "M", "SPACE"],
        ]

        for row_keys in key_rows:
            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)
            for key in row_keys:
                btn = QPushButton("<" if key == "BACKSPACE" else ("Clear" if key == "CLEAR" else ("Bo'shliq" if key == "SPACE" else key)))
                btn.clicked.connect(partial(self._handle_virtual_key, key))
                if key in ("SPACE", "BACKSPACE", "CLEAR"):
                    btn.setMinimumWidth(130)
                row_layout.addWidget(btn)
            keyboard_layout.addLayout(row_layout)

        root.addWidget(keyboard_card)

        footer = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setObjectName("StatusLabel")
        footer.addWidget(self.status_label, 1)

        reset_btn = QPushButton("Standartga qaytarish")
        reset_btn.setObjectName("ResetBtn")
        reset_btn.clicked.connect(self._reset_defaults)

        save_btn = QPushButton("Saqlash")
        save_btn.setObjectName("SaveBtn")
        save_btn.clicked.connect(self._save)

        close_btn = QPushButton("Yopish")
        close_btn.setObjectName("CloseBtn")
        close_btn.clicked.connect(self.accept)

        footer.addWidget(reset_btn)
        footer.addWidget(save_btn)
        footer.addWidget(close_btn)
        root.addLayout(footer)

        self._register_focus_target(self.pin_edit, pin=True)
        self._register_focus_target(self.pin2_edit, pin=True)
        self._register_focus_target(self.free_pause_edit, numeric=True)
        self._register_focus_target(self.paid_pause_edit, numeric=True)
        self._register_focus_target(self.bonus_percent_edit, numeric=True)
        self._register_focus_target(self.bonus_threshold_edit, numeric=True)

        self._load_payload(self.ui_ref._settings_payload())

    def _new_text_edit(self, max_len=None, digits_only=False):
        edit = QLineEdit()
        if max_len:
            edit.setMaxLength(max_len)
        if digits_only:
            edit.setValidator(QIntValidator(0, 999999))
        return edit

    def _new_number_edit(self, min_value):
        edit = QLineEdit()
        edit.setValidator(QIntValidator(min_value, 999999))
        return edit

    def _add_labeled_field(self, layout, row, col, label, widget):
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(4)

        cap = QLabel(label)
        cap.setStyleSheet("font-size: 14px; color: #dce3f4; font-weight: 700;")
        container_layout.addWidget(cap)
        container_layout.addWidget(widget)

        layout.addWidget(container, row, col)

    def _register_focus_target(self, widget, numeric=False, pin=False):
        widget.setProperty("numeric", bool(numeric or pin))
        widget.setProperty("pin", bool(pin))
        widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.FocusIn and isinstance(obj, QLineEdit):
            self._active_input = obj
            self._update_keyboard_display()
        return super().eventFilter(obj, event)

    def _load_payload(self, payload):
        payload = payload or {}

        self.pin_edit.setText(str(payload.get("pin") or "1234"))
        self.pin2_edit.setText(str(payload.get("pin2") or "5678"))
        self.show_icons_check.setChecked(bool(payload.get("showIcons", True)))

        pause_cfg = payload.get("pause", {}) or {}
        self.free_pause_edit.setText(str(_to_int(pause_cfg.get("freeSeconds", 5), 5, 0)))
        self.paid_pause_edit.setText(str(_to_int(pause_cfg.get("paidSecondsPer5000", 120), 120, 1)))

        bonus_cfg = payload.get("bonus", {}) or {}
        self.bonus_percent_edit.setText(str(_to_int(bonus_cfg.get("percent", 0), 0, 0)))
        self.bonus_threshold_edit.setText(str(_to_int(bonus_cfg.get("threshold", 0), 0, 0)))

        self.total_label.setText(f"Jami: {_format_money(self.ui_ref.cfg.get('total_earned', 0))} so'm")

        services = payload.get("services", [])
        if isinstance(services, dict):
            services = [{"name": name, **(svc or {})} for name, svc in services.items()]

        default_services = []
        for key, svc in self.ui_ref.cfg.get("services", {}).items():
            default_services.append(
                {
                    "name": key,
                    "label": svc.get("display_name", key),
                    "icon": svc.get("icon", ""),
                    "theme": svc.get("theme", "suv"),
                    "secondsPer5000": max(1, math.ceil(5000 / max(1, int(svc.get("price_per_sec", 1))))),
                    "active": bool(svc.get("active", True)),
                }
            )

        indexed = {}
        for svc in services:
            key = svc.get("name") or svc.get("key")
            if key:
                indexed[key] = svc

        rows = []
        for fallback in default_services:
            key = fallback["name"]
            src = indexed.get(key, fallback)
            rows.append(
                {
                    "key": key,
                    "label": str(src.get("label") or src.get("display_name") or key),
                    "icon": str(src.get("icon") or fallback.get("icon") or ""),
                    "theme": str(src.get("theme") or fallback.get("theme") or "suv"),
                    "seconds": _to_int(src.get("secondsPer5000"), fallback.get("secondsPer5000", 120), 1),
                    "active": bool(src.get("active", fallback.get("active", True))),
                }
            )

        self._populate_service_rows(rows)

    def _populate_service_rows(self, rows):
        self._service_rows = []
        self.service_table.setRowCount(0)

        for row_idx, svc in enumerate(rows):
            self.service_table.insertRow(row_idx)

            name_edit = QLineEdit(str(svc.get("label") or svc.get("key") or ""))
            self._register_focus_target(name_edit)

            icon_combo = QComboBox()
            icon_combo.setMinimumWidth(120)
            for icon_name in self.icon_options:
                icon_fp = _icon_path(icon_name)
                if icon_fp:
                    icon_combo.addItem(QIcon(icon_fp), icon_name)
                else:
                    icon_combo.addItem(icon_name)
            icon_val = str(svc.get("icon") or "")
            if icon_val and icon_val not in self.icon_options:
                icon_combo.addItem(icon_val)
            found_icon = icon_combo.findText(icon_val)
            if found_icon >= 0:
                icon_combo.setCurrentIndex(found_icon)

            theme_combo = QComboBox()
            theme_combo.setMinimumWidth(130)
            for theme_name in THEME_COLORS.keys():
                theme_combo.addItem(theme_name)
            theme_val = str(svc.get("theme") or "suv")
            found_theme = theme_combo.findText(theme_val)
            theme_combo.setCurrentIndex(found_theme if found_theme >= 0 else 0)

            seconds_edit = QLineEdit(str(_to_int(svc.get("seconds"), 120, 1)))
            seconds_edit.setValidator(QIntValidator(1, 999999))
            self._register_focus_target(seconds_edit, numeric=True)

            active_check = QCheckBox()
            active_check.setChecked(bool(svc.get("active", True)))

            active_holder = QWidget()
            active_layout = QHBoxLayout(active_holder)
            active_layout.setContentsMargins(0, 0, 0, 0)
            active_layout.addWidget(active_check, alignment=Qt.AlignmentFlag.AlignCenter)

            self.service_table.setCellWidget(row_idx, 0, name_edit)
            self.service_table.setCellWidget(row_idx, 1, icon_combo)
            self.service_table.setCellWidget(row_idx, 2, theme_combo)
            self.service_table.setCellWidget(row_idx, 3, seconds_edit)
            self.service_table.setCellWidget(row_idx, 4, active_holder)
            self.service_table.setRowHeight(row_idx, 58)

            self._service_rows.append(
                {
                    "key": str(svc.get("key")),
                    "name_edit": name_edit,
                    "icon_combo": icon_combo,
                    "theme_combo": theme_combo,
                    "seconds_edit": seconds_edit,
                    "active_check": active_check,
                }
            )

        self._active_input = self.pin_edit
        self._update_keyboard_display()

    def _handle_virtual_key(self, key):
        if not isinstance(self._active_input, QLineEdit):
            self._active_input = self.pin_edit

        target = self._active_input
        text = target.text()
        is_numeric = bool(target.property("numeric"))
        is_pin = bool(target.property("pin"))

        if key == "CLEAR":
            text = ""
        elif key == "BACKSPACE":
            text = text[:-1]
        elif key == "SPACE":
            if is_numeric:
                return
            text += " "
        else:
            if is_numeric and not key.isdigit():
                return
            if is_pin and len(text) >= 6:
                return
            text += key

        target.setText(text)
        self._update_keyboard_display()

    def _update_keyboard_display(self):
        if not isinstance(self._active_input, QLineEdit):
            self.keyboard_display.setText("Fokus: yo'q")
            return

        target = self._active_input
        name = "Matn"
        if target is self.pin_edit:
            name = "PIN"
        elif target is self.pin2_edit:
            name = "PIN 2"
        elif target is self.free_pause_edit:
            name = "Tekin pauza"
        elif target is self.paid_pause_edit:
            name = "Pauza 5000"
        elif target is self.bonus_percent_edit:
            name = "Bonus %"
        elif target is self.bonus_threshold_edit:
            name = "Bonus threshold"

        if bool(target.property("pin")):
            raw = target.text()
            masked = []
            for idx in range(6):
                masked.append("O" if idx < len(raw) else "o")
            self.keyboard_display.setText(f"{name}: {''.join(masked)}")
            return

        self.keyboard_display.setText(f"{name}: {target.text()}")

    def _collect_settings(self):
        free_pause = _to_int(self.free_pause_edit.text(), 5, 0)
        paid_pause = _to_int(self.paid_pause_edit.text(), 120, 1)
        bonus_percent = _to_int(self.bonus_percent_edit.text(), 0, 0)
        bonus_threshold = _to_int(self.bonus_threshold_edit.text(), 0, 0)

        services = []
        for row in self._service_rows:
            key = row["key"]
            label = (row["name_edit"].text() or key).strip()
            icon = row["icon_combo"].currentText().strip()
            theme = row["theme_combo"].currentText().strip() or "suv"
            seconds = _to_int(row["seconds_edit"].text(), 120, 1)
            active = row["active_check"].isChecked()

            services.append(
                {
                    "key": key,
                    "name": key,
                    "label": label,
                    "icon": icon,
                    "theme": theme,
                    "active": active,
                    "secondsPer5000": seconds,
                    "duration": seconds,
                    "showIcon": True,
                }
            )

        return {
            "pin": (self.pin_edit.text() or "1234").strip(),
            "pin2": (self.pin2_edit.text() or "5678").strip(),
            "showIcons": self.show_icons_check.isChecked(),
            "totalButtons": len(services),
            "pause": {
                "freeSeconds": free_pause,
                "paidSecondsPer5000": paid_pause,
            },
            "bonus": {
                "percent": bonus_percent,
                "threshold": bonus_threshold,
            },
            "services": services,
        }

    def _set_status(self, text, color="#60a5fa"):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"font-size: 18px; color: {color};")

    def _save(self):
        payload = self._collect_settings()
        self.ui_ref.update_front_settings(payload)
        self.total_label.setText(f"Jami: {_format_money(self.ui_ref.cfg.get('total_earned', 0))} so'm")
        self._set_status("Saqlandi", "#22c55e")

    def _reset_defaults(self):
        answer = QMessageBox.question(
            self,
            "Tasdiqlang",
            "Barcha sozlamalar standartga qaytadi. Davom etilsinmi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.ui_ref.reset_config_to_defaults()
        self._load_payload(self.ui_ref._settings_payload())
        self._set_status("Standart sozlamalar tiklandi", "#f59e0b")


