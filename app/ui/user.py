import json
import math
import os
import time
from datetime import datetime
from functools import partial

from PyQt6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QIcon, QIntValidator, QTransform
from PyQt6.QtWidgets import (
    QApplication,
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
    QGraphicsScene,
    QGraphicsView,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app.gpio_controller import GPIOController
from app.settings import BLINK_WARN, DEBUG, DEFAULT_CONFIG, ICONS_DIR, INPUT_GPIO_TO_SERVICE, LOW_BALANCE, app_font
from app.storage import add_session, load_config, save_config


THEME_COLORS = {
    "suv": ("#3366de", "#2f62d7", "#4c88ff"),
    "osmos": ("#25a2d8", "#2298cf", "#43caff"),
    "aktiv": ("#cf49dc", "#c540d8", "#e8aff3"),
    "pena": ("#2cadc6", "#2aa8c0", "#47d8ec"),
    "nano": ("#6b6de8", "#6063df", "#878bf7"),
    "vosk": ("#f4a706", "#f1a102", "#ffd254"),
    "quritish": ("#1f9b6c", "#17895c", "#3ad89b"),
}


def _theme_palette(theme_name):
    return THEME_COLORS.get(theme_name, THEME_COLORS["suv"])


def _icon_path(icon_file):
    if not icon_file:
        return ""
    path = os.path.join(ICONS_DIR, icon_file)
    return path if os.path.exists(path) else ""


def _to_int(value, fallback, min_value=0):
    try:
        out = int(str(value).strip())
    except Exception:
        out = fallback
    return max(min_value, out)


def _format_money(value):
    return "{:,}".format(max(0, int(value))).replace(",", " ")


class ClickableFrame(QFrame):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class RotatedContainer(QGraphicsView):
    def __init__(self, inner_widget, angle_deg=-90, parent=None, fallback_size=None):
        super().__init__(parent)
        self._inner = inner_widget
        self._angle = angle_deg
        self._fallback_size = fallback_size or (0, 0)

        self.setStyleSheet("background: transparent; border: none;")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._scene = QGraphicsScene(self)
        self._proxy = self._scene.addWidget(inner_widget)
        self._proxy.setTransform(QTransform().rotate(self._angle))
        self.setScene(self._scene)

        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

        self._update_scene_rect(force_fallback=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scene_rect()

    def _update_scene_rect(self, force_fallback=False):
        poly = self._proxy.mapToScene(self._proxy.boundingRect())
        rect = poly.boundingRect()
        if force_fallback or rect.width() <= 1 or rect.height() <= 1:
            fw, fh = self._fallback_size
            if fw and fh:
                rect = QRectF(0, 0, fw, fh)
            else:
                vp = self.viewport().rect()
                rect = QRectF(0, 0, max(1, vp.width()), max(1, vp.height()))
        self._scene.setSceneRect(rect)
        self.centerOn(rect.center())


class ServiceButton(QPushButton):
    def __init__(self, label, theme, icon_file, show_icon=True, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        text = str(label or "").upper()
        self.setText(text)
        self.setFont(app_font(22, bold=True))

        icon_path = _icon_path(icon_file) if show_icon else ""
        if icon_path:
            self.setIcon(QIcon(icon_path))
            self.setIconSize(QSize(84, 84))
            self.setStyleSheet("padding: 8px 12px; text-align: center;")
        else:
            self.setStyleSheet("padding: 8px 12px; text-align: center;")

        self._apply_style()

    def set_active(self, active):
        self._active = bool(active)
        self._apply_style()

    def _apply_style(self):
        c1, c2, border = _theme_palette(self._theme)
        border_width = "4px" if self._active else "3px"
        border_color = "#f8fafc" if self._active else border
        self.setStyleSheet(
            f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {c1}, stop:1 {c2});
                border: {border_width} solid {border_color};
                border-radius: 18px;
                color: #f3f7ff;
                font-size: 34px;
                font-weight: 800;
                line-height: 1;
                letter-spacing: 1.1px;
                padding: 12px 16px;
            }}
            QPushButton:hover {{
                border-color: #ffffff;
            }}
            QPushButton:pressed {{
                border-color: #ffffff;
                padding-top: 13px;
                padding-left: 17px;
            }}
            """
        )


class PauseButton(QFrame):
    pressedSignal = pyqtSignal()
    releasedSignal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False
        self._free = False

        self.setObjectName("PauseButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(8)

        self.left_mark = QLabel("STOP")
        self.left_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.left_mark.setFont(app_font(16, bold=True))
        self.left_mark.setStyleSheet("font-size: 30px; font-weight: 800;")

        self.right_mark = QLabel("STOP")
        self.right_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.right_mark.setFont(app_font(16, bold=True))
        self.right_mark.setStyleSheet("font-size: 30px; font-weight: 800;")

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(2)

        self.main_text = QLabel("PAUZA")
        self.main_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_text.setFont(app_font(30, bold=True))
        self.main_text.setStyleSheet("font-size: 62px; font-weight: 800; letter-spacing: 1px;")

        self.sub_text = QLabel("")
        self.sub_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_text.setFont(app_font(14, bold=True))
        self.sub_text.setStyleSheet("font-size: 28px; font-weight: 700;")

        center_layout.addWidget(self.main_text)
        center_layout.addWidget(self.sub_text)

        layout.addWidget(self.left_mark)
        layout.addWidget(center, 1)
        layout.addWidget(self.right_mark)

        self.set_state(False, False, "PAUZA", "")

    def set_state(self, is_active, is_free, label, sub_label):
        self._active = bool(is_active)
        self._free = bool(is_free)
        self.main_text.setText(label or "PAUZA")
        self.sub_text.setText(sub_label or "")

        if self._free:
            border_color = "#f1c232"
            bg_a = "#ffd84d"
            bg_b = "#f7c534"
            fg = "#1d1d1d"
        else:
            border_color = "#f8fafc" if self._active else "#e52235"
            bg_a = "#f53a46"
            bg_b = "#ed2435"
            fg = "#ffffff"

        border_width = "4px" if self._active else "3px"
        self.setStyleSheet(
            f"""
            QFrame#PauseButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {bg_a}, stop:1 {bg_b});
                border: {border_width} solid {border_color};
                border-radius: 18px;
                color: {fg};
            }}
            QLabel {{
                color: {fg};
            }}
            """
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.pressedSignal.emit()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.releasedSignal.emit()
        super().mouseReleaseEvent(event)


class PinDialog(QDialog):
    def __init__(self, allowed_pins, parent=None):
        super().__init__(parent)
        self.allowed_pins = [str(p) for p in allowed_pins if str(p)]
        self._pin_value = ""

        self.setModal(True)
        self.setWindowTitle("Admin PIN")
        self.setStyleSheet(
            """
            QDialog {
                background: #0f1f4a;
                color: #f8fafc;
            }
            QLabel {
                color: #f8fafc;
            }
            QPushButton {
                background: #1e335f;
                color: #f8fafc;
                border: 1px solid #365f9d;
                border-radius: 10px;
                font-size: 24px;
                font-weight: 700;
                padding: 10px;
            }
            QPushButton:pressed {
                background: #152647;
            }
            QPushButton#SubmitBtn {
                background: #3a6fd4;
                border-color: #4c88ff;
            }
            QPushButton#ClearBtn {
                background: #2f3f5f;
                border-color: #5b6b87;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 26, 26, 26)
        root.setSpacing(14)

        title = QLabel("PIN kiriting")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 34px; font-weight: 800;")
        root.addWidget(title)

        self.pin_dots = QLabel("o o o o o o")
        self.pin_dots.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_dots.setStyleSheet("font-size: 30px; font-weight: 700;")
        root.addWidget(self.pin_dots)

        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setStyleSheet("color: #ff9a9a; font-size: 20px; min-height: 28px;")
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
        self.setStyleSheet(
            """
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0a1436, stop:1 #081433);
                color: #f8fafc;
            }
            QLabel {
                color: #f8fafc;
            }
            QLabel#StatusLabel {
                font-size: 18px;
                color: #60a5fa;
            }
            QLineEdit, QComboBox {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                color: #f8fafc;
                padding: 8px 10px;
                font-size: 20px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #4c88ff;
            }
            QTableWidget {
                background: rgba(15, 23, 42, 0.5);
                border: 1px solid rgba(76, 136, 255, 0.2);
                gridline-color: rgba(76, 136, 255, 0.2);
                font-size: 19px;
            }
            QHeaderView::section {
                background: rgba(76, 136, 255, 0.15);
                color: #e2e8f0;
                font-size: 18px;
                font-weight: 700;
                border: 1px solid rgba(76, 136, 255, 0.2);
                padding: 8px;
            }
            QPushButton {
                background: #1f3f77;
                border: 1px solid #4c88ff;
                border-radius: 10px;
                color: #ffffff;
                padding: 10px 16px;
                font-size: 20px;
                font-weight: 700;
            }
            QPushButton:pressed {
                background: #162d55;
            }
            QPushButton#SaveBtn {
                background: #3a6fd4;
            }
            QPushButton#ResetBtn {
                background: #7c2d12;
                border-color: #dc2626;
            }
            QPushButton#CloseBtn {
                background: #1e293b;
                border-color: #475569;
            }
            QCheckBox {
                font-size: 20px;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_col = QVBoxLayout()

        title_eyebrow = QLabel("Admin panel")
        title_eyebrow.setStyleSheet("font-size: 14px; color: #94a3b8; font-weight: 700;")
        title = QLabel("Sozlamalar")
        title.setStyleSheet("font-size: 36px; font-weight: 800; color: #4c88ff;")
        title_col.addWidget(title_eyebrow)
        title_col.addWidget(title)

        header.addLayout(title_col)
        header.addStretch(1)

        self.total_label = QLabel("")
        self.total_label.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #4ade80;"
            "background: rgba(74, 222, 128, 0.1); border: 1px solid rgba(74, 222, 128, 0.35);"
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
            "QFrame { background: rgba(15,23,42,0.5); border: 1px solid rgba(76,136,255,0.2); border-radius: 12px; }"
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
            "QFrame { background: rgba(15,23,42,0.5); border: 1px solid rgba(76,136,255,0.2); border-radius: 12px; }"
        )
        services_layout = QVBoxLayout(services_card)
        services_layout.setContentsMargins(12, 12, 12, 12)
        services_layout.setSpacing(10)

        services_title = QLabel("Xizmatlar")
        services_title.setStyleSheet("font-size: 26px; font-weight: 800;")
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
            "QFrame { background: rgba(12,26,46,0.75); border: 1px solid rgba(76,136,255,0.2); border-radius: 12px; }"
        )
        keyboard_layout = QVBoxLayout(keyboard_card)
        keyboard_layout.setContentsMargins(10, 10, 10, 10)
        keyboard_layout.setSpacing(8)

        keyboard_label = QLabel("Virtual klaviatura")
        keyboard_label.setStyleSheet("font-size: 18px; color: #94a3b8; font-weight: 700;")
        keyboard_layout.addWidget(keyboard_label)

        self.keyboard_display = QLabel("Fokus: yo'q")
        self.keyboard_display.setStyleSheet("font-size: 22px; color: #5eb3ff; font-weight: 700;")
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
        cap.setStyleSheet("font-size: 16px; color: #dce3f4;")
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


class MoykaUI(QWidget):
    def __init__(self, width, height):
        super().__init__()

        self.w = width
        self.h = height
        self.setFixedSize(width, height)
        self.setObjectName("MoykaRoot")

        self.cfg = load_config()
        relay_map = {
            name: data.get("gpio_out", data.get("relay_bit", idx))
            for idx, (name, data) in enumerate(self.cfg["services"].items())
        }
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

        self._pause_hold_timer = QTimer(self)
        self._pause_hold_timer.setSingleShot(True)
        self._pause_hold_timer.setInterval(2000)
        self._pause_hold_timer.timeout.connect(self._pause_hold_tick)
        self._stop_hold_source = None
        self._stop_hold_started = None

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

        self._service_buttons = {}
        self._grid_dirty = True
        self._pin_dialog_open = False

        self._setup_ui()
        self._rebuild_front_services()
        self._emit_state()

    def _setup_ui(self):
        self._title_max_px = max(72, int(self.h * 0.12))
        self._title_min_px = max(34, int(self.h * 0.052))
        self._main_max_px = max(86, int(self.h * 0.17))
        self._main_min_px = max(44, int(self.h * 0.07))
        self._top_panel_height = max(260, int(self.h * 0.34))

        self.setStyleSheet(
            """
            QWidget#MoykaRoot {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #050c1f, stop:0.55 #0b1f49, stop:1 #10285f);
                color: #f8fafc;
            }
            QFrame#TopPanel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(18, 36, 84, 220), stop:1 rgba(9, 22, 54, 220));
                border: 2px solid rgba(132, 183, 255, 120);
                border-radius: 24px;
            }
            QFrame#Divider {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(222, 235, 255, 40), stop:0.5 rgba(248, 252, 255, 220), stop:1 rgba(222, 235, 255, 40));
                border: none;
                min-height: 5px;
                max-height: 5px;
                border-radius: 2px;
            }
            QWidget#ControlsWrap {
                background: rgba(6, 15, 38, 150);
                border: 1px solid rgba(132, 183, 255, 80);
                border-radius: 24px;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        self.top_panel = ClickableFrame(self)
        self.top_panel.setObjectName("TopPanel")
        self.top_panel.setFixedHeight(self._top_panel_height)
        self.top_panel.clicked.connect(self._on_top_panel_clicked)
        top_layout = QVBoxLayout(self.top_panel)
        top_layout.setContentsMargins(28, 20, 28, 14)
        top_layout.setSpacing(8)

        self.header_title = QLabel("XUSH KELIBSIZ")
        self.header_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_title.setStyleSheet("font-weight: 800; font-style: italic; letter-spacing: 3px; color: #ffffff;")

        self.header_main = QLabel(self.cfg.get("moyka_name", "MOYKA"))
        self.header_main.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_main.setStyleSheet("font-weight: 900; letter-spacing: 1px; color: #ffffff;")

        top_layout.addStretch(1)
        top_layout.addWidget(self.header_title)
        top_layout.addWidget(self.header_main)
        top_layout.addStretch(1)

        divider = QFrame(self)
        divider.setObjectName("Divider")

        controls_wrap = QWidget(self)
        controls_wrap.setObjectName("ControlsWrap")
        controls_layout = QVBoxLayout(controls_wrap)
        controls_layout.setContentsMargins(18, 18, 18, 18)
        controls_layout.setSpacing(14)

        grid_holder = QWidget(controls_wrap)
        grid_holder.setObjectName("GridHolder")
        self.service_grid = QGridLayout(grid_holder)
        self.service_grid.setContentsMargins(0, 0, 0, 0)
        self.service_grid.setHorizontalSpacing(14)
        self.service_grid.setVerticalSpacing(14)
        self.service_grid.setColumnStretch(0, 1)
        self.service_grid.setColumnStretch(1, 1)
        controls_layout.addWidget(grid_holder, 1)

        self.pause_button = PauseButton(controls_wrap)
        self.pause_button.setMinimumHeight(max(120, int(self.h * 0.19)))
        self.pause_button.pressedSignal.connect(lambda: self._on_stop_pressed("touch"))
        self.pause_button.releasedSignal.connect(lambda: self._on_stop_released("touch"))

        root.addWidget(self.top_panel)
        root.addWidget(divider)
        root.addWidget(controls_wrap, 1)

    def _fit_font_px(self, text, max_px, min_px, max_width, max_height, bold=True):
        safe = text if text and str(text).strip() else " "
        lines = safe.split("\n")
        width_limit = max(80, int(max_width))
        height_limit = max(40, int(max_height))

        for px in range(int(max_px), int(min_px) - 1, -1):
            font = app_font(px, bold=bold)
            fm = QFontMetrics(font)

            line_width = 0
            for ln in lines:
                line_width = max(line_width, fm.horizontalAdvance(ln if ln else " "))

            total_height = fm.height() * len(lines) + max(0, len(lines) - 1) * 4
            if line_width <= width_limit and total_height <= height_limit:
                return px

        return int(min_px)

    def _apply_dynamic_header_fonts(self, mode):
        panel_w = max(220, self.top_panel.width() - 56)
        panel_h = max(140, self.top_panel.height() - 34)

        if mode == "idle":
            title_room = int(panel_h * 0.30)
            main_room = int(panel_h * 0.62)
        else:
            title_room = int(panel_h * 0.36)
            main_room = int(panel_h * 0.54)

        title_px = self._fit_font_px(
            self.header_title.text(),
            self._title_max_px,
            self._title_min_px,
            panel_w,
            title_room,
            bold=True,
        )
        main_px = self._fit_font_px(
            self.header_main.text(),
            self._main_max_px,
            self._main_min_px,
            panel_w,
            main_room,
            bold=True,
        )

        self.header_title.setFont(app_font(title_px, bold=True))
        self.header_main.setFont(app_font(main_px, bold=True))

    def _on_top_panel_clicked(self):
        if self.is_running or self.pause_mode:
            return
        self.add_money(5000)

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
            pause_cfg = self.cfg.get("pause") or {}

        self.pause_free_default = max(0, int((pause_cfg or {}).get("freeSeconds", 0)))
        paid_sec = max(1, int((pause_cfg or {}).get("paidSecondsPer5000", 60)))
        self.pause_paid_rate = max(1, math.ceil(5000 / paid_sec))

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
                        "hw_key": hw_key,
                    }
                )
                fk_to_hw[front_key] = hw_key
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
        self._grid_dirty = True

    def update_front_settings(self, settings):
        norm = self._normalize_front_settings(settings)
        if not norm:
            return

        self.front_settings = norm
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
            if balance_value <= 0:
                title = "XUSH KELIBSIZ"
                main_text = self.cfg.get("moyka_name", "MOYKA")
            else:
                title = "BALANS"
                main_text = f"{_format_money(balance_value)}\nSO'M"

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
                }
            )

        return {
            "mode": mode,
            "title": title,
            "mainText": main_text,
            "headerColor": self._header_color(mode),
            "balanceText": _format_money(self.balance),
            "activeService": self.active_front_key or "",
            "services": services,
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

    def _refresh_service_grid(self):
        while self.service_grid.count():
            item = self.service_grid.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self.pause_button:
                widget.deleteLater()

        self._service_buttons = {}
        show_icons = bool(self.cfg.get("show_icons", True))
        btn_height = max(116, int(self.h * 0.165))

        for idx, slot in enumerate(self.front_services):
            front_key = slot.get("front_key")
            if not front_key:
                continue

            btn = ServiceButton(
                label=slot.get("label", front_key),
                theme=slot.get("theme", "suv"),
                icon_file=slot.get("icon_file", ""),
                show_icon=show_icons,
            )
            btn.setMinimumHeight(btn_height)
            btn.clicked.connect(partial(self.button_clicked, front_key))

            row = idx // 2
            col = idx % 2
            self.service_grid.addWidget(btn, row, col)
            self._service_buttons[front_key] = btn

        count = len(self.front_services)
        pause_row = count // 2
        if count % 2 == 1:
            self.service_grid.addWidget(self.pause_button, pause_row, 1)
        else:
            self.service_grid.addWidget(self.pause_button, pause_row, 0, 1, 2)

        self._grid_dirty = False

    def _render_state(self):
        if self._grid_dirty:
            self._refresh_service_grid()

        state = self._state_dict()
        mode = state.get("mode", "idle")
        title = state.get("title", "")
        main_text = state.get("mainText", "")
        header_color = state.get("headerColor", "#ffffff")

        self.header_title.setText(title)
        self.header_main.setText(main_text)
        self.header_title.setStyleSheet(
            f"font-weight: 800; font-style: italic; letter-spacing: 3px; color: {header_color};"
        )
        self.header_main.setStyleSheet(
            f"font-weight: 900; letter-spacing: 1px; color: {header_color};"
        )
        self._apply_dynamic_header_fonts(mode)

        active_front_key = state.get("activeService")
        for key, btn in self._service_buttons.items():
            btn.set_active(bool(self.is_running and key == active_front_key))

        pause_state = state.get("pauseState", {}) or {}
        is_pause = mode == "pause"
        is_free = pause_state.get("status") == "free"
        pause_label = pause_state.get("label") or ("TEKIN PAUZA" if is_free else "PAUZA")
        pause_sub = pause_state.get("remainingText") or ""
        self.pause_button.set_state(is_pause, is_free, pause_label, pause_sub)

    def _emit_state(self):
        self._render_state()

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

        self._stop_hold_source = None

    def _pause_hold_tick(self):
        self._pause_hold_timer.stop()
        if self._stop_hold_source is not None and not self.is_running:
            self._open_pin_modal()
            self._stop_hold_source = None

    def _open_pin_modal(self):
        if self._pin_dialog_open:
            return

        self._pin_dialog_open = True
        try:
            pins = [self.cfg.get("admin_pin", "1234"), self.cfg.get("admin_pin_alt", "5678")]
            dialog = PinDialog(pins, self)
            dialog.resize(520, 680)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self._open_admin_panel()
        finally:
            self._pin_dialog_open = False

    def _open_admin_panel(self):
        dialog = AdminDialog(self, self)
        dialog.setWindowState(dialog.windowState() | Qt.WindowState.WindowFullScreen)
        dialog.exec()
        self._emit_state()

    def _return_to_main(self):
        self._emit_state()

    def _tick(self):
        if self.pause_mode:
            self._tick_pause()
            return

        if not self.is_running or not self.active_service:
            return

        cost = max(
            1,
            int(self.price_per_sec.get(self.active_front_key) or self.cfg["services"][self.active_service].get("price_per_sec", 1)),
        )

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

    def _activate_pin(self, name):
        if not name:
            return
        self.gpio.all_off()
        self.gpio.set_pin(name, 1)

    def _deactivate_pin(self, name):
        if not name:
            return
        self.gpio.set_pin(name, 0)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
            self._on_top_panel_clicked()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.gpio.cleanup()
        super().closeEvent(event)

    def resizeEvent(self, event):
        self._emit_state()
        super().resizeEvent(event)


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

        # Render UI in swapped dimensions and rotate by -90 degrees.
        self.ui = MoykaUI(sh, sw)
        self.rotated = RotatedContainer(self.ui, -90, self, fallback_size=(sw, sh))
        layout.addWidget(self.rotated)

    def show_ui(self):
        self.showFullScreen()

    def keyPressEvent(self, event):
        self.ui.keyPressEvent(event)
        if event.key() == Qt.Key.Key_Escape:
            QApplication.quit()
