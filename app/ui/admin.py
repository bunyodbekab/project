"""Admin UI dialogs."""

import glob
import math
import os
import shutil
import subprocess
import sys
import time
from functools import partial
from pathlib import Path

from PyQt6.QtCore import QEvent, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QIcon, QIntValidator, QPainter, QPixmap
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
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app.settings import DEFAULT_CONFIG, SHOW_GAME_ADMIN_SETTINGS, ICONS_DIR, app_font
from .common import THEME_COLORS, _format_money, _icon_path, _to_int

# Custom icons directory for user-provided icons
ADDICONS_DIR = os.path.join(os.path.dirname(ICONS_DIR), "addicons")


def _center_message_box_on_parent(msg_box, parent):
    """Center QMessageBox on the same screen as parent widget."""
    if parent and parent.isVisible():
        try:
            from PyQt6.QtGui import QScreen
            # Get parent window's screen
            parent_screen = parent.screen()
            if parent_screen:
                screen_geo = parent_screen.availableGeometry()
                msg_geo = msg_box.geometry()
                
                # Center on the screen
                x = screen_geo.x() + (screen_geo.width() - msg_geo.width()) // 2
                y = screen_geo.y() + (screen_geo.height() - msg_geo.height()) // 2
                msg_box.move(x, y)
        except Exception:
            pass  # Fallback to Qt's default centering


class FallbackComboBox(QComboBox):
    """Compact selector: click to cycle values, avoids popup issues in rotated/touch layouts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaxVisibleItems(12)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def showPopup(self):
        # Disable native popup in this layout; selection changes by click cycling.
        return

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.count() > 0:
                next_index = (self.currentIndex() + 1) % self.count()
                self.setCurrentIndex(next_index)
                self.activated.emit(next_index)
            event.accept()
            return
        super().mousePressEvent(event)


class CenteredIconComboBox(FallbackComboBox):
    """Icon-only selector that always paints the current icon at the exact center."""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        idx = self.currentIndex()
        if idx < 0:
            return

        icon = self.itemIcon(idx)
        if icon.isNull():
            return

        size = self.iconSize()
        if size.isEmpty():
            size = QSize(min(self.width(), 48), min(self.height(), 48))

        pixmap = icon.pixmap(size)
        x = (self.width() - pixmap.width()) // 2
        y = (self.height() - pixmap.height()) // 2
        painter.drawPixmap(x, y, pixmap)


class PinDialog(QDialog):
    def __init__(self, allowed_pins, parent=None, on_clear_money=None):
        super().__init__(parent)
        self.allowed_pins = [str(p) for p in allowed_pins if str(p)]
        self._pin_value = ""
        self.on_clear_money = on_clear_money

        self.setModal(False)
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
                font-size: 26px;
                font-weight: 800;
                padding: 12px;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3a6fd4, stop:1 #2d5cb3);
            }
            QPushButton#SubmitBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4c88ff, stop:1 #3a6fd4);
                font-size: 30px;
            }
            QPushButton#ClearBtn {
                background: rgba(76, 136, 255, 0.08);
                border-color: rgba(76, 136, 255, 0.3);
                color: #a8d5ff;
                font-size: 30px;
            }
            QPushButton#CancelBtn {
                font-size: 30px;
            }
            QPushButton#ResetMoneyBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #d04141, stop:1 #a93333);
                border-color: rgba(255, 130, 130, 0.5);
                color: #fff5f5;
                font-size: 30px;
            }
            QPushButton#ResetMoneyBtn:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #a93333, stop:1 #812626);
            }
            QPushButton#DigitBtn {
                font-size: 52px;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 26, 26, 26)
        root.setSpacing(14)

        top_section = QWidget(self)
        top_layout = QVBoxLayout(top_section)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)

        title = QLabel("PIN kiriting")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 52px; font-weight: 900;")
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._pin_dot_size = 64
        self._pin_dot_border = 5
        self.pin_dots = QWidget(self)
        self.pin_dots.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        dots_layout = QHBoxLayout(self.pin_dots)
        dots_layout.setContentsMargins(0, 0, 0, 0)
        dots_layout.setSpacing(18)
        dots_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.pin_dot_items = []
        for _ in range(6):
            dot = QFrame(self.pin_dots)
            dot.setFixedSize(self._pin_dot_size, self._pin_dot_size)
            dots_layout.addWidget(dot)
            self.pin_dot_items.append(dot)

        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setStyleSheet("color: #ff9a9a; font-size: 24px; min-height: 36px;")
        self.error_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        top_layout.addStretch(1)
        top_layout.addWidget(title)
        top_layout.addWidget(self.pin_dots)
        top_layout.addWidget(self.error_label)
        top_layout.addStretch(1)

        bottom_section = QWidget(self)
        bottom_layout = QVBoxLayout(bottom_section)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(10)

        keypad = QGridLayout()
        keypad.setSpacing(8)
        keypad.setContentsMargins(0, 0, 0, 0)
        digits = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
        for idx, digit in enumerate(digits):
            row = idx // 3
            col = idx % 3
            btn = QPushButton(digit)
            btn.setObjectName("DigitBtn")
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            btn.clicked.connect(partial(self._add_digit, digit))
            keypad.addWidget(btn, row, col)

        zero_btn = QPushButton("0")
        zero_btn.setObjectName("DigitBtn")
        zero_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        zero_btn.clicked.connect(partial(self._add_digit, "0"))

        reset_money_btn = QPushButton("Pulni tozalash")
        reset_money_btn.setObjectName("ResetMoneyBtn")
        reset_money_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        reset_money_btn.clicked.connect(self._clear_money)

        keypad.addWidget(reset_money_btn, 3, 0)
        keypad.addWidget(zero_btn, 3, 1)

        for row in range(4):
            keypad.setRowStretch(row, 1)
        for col in range(3):
            keypad.setColumnStretch(col, 1)

        bottom_layout.addLayout(keypad, 1)

        actions = QHBoxLayout()
        actions.setSpacing(10)

        cancel_btn = QPushButton("Bekor qilish")
        cancel_btn.setObjectName("CancelBtn")
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        cancel_btn.setMinimumHeight(96)
        cancel_btn.clicked.connect(self.reject)

        clear_btn = QPushButton("Tozalash")
        clear_btn.setObjectName("ClearBtn")
        clear_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        clear_btn.setMinimumHeight(96)
        clear_btn.clicked.connect(self._clear)

        submit_btn = QPushButton("Kirish")
        submit_btn.setObjectName("SubmitBtn")
        submit_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        submit_btn.setMinimumHeight(96)
        submit_btn.clicked.connect(self._submit)

        actions.addWidget(cancel_btn)
        actions.addWidget(clear_btn)
        actions.addWidget(submit_btn)

        bottom_layout.addLayout(actions)

        # Full-page split: top 35% PIN area, bottom 65% keypad area.
        root.addWidget(top_section, 35)
        root.addWidget(bottom_section, 65)
        self._refresh_dots()

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
        for idx, dot in enumerate(self.pin_dot_items):
            is_filled = idx < len(self._pin_value)
            bg = "#f8fafc" if is_filled else "rgba(248, 250, 252, 0.06)"
            border = "#f8fafc" if is_filled else "rgba(248, 250, 252, 0.78)"
            dot.setStyleSheet(
                f"background: {bg};"
                f"border: {self._pin_dot_border}px solid {border};"
                f"border-radius: {self._pin_dot_size // 2}px;"
            )

    def _submit(self):
        if self._pin_value in self.allowed_pins:
            self.accept()
            return
        self.error_label.setText("Noto'g'ri PIN")
        self._pin_value = ""
        self._refresh_dots()

    def _clear_money(self):
        if callable(self.on_clear_money):
            self.on_clear_money()
        self._clear()
        self.reject()


class LongPressButton(QPushButton):
    """Button that detects long press for 2+ seconds."""
    
    def __init__(self, text="", parent=None, on_short_click=None, on_long_press=None):
        super().__init__(text, parent)
        self.on_short_click = on_short_click
        self.on_long_press = on_long_press
        self._press_time = 0
    
    def mousePressEvent(self, event):
        self._press_time = time.monotonic()
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        if self._press_time > 0:
            elapsed = time.monotonic() - self._press_time
            self._press_time = 0
            
            if elapsed > 2.0 and callable(self.on_long_press):
                self.on_long_press()
                event.accept()
                return
            elif elapsed <= 2.0 and callable(self.on_short_click):
                self.on_short_click()
                event.accept()
                return
        
        super().mouseReleaseEvent(event)


class AdminDialog(QDialog):
    def __init__(self, ui_ref, parent=None):
        super().__init__(parent)
        self.ui_ref = ui_ref
        self._active_input = None
        self._service_rows = []
        self._show_game_admin_settings = bool(SHOW_GAME_ADMIN_SETTINGS)

        self.icon_options = []
        # Load default icons from config
        for svc in DEFAULT_CONFIG.get("services", {}).values():
            icon_name = svc.get("icon")
            if icon_name and icon_name not in self.icon_options:
                self.icon_options.append(icon_name)
        
        # Load custom icons from addicons folder
        if os.path.isdir(ADDICONS_DIR):
            for png_file in glob.glob(os.path.join(ADDICONS_DIR, "*.png")):
                icon_name = os.path.basename(png_file)
                if icon_name not in self.icon_options:
                    self.icon_options.append(icon_name)

        self.setModal(False)
        self.setWindowTitle("Admin sozlamalar")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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
                font-size: 22px;
                color: #60a5fa;
            }
            QLineEdit, QComboBox {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                color: #f8fafc;
                padding: 10px 14px;
                font-size: 22px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #4c88ff;
            }
            QComboBox::drop-down {
                width: 34px;
                border-left: 1px solid rgba(255, 255, 255, 0.2);
            }
            QComboBox#IconOnlyCombo {
                background: transparent;
                border: none;
                padding: 0px;
            }
            QComboBox#IconOnlyCombo::drop-down {
                width: 0px;
                border: none;
            }
            QComboBox#IconOnlyCombo::down-arrow {
                image: none;
                width: 0px;
                height: 0px;
            }
            QComboBox QAbstractItemView {
                background: rgba(12, 24, 59, 0.98);
                color: #f8fafc;
                border: 1px solid rgba(126, 174, 248, 0.55);
                selection-background-color: #2d6bd8;
                selection-color: #ffffff;
                font-size: 22px;
                outline: none;
            }
            QTableWidget {
                background: rgba(10, 34, 78, 0.6);
                border: 1px solid rgba(126, 174, 248, 0.28);
                gridline-color: rgba(126, 174, 248, 0.28);
                font-size: 22px;
            }
            QHeaderView::section {
                background: rgba(126, 174, 248, 0.18);
                color: #e2e8f0;
                font-size: 21px;
                font-weight: 800;
                border: 1px solid rgba(126, 174, 248, 0.28);
                padding: 10px;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4c88ff, stop:1 #3a6fd4);
                border: 1px solid rgba(76, 136, 255, 0.5);
                border-radius: 10px;
                color: #ffffff;
                padding: 12px 18px;
                font-size: 22px;
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
            QPushButton#RebootBtn {
                background: #d97706;
                border-color: #f59e0b;
            }
            QPushButton#ShutdownBtn {
                background: #b91c1c;
                border-color: #ef4444;
            }
            QPushButton#SaveBtn, QPushButton#ResetBtn, QPushButton#CloseBtn {
                font-size: 26px;
                min-height: 78px;
            }
            QPushButton#RebootBtn, QPushButton#ShutdownBtn {
                font-size: 24px;
                min-height: 78px;
            }
            QPushButton#CloseTopBtn {
                background: #20478f;
                border-color: #7eaef8;
                font-size: 22px;
                min-height: 58px;
            }
            QCheckBox#SwitchCheck {
                font-size: 22px;
                font-weight: 700;
                color: #dbe9ff;
                spacing: 14px;
            }
            QCheckBox#SwitchCheck::indicator {
                width: 58px;
                height: 32px;
                border-radius: 16px;
                border: 2px solid rgba(248, 250, 252, 0.48);
                background: rgba(160, 174, 192, 0.45);
            }
            QCheckBox#SwitchCheck::indicator:checked {
                background: #22c55e;
                border: 2px solid #86efac;
            }
            QCheckBox#SwitchCheck::indicator:unchecked {
                background: rgba(71, 85, 105, 0.75);
            }
            QLabel#SwitchStateLabel {
                font-size: 14px;
                font-weight: 800;
                border-radius: 8px;
                padding: 3px 8px;
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
            "font-size: 22px; font-weight: 800; color: #e9f2ff;"
            "background: rgba(126, 174, 248, 0.2); border: 1px solid rgba(126, 174, 248, 0.45);"
            "border-radius: 8px; padding: 8px 12px;"
        )
        chip_height = 62
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.total_label.setMinimumHeight(chip_height)
        self.total_label.setMaximumHeight(chip_height)
        header.addWidget(self.total_label)

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
        self.show_icons_check = QCheckBox("Iconlar ko'rsatish")
        self.show_icons_check.setObjectName("SwitchCheck")
        self.game_enabled_check = QCheckBox("O'yin rejimi")
        self.game_enabled_check.setObjectName("SwitchCheck")
        self.free_pause_edit = self._new_number_edit(0)
        self.paid_pause_edit = self._new_number_edit(1)
        self.bonus_percent_edit = self._new_number_edit(0)
        self.bonus_threshold_edit = self._new_number_edit(0)
        self.game_min_balance_edit = self._new_number_edit(0)
        self.game_reward_edit = self._new_number_edit(1)

        self._add_labeled_field(settings_layout, 0, 0, "PIN", self.pin_edit)
        self._add_labeled_field(settings_layout, 0, 1, "Tekin pauza (s)", self.free_pause_edit)
        self._add_labeled_field(settings_layout, 0, 2, "Pauza 5000 so'm (s)", self.paid_pause_edit)
        self._add_labeled_field(settings_layout, 0, 3, "Bonus %", self.bonus_percent_edit)
        self._add_labeled_field(settings_layout, 1, 0, "Bonus threshold (so'm)", self.bonus_threshold_edit)
        if self._show_game_admin_settings:
            self._add_labeled_field(settings_layout, 1, 1, "O'yin min balans (so'm)", self.game_min_balance_edit)
            self._add_labeled_field(settings_layout, 1, 2, "O'yin mukofot (so'm)", self.game_reward_edit)
            settings_layout.addWidget(self.game_enabled_check, 1, 3)
            
            # Show icons row with import button
            icons_row = QHBoxLayout()
            icons_row.setSpacing(12)
            icons_row.addWidget(self.show_icons_check)
            
            import_btn = LongPressButton(
                "Icon import",
                on_short_click=self._on_import_icons_clicked,
                on_long_press=self._show_clear_addicons_dialog
            )
            import_btn.setMaximumWidth(200)
            import_btn.setMinimumHeight(48)
            icons_row.addWidget(import_btn)
            icons_row.addStretch(1)
            
            icons_widget = QWidget()
            icons_widget.setLayout(icons_row)
            settings_layout.addWidget(icons_widget, 2, 0, 1, 4)
        else:
            icons_row = QHBoxLayout()
            icons_row.setSpacing(12)
            icons_row.addWidget(self.show_icons_check)
            
            import_btn = LongPressButton(
                "Icon import",
                on_short_click=self._on_import_icons_clicked,
                on_long_press=self._show_clear_addicons_dialog
            )
            import_btn.setMaximumWidth(200)
            import_btn.setMinimumHeight(48)
            icons_row.addWidget(import_btn)
            icons_row.addStretch(1)
            
            icons_widget = QWidget()
            icons_widget.setLayout(icons_row)
            settings_layout.addWidget(icons_widget, 1, 1, 1, 3)

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

        self.service_table = QTableWidget(0, 6)
        self.service_table.setHorizontalHeaderLabels(["Nomi", "Icon", "Rang", "Vaqt (s)", "Faol", "Bor"])
        self.service_table.verticalHeader().setVisible(False)
        self.service_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.service_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.service_table.setShowGrid(False)
        header_view = self.service_table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header_view.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.service_table.setColumnWidth(1, 124)
        self.service_table.setColumnWidth(2, 124)
        self.service_table.setColumnWidth(3, 122)
        self.service_table.setColumnWidth(4, 120)
        self.service_table.setColumnWidth(5, 120)
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
        keyboard_label.setStyleSheet("font-size: 19px; color: #b6cdf5; font-weight: 700;")
        keyboard_layout.addWidget(keyboard_label)

        self.keyboard_display = QLabel("Fokus: yo'q")
        self.keyboard_display.setStyleSheet("font-size: 22px; color: #dbe9ff; font-weight: 800;")
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

        reset_btn = QPushButton("Standart")
        reset_btn.setObjectName("ResetBtn")
        reset_btn.setMinimumHeight(82)
        reset_btn.clicked.connect(self._reset_defaults)

        save_btn = QPushButton("Saqlash")
        save_btn.setObjectName("SaveBtn")
        save_btn.setMinimumHeight(82)
        save_btn.clicked.connect(self._save)

        close_btn = QPushButton("Yopish")
        close_btn.setObjectName("CloseBtn")
        close_btn.setMinimumHeight(82)
        close_btn.clicked.connect(self.accept)

        reboot_btn = QPushButton("Reboot")
        reboot_btn.setObjectName("RebootBtn")
        reboot_btn.setMinimumHeight(82)
        reboot_btn.clicked.connect(lambda: self._request_system_action("reboot"))

        shutdown_btn = QPushButton("Shutdown")
        shutdown_btn.setObjectName("ShutdownBtn")
        shutdown_btn.setMinimumHeight(82)
        shutdown_btn.clicked.connect(lambda: self._request_system_action("shutdown"))

        footer.addWidget(reboot_btn)
        footer.addWidget(shutdown_btn)
        footer.addWidget(reset_btn)
        footer.addWidget(save_btn)
        footer.addWidget(close_btn)
        root.addLayout(footer)

        self._register_focus_target(self.pin_edit, pin=True)
        self._register_focus_target(self.free_pause_edit, numeric=True)
        self._register_focus_target(self.paid_pause_edit, numeric=True)
        self._register_focus_target(self.bonus_percent_edit, numeric=True)
        self._register_focus_target(self.bonus_threshold_edit, numeric=True)
        if self._show_game_admin_settings:
            self._register_focus_target(self.game_min_balance_edit, numeric=True)
            self._register_focus_target(self.game_reward_edit, numeric=True)

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

    def _make_color_swatch_icon(self, color_hex):
        pixmap = QPixmap(64, 38)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QColor(color_hex))
        painter.setPen(QColor("#f8fafc"))
        painter.drawRoundedRect(1, 1, 62, 36, 12, 12)
        painter.end()
        return QIcon(pixmap)

    def _add_labeled_field(self, layout, row, col, label, widget):
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(4)

        cap = QLabel(label)
        cap.setStyleSheet("font-size: 16px; color: #dce3f4; font-weight: 700;")
        container_layout.addWidget(cap)
        container_layout.addWidget(widget)

        layout.addWidget(container, row, col)

    def _build_centered_service_cell(self, widget):
        holder = QFrame()
        holder.setObjectName("CenteredServiceCell")
        holder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        holder_layout = QHBoxLayout(holder)
        holder_layout.setContentsMargins(6, 8, 6, 8)
        holder_layout.setSpacing(0)
        holder_layout.addWidget(widget, alignment=Qt.AlignmentFlag.AlignCenter)

        holder.setStyleSheet(
            "QFrame#CenteredServiceCell {"
            "border: 1px solid rgba(126, 174, 248, 0.55);"
            "border-radius: 10px;"
            "background: rgba(12, 24, 59, 0.22);"
            "}"
        )
        return holder

    def _update_switch_state_label(self, label, checked, on_text, off_text):
        checked = bool(checked)
        text = on_text if checked else off_text
        fg = "#dcfce7" if checked else "#fee2e2"
        bg = "rgba(34, 197, 94, 0.24)" if checked else "rgba(239, 68, 68, 0.22)"
        border = "rgba(134, 239, 172, 0.72)" if checked else "rgba(252, 165, 165, 0.72)"
        label.setText(text)
        label.setStyleSheet(
            f"font-size: 14px; font-weight: 800; color: {fg}; "
            f"background: {bg}; border: 1px solid {border}; border-radius: 8px; padding: 3px 8px;"
        )

    def _build_switch_cell(self, checked=False, on_text="ON", off_text="OFF"):
        switch_check = QCheckBox()
        switch_check.setObjectName("SwitchCheck")
        switch_check.setChecked(bool(checked))

        state_label = QLabel()
        state_label.setObjectName("SwitchStateLabel")
        state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_switch_state_label(state_label, switch_check.isChecked(), on_text, off_text)

        switch_check.toggled.connect(
            lambda state, lbl=state_label, on_val=on_text, off_val=off_text: self._update_switch_state_label(
                lbl,
                state,
                on_val,
                off_val,
            )
        )

        holder = QWidget()
        holder_layout = QHBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        holder_layout.setSpacing(6)
        holder_layout.addWidget(switch_check)
        holder_layout.addWidget(state_label)
        holder_layout.addStretch(1)
        holder_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return holder, switch_check

    def _register_focus_target(self, widget, numeric=False, pin=False):
        widget.setProperty("numeric", bool(numeric or pin))
        widget.setProperty("pin", bool(pin))
        widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.FocusIn and isinstance(obj, QLineEdit):
            self._active_input = obj
            self._update_keyboard_display()
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        super().showEvent(event)
        self._clear_initial_focus()

    def _clear_initial_focus(self):
        focus_widgets = [
            self.pin_edit,
            self.free_pause_edit,
            self.paid_pause_edit,
            self.bonus_percent_edit,
            self.bonus_threshold_edit,
        ]
        if self._show_game_admin_settings:
            focus_widgets.extend([
                self.game_min_balance_edit,
                self.game_reward_edit,
            ])

        for widget in focus_widgets:
            widget.clearFocus()
        self.service_table.clearSelection()
        self.service_table.clearFocus()
        self._active_input = None
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self._update_keyboard_display()

    def _load_payload(self, payload):
        payload = payload or {}

        self.pin_edit.setText(str(payload.get("pin") or "1234"))
        self.show_icons_check.setChecked(bool(payload.get("showIcons", True)))

        pause_cfg = payload.get("pause", {}) or {}
        self.free_pause_edit.setText(str(_to_int(pause_cfg.get("freeSeconds", 5), 5, 0)))
        self.paid_pause_edit.setText(str(_to_int(pause_cfg.get("paidSecondsPer5000", 120), 120, 1)))

        bonus_cfg = payload.get("bonus", {}) or {}
        self.bonus_percent_edit.setText(str(_to_int(bonus_cfg.get("percent", 0), 0, 0)))
        self.bonus_threshold_edit.setText(str(_to_int(bonus_cfg.get("threshold", 0), 0, 0)))

        game_cfg = payload.get("game", {}) or {}
        game_enabled = bool(game_cfg.get("enabled", False))
        game_min_balance = _to_int(
            game_cfg.get("minBalance", game_cfg.get("min_balance", 10000)),
            10000,
            0,
        )
        game_reward = _to_int(
            game_cfg.get("rewardPerCorrect", game_cfg.get("reward_per_correct", 500)),
            500,
            1,
        )
        self.game_enabled_check.setChecked(game_enabled)
        self.game_min_balance_edit.setText(str(game_min_balance))
        self.game_reward_edit.setText(str(game_reward))

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
                    "is_available": bool(svc.get("is_available", True)),
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
                    "is_available": bool(
                        src.get(
                            "is_available",
                            src.get("isAvailable", fallback.get("is_available", True)),
                        )
                    ),
                }
            )

        rows = rows[:8]
        self._populate_service_rows(rows)

    def _populate_service_rows(self, rows):
        self._service_rows = []
        self.service_table.setRowCount(0)

        for row_idx, svc in enumerate(rows):
            self.service_table.insertRow(row_idx)

            name_edit = QLineEdit(str(svc.get("label") or svc.get("key") or ""))
            name_edit.setMinimumHeight(58)
            name_edit.setFont(app_font(19, bold=True))
            name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._register_focus_target(name_edit)

            icon_combo = CenteredIconComboBox()
            icon_combo.setObjectName("IconOnlyCombo")
            icon_combo.setMinimumWidth(112)
            icon_combo.setMaximumWidth(112)
            icon_combo.setMinimumHeight(74)
            icon_combo.setFont(app_font(20, bold=True))
            icon_combo.setIconSize(QSize(60, 60))
            icon_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            icon_combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            for icon_name in self.icon_options:
                icon_fp = _icon_path(icon_name)
                if icon_fp:
                    icon_combo.addItem(QIcon(icon_fp), "")
                else:
                    icon_combo.addItem(QIcon(), "")
                icon_combo.setItemData(icon_combo.count() - 1, icon_name, Qt.ItemDataRole.UserRole)
            icon_val = str(svc.get("icon") or "")
            if icon_val and icon_val not in self.icon_options:
                custom_icon_fp = _icon_path(icon_val)
                icon_combo.addItem(QIcon(custom_icon_fp) if custom_icon_fp else QIcon(), "")
                icon_combo.setItemData(icon_combo.count() - 1, icon_val, Qt.ItemDataRole.UserRole)
            if icon_combo.count() == 0:
                icon_combo.addItem(QIcon(), "")
                icon_combo.setItemData(0, "", Qt.ItemDataRole.UserRole)

            selected_icon_idx = 0
            for i in range(icon_combo.count()):
                if str(icon_combo.itemData(i, Qt.ItemDataRole.UserRole) or "") == icon_val:
                    selected_icon_idx = i
                    break
            icon_combo.setCurrentIndex(selected_icon_idx)

            theme_combo = CenteredIconComboBox()
            theme_combo.setObjectName("IconOnlyCombo")
            theme_combo.setMinimumWidth(112)
            theme_combo.setMaximumWidth(112)
            theme_combo.setMinimumHeight(74)
            theme_combo.setFont(app_font(20, bold=True))
            theme_combo.setIconSize(QSize(64, 38))
            theme_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            theme_combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            for theme_name, theme_values in THEME_COLORS.items():
                swatch_color = "#4c88ff"
                if isinstance(theme_values, dict):
                    swatch_color = str(theme_values.get("swatch_color") or theme_values.get("border_color") or swatch_color)
                elif isinstance(theme_values, tuple) and len(theme_values) > 1:
                    swatch_color = str(theme_values[1])
                theme_combo.addItem(self._make_color_swatch_icon(swatch_color), "")
                theme_combo.setItemData(theme_combo.count() - 1, theme_name, Qt.ItemDataRole.UserRole)
            theme_val = str(svc.get("theme") or "suv")
            selected_theme_idx = 0
            for i in range(theme_combo.count()):
                if str(theme_combo.itemData(i, Qt.ItemDataRole.UserRole) or "") == theme_val:
                    selected_theme_idx = i
                    break
            theme_combo.setCurrentIndex(selected_theme_idx)

            icon_holder = self._build_centered_service_cell(icon_combo)
            theme_holder = self._build_centered_service_cell(theme_combo)

            seconds_edit = QLineEdit(str(_to_int(svc.get("seconds"), 120, 1)))
            seconds_edit.setValidator(QIntValidator(1, 999999))
            seconds_edit.setMinimumHeight(58)
            seconds_edit.setFont(app_font(21, bold=True))
            seconds_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._register_focus_target(seconds_edit, numeric=True)

            active_holder, active_check = self._build_switch_cell(
                checked=bool(svc.get("active", True)),
                on_text="ON",
                off_text="OFF",
            )

            available_holder, available_check = self._build_switch_cell(
                checked=bool(svc.get("is_available", True)),
                on_text="BOR",
                off_text="YO'Q",
            )

            self.service_table.setCellWidget(row_idx, 0, name_edit)
            self.service_table.setCellWidget(row_idx, 1, icon_holder)
            self.service_table.setCellWidget(row_idx, 2, theme_holder)
            self.service_table.setCellWidget(row_idx, 3, seconds_edit)
            self.service_table.setCellWidget(row_idx, 4, active_holder)
            self.service_table.setCellWidget(row_idx, 5, available_holder)
            self.service_table.setRowHeight(row_idx, 112)

            self._service_rows.append(
                {
                    "key": str(svc.get("key")),
                    "name_edit": name_edit,
                    "icon_combo": icon_combo,
                    "theme_combo": theme_combo,
                    "seconds_edit": seconds_edit,
                    "active_check": active_check,
                    "available_check": available_check,
                }
            )

        self._active_input = None
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
        elif target is self.free_pause_edit:
            name = "Tekin pauza"
        elif target is self.paid_pause_edit:
            name = "Pauza 5000"
        elif target is self.bonus_percent_edit:
            name = "Bonus %"
        elif target is self.bonus_threshold_edit:
            name = "Bonus threshold"
        elif target is self.game_min_balance_edit:
            name = "O'yin min balans"
        elif target is self.game_reward_edit:
            name = "O'yin mukofot"

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
        game_min_balance = _to_int(self.game_min_balance_edit.text(), 10000, 0)
        game_reward = _to_int(self.game_reward_edit.text(), 500, 1)

        services = []
        for row in self._service_rows:
            key = row["key"]
            label = (row["name_edit"].text() or key).strip()
            icon = str(row["icon_combo"].currentData(Qt.ItemDataRole.UserRole) or "").strip()
            theme = str(row["theme_combo"].currentData(Qt.ItemDataRole.UserRole) or "suv").strip() or "suv"
            seconds = _to_int(row["seconds_edit"].text(), 120, 1)
            active = row["active_check"].isChecked()
            is_available = row["available_check"].isChecked()

            services.append(
                {
                    "key": key,
                    "name": key,
                    "label": label,
                    "icon": icon,
                    "theme": theme,
                    "active": active,
                    "is_available": is_available,
                    "secondsPer5000": seconds,
                    "duration": seconds,
                    "showIcon": True,
                }
            )

        return {
            "pin": (self.pin_edit.text() or "1234").strip(),
            "showIcons": self.show_icons_check.isChecked(),
            "totalButtons": max(1, min(8, len(services))),
            "pause": {
                "freeSeconds": free_pause,
                "paidSecondsPer5000": paid_pause,
            },
            "bonus": {
                "percent": bonus_percent,
                "threshold": bonus_threshold,
            },
            "game": {
                "enabled": self.game_enabled_check.isChecked(),
                "minBalance": game_min_balance,
                "rewardPerCorrect": game_reward,
            },
            "services": services,
        }

    def _request_system_action(self, action):
        action = str(action or "").strip().lower()
        if action not in ("reboot", "shutdown"):
            return

        action_label = "qayta yuklash" if action == "reboot" else "o'chirish"
        msg_box = QMessageBox(
            QMessageBox.Icon.Question,
            "Tasdiqlang",
            f"Qurilmani {action_label}ni xohlaysizmi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            self,
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)
        _center_message_box_on_parent(msg_box, self)
        answer = msg_box.exec()
        if answer != QMessageBox.StandardButton.Yes:
            return

        if sys.platform == "win32":
            # Windows commands
            if action == "reboot":
                commands = [["shutdown", "/r", "/t", "0"]]
            else:
                commands = [["shutdown", "/s", "/t", "0"]]
        else:
            # Linux commands
            if action == "reboot":
                commands = [["systemctl", "reboot"], ["reboot"]]
            else:
                commands = [["systemctl", "poweroff"], ["shutdown", "-h", "now"]]

        last_error = None
        for cmd in commands:
            try:
                subprocess.Popen(cmd)
                self._set_status(f"Qurilma {action_label} buyrug'i yuborildi", "#f59e0b")
                return
            except Exception as exc:
                last_error = exc

        self._set_status(f"{action_label.title()} buyrug'i yuborilmadi", "#ef4444")
        msg_box = QMessageBox(
            QMessageBox.Icon.Warning,
            "Xatolik",
            f"{action_label.title()} buyrug'ini yuborib bo'lmadi.\n{last_error}",
            QMessageBox.StandardButton.Ok,
            self,
        )
        _center_message_box_on_parent(msg_box, self)
        msg_box.exec()

    def _set_status(self, text, color="#60a5fa"):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"font-size: 18px; color: {color};")

    def _save(self):
        payload = self._collect_settings()
        self.ui_ref.update_front_settings(payload)
        self.total_label.setText(f"Jami: {_format_money(self.ui_ref.cfg.get('total_earned', 0))} so'm")
        self._set_status("Saqlandi", "#22c55e")

    def _show_clear_addicons_dialog(self):
        """Show dialog to confirm clearing addicons folder."""
        msg_box = QMessageBox(
            QMessageBox.Icon.Question,
            "Tozalash",
            "Addicons folderini tozalamoqchisiz?",
            QMessageBox.StandardButton.No | QMessageBox.StandardButton.Yes,
            self,
        )
        _center_message_box_on_parent(msg_box, self)
        answer = msg_box.exec()
        if answer == QMessageBox.StandardButton.Yes:
            self._clear_addicons()
    
    def _clear_addicons(self):
        """Clear all PNG files from addicons folder."""
        try:
            if os.path.isdir(ADDICONS_DIR):
                for png_file in glob.glob(os.path.join(ADDICONS_DIR, "*.png")):
                    try:
                        os.remove(png_file)
                    except Exception as exc:
                        print(f"Faylni o'chirishda xato: {png_file}: {exc}")
                self._set_status("Addicons tozalandi", "#22c55e")
                self._refresh_icon_combos()
        except Exception as exc:
            self._set_status(f"Tozalashda xato: {exc}", "#ef4444")
    
    def _refresh_icon_combos(self):
        """Refresh icon combo boxes with current available icons."""
        # Regenerate icon_options
        self.icon_options = []
        for svc in DEFAULT_CONFIG.get("services", {}).values():
            icon_name = svc.get("icon")
            if icon_name and icon_name not in self.icon_options:
                self.icon_options.append(icon_name)
        
        if os.path.isdir(ADDICONS_DIR):
            for png_file in glob.glob(os.path.join(ADDICONS_DIR, "*.png")):
                icon_name = os.path.basename(png_file)
                if icon_name not in self.icon_options:
                    self.icon_options.append(icon_name)
        
        # Get first default icon as fallback
        default_icons = glob.glob(os.path.join(ICONS_DIR, "*.png"))
        first_default_icon = os.path.basename(default_icons[0]) if default_icons else ""
        
        # Update all service row icon combos
        for row in self._service_rows:
            icon_combo = row.get("icon_combo")
            if not icon_combo:
                continue
            
            # Get currently selected icon
            current_icon = str(icon_combo.currentData(Qt.ItemDataRole.UserRole) or "")
            
            # Clear combo
            icon_combo.clear()
            
            # Rebuild combo with all available icons
            for icon_name in self.icon_options:
                icon_fp = _icon_path(icon_name)
                if icon_fp:
                    icon_combo.addItem(QIcon(icon_fp), "")
                else:
                    icon_combo.addItem(QIcon(), "")
                icon_combo.setItemData(icon_combo.count() - 1, icon_name, Qt.ItemDataRole.UserRole)
            
            # Try to restore previously selected icon, or use first default if not found
            selected_idx = 0
            for i in range(icon_combo.count()):
                if str(icon_combo.itemData(i, Qt.ItemDataRole.UserRole) or "") == current_icon:
                    selected_idx = i
                    break
            else:
                # If current icon not found, use first default icon
                if first_default_icon:
                    for i in range(icon_combo.count()):
                        if str(icon_combo.itemData(i, Qt.ItemDataRole.UserRole) or "") == first_default_icon:
                            selected_idx = i
                            break
            
            icon_combo.setCurrentIndex(selected_idx)
    
    def _find_usb_icons_paths(self):
        """Find possible USB mounted paths with icons folder - works on Windows and Linux."""
        potential_paths = []
        
        if sys.platform == "win32":
            # Windows: search all drive letters
            import string
            for drive in string.ascii_uppercase:
                drive_path = f"{drive}:\\"
                if os.path.isdir(drive_path):
                    try:
                        # Search for icons folder at root level
                        icons_dir = os.path.join(drive_path, "icons")
                        if os.path.isdir(icons_dir):
                            potential_paths.append(icons_dir)
                        
                        # Search one level deep
                        for item in glob.glob(os.path.join(drive_path, "*", "icons")):
                            if os.path.isdir(item):
                                potential_paths.append(item)
                    except Exception:
                        continue
        else:
            # Linux/Armbian: search mount points
            common_mounts = [
                "/media",
                "/mnt",
                "/aa",
                "/tmp",
                "/root",
                "/home",
                "/run/media",
                "/var/run/media",
                "/opt",
            ]
            
            # Try to search all mounted filesystems via /proc/mounts
            try:
                if os.path.exists("/proc/mounts"):
                    with open("/proc/mounts", "r") as f:
                        for line in f:
                            parts = line.split()
                            if len(parts) >= 2:
                                mount_point = parts[1]
                                # Skip system mount points
                                if mount_point not in ["/", "/boot", "/sys", "/proc", "/dev"]:
                                    if mount_point not in common_mounts:
                                        common_mounts.append(mount_point)
            except Exception:
                pass  # Continue with default mount points
            
            # Search for icons folders in all mount points
            for mount_base in common_mounts:
                if not os.path.isdir(mount_base):
                    continue
                
                try:
                    # Search up to 3 levels deep for icons folders
                    for item in glob.glob(os.path.join(mount_base, "*", "icons")):
                        if os.path.isdir(item):
                            potential_paths.append(item)
                    
                    # Two levels deep
                    for item in glob.glob(os.path.join(mount_base, "*", "*", "icons")):
                        if os.path.isdir(item):
                            potential_paths.append(item)
                    
                    # Direct icons folder
                    icons_dir = os.path.join(mount_base, "icons")
                    if os.path.isdir(icons_dir):
                        potential_paths.append(icons_dir)
                except Exception:
                    continue  # Skip problematic directories
        
        return list(set(potential_paths))  # Remove duplicates
    
    def _on_import_icons_clicked(self):
        """Handle import icons button click."""
        usb_paths = self._find_usb_icons_paths()
        
        if not usb_paths:
            # Show detailed error message
            if sys.platform == "win32":
                msg = "USB dagi icons/ folderi topilmadi.\n\nUSB bilan tutashgan drive ni tekshiring (D:, E:, F: va boshqa)\nva uni icons/ folderi mavjud bo'lsin."
            else:
                msg = "USB dagi icons/ folderi topilmadi.\n\nUSB montaj yo'llarini tekshiring:\n/media, /mnt, /tmp, /root, /home, /run/media"
            
            msg_box = QMessageBox(QMessageBox.Icon.Warning, "Topilmadi", msg, QMessageBox.StandardButton.Ok, self)
            _center_message_box_on_parent(msg_box, self)
            msg_box.exec()
            return
        
        if len(usb_paths) > 1:
            # If multiple paths found, use first one or show selection
            source_icons_dir = usb_paths[0]
        else:
            source_icons_dir = usb_paths[0]
        
        self._import_icons_from_path(source_icons_dir)
    
    def _import_icons_from_path(self, source_dir):
        """Import PNG icons from source directory to addicons folder."""
        try:
            # Create addicons directory if it doesn't exist
            os.makedirs(ADDICONS_DIR, exist_ok=True)
            
            # Find all PNG files in source
            png_files = glob.glob(os.path.join(source_dir, "*.png"))
            
            if not png_files:
                msg = f"PNG fayllar topilmadi:\n{source_dir}\n\nUSBga icons/PNG fayllarini qo'yib qayta harakat qiling."
                msg_box = QMessageBox(QMessageBox.Icon.Warning, "Topilmadi", msg, QMessageBox.StandardButton.Ok, self)
                _center_message_box_on_parent(msg_box, self)
                msg_box.exec()
                return
            
            # Get icon size from first icon in icons folder for reference
            ref_icon_size = None
            default_icons = glob.glob(os.path.join(ICONS_DIR, "*.png"))
            if default_icons:
                try:
                    pixmap = QPixmap(default_icons[0])
                    if not pixmap.isNull():
                        ref_icon_size = (pixmap.width(), pixmap.height())
                except Exception:
                    pass
            
            # Copy PNG files, maintaining exact size
            copied_count = 0
            for src_file in png_files:
                try:
                    filename = os.path.basename(src_file)
                    dst_file = os.path.join(ADDICONS_DIR, filename)
                    
                    # Load source image
                    src_pixmap = QPixmap(src_file)
                    if src_pixmap.isNull():
                        continue
                    
                    # If reference size exists, scale to match (maintaining aspect ratio)
                    if ref_icon_size:
                        src_pixmap = src_pixmap.scaledToWidth(
                            ref_icon_size[0],
                            Qt.TransformationMode.SmoothTransformation
                        )
                    
                    # Save to destination
                    if src_pixmap.save(dst_file, "PNG"):
                        copied_count += 1
                except Exception as exc:
                    print(f"Icon nusxa olishda xato: {src_file}: {exc}")
            
            if copied_count > 0:
                # Refresh icon options
                self.icon_options = []
                for svc in DEFAULT_CONFIG.get("services", {}).values():
                    icon_name = svc.get("icon")
                    if icon_name and icon_name not in self.icon_options:
                        self.icon_options.append(icon_name)
                
                if os.path.isdir(ADDICONS_DIR):
                    for png_file in glob.glob(os.path.join(ADDICONS_DIR, "*.png")):
                        icon_name = os.path.basename(png_file)
                        if icon_name not in self.icon_options:
                            self.icon_options.append(icon_name)
                
                self._set_status(f"{copied_count} ta icon import qilindi", "#22c55e")
                self._refresh_icon_combos()
                msg_box = QMessageBox(
                    QMessageBox.Icon.Information,
                    "Muvaffaqiyat",
                    f"{copied_count} ta PNG icon import qilindi.\n\nBirma-bir ustiga bosib tanlashingiz mumkin.",
                    QMessageBox.StandardButton.Ok,
                    self,
                )
                _center_message_box_on_parent(msg_box, self)
                msg_box.exec()
            else:
                msg = f"Hech qanday icon import qilib bo'lmadi.\n\nUsb manzilin tekshiring: {source_dir}"
                msg_box = QMessageBox(QMessageBox.Icon.Warning, "Xato", msg, QMessageBox.StandardButton.Ok, self)
                _center_message_box_on_parent(msg_box, self)
                msg_box.exec()
        except Exception as exc:
            self._set_status(f"Import xatosi: {exc}", "#ef4444")
            msg_box = QMessageBox(
                QMessageBox.Icon.Critical,
                "Xato",
                f"Icon import qilishda xato:\n{exc}",
                QMessageBox.StandardButton.Ok,
                self,
            )
            _center_message_box_on_parent(msg_box, self)
            msg_box.exec()
    
    def _reset_defaults(self):
        msg_box = QMessageBox(
            QMessageBox.Icon.Question,
            "Tasdiqlang",
            "Barcha sozlamalar standartga qaytadi. Davom etilsinmi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            self,
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)
        _center_message_box_on_parent(msg_box, self)
        answer = msg_box.exec()
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.ui_ref.reset_config_to_defaults()
        self._load_payload(self.ui_ref._settings_payload())
        self._set_status("Standart sozlamalar tiklandi", "#f59e0b")


