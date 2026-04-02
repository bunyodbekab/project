import os
from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QIcon, QPixmap, QTransform
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.settings import ICONS_DIR, app_font


# HTML/CSS-dagi original colors
THEME_COLORS = {
    "suv": ("linear-gradient(90deg, #3366de 0%, #2f62d7 100%)", "#4c88ff"),
    "osmos": ("linear-gradient(90deg, #25a2d8 0%, #2298cf 100%)", "#43caff"),
    "aktiv": ("linear-gradient(90deg, #cf49dc 0%, #c540d8 100%)", "#e8aff3"),
    "pena": ("linear-gradient(90deg, #2cadc6 0%, #2aa8c0 100%)", "#47d8ec"),
    "nano": ("linear-gradient(90deg, #6b6de8 0%, #6063df 100%)", "#878bf7"),
    "vosk": ("linear-gradient(90deg, #f4a706 0%, #f1a102 100%)", "#ffd254"),
    "quritish": ("linear-gradient(90deg, #1f9b6c 0%, #17895c 100%)", "#3ad89b"),
}


def _theme_palette(theme_name):
    """Convert HTML/CSS gradient format to PyQt6 qlineargradient format"""
    themes = {
        "suv": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3366de, stop:1 #2f62d7)",
        "osmos": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #25a2d8, stop:1 #2298cf)",
        "aktiv": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #cf49dc, stop:1 #c540d8)",
        "pena": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2cadc6, stop:1 #2aa8c0)",
        "nano": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6b6de8, stop:1 #6063df)",
        "vosk": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f4a706, stop:1 #f1a102)",
        "quritish": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f9b6c, stop:1 #17895c)",
    }
    
    # Return gradient and border color
    gradient = themes.get(theme_name, themes["suv"])
    borders = {
        "suv": "#4c88ff", "osmos": "#43caff", "aktiv": "#e8aff3",
        "pena": "#47d8ec", "nano": "#878bf7", "vosk": "#ffd254", "quritish": "#3ad89b"
    }
    return gradient, borders.get(theme_name, "#4c88ff")


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
        self._theme = str(theme or "suv")
        self._icon_file = str(icon_file or "")
        self._show_icon = bool(show_icon)
        self._active = False
        self._base_font_px = 34
        self._min_font_px = 24
        self._max_font_px = 30
        self._icon_px = 70

        self.setObjectName("ServiceButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setText("")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        self.icon_label = QLabel()
        self.icon_label.setObjectName("ServiceIcon")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.text_label = QLabel(str(label or "").upper())
        self.text_label.setObjectName("ServiceText")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setWordWrap(True)
        self.text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label, 1)

        self._update_icon()
        self._apply_style()
        self._fit_text_font()

    def set_active(self, active):
        self._active = bool(active)
        self._apply_style()

    def set_font_px(self, px):
        self._base_font_px = max(18, int(px))
        # Keep most button labels in a close visual range.
        self._min_font_px = max(22, int(self._base_font_px * 0.76))
        self._max_font_px = max(self._min_font_px, int(self._base_font_px * 0.90))
        self._icon_px = max(70, min(90, int(self._base_font_px * 0.95)))
        self._update_icon()
        self._apply_style()
        self._fit_text_font()

    def _update_icon(self):
        if not self._show_icon:
            self.icon_label.clear()
            self.icon_label.setFixedWidth(0)
            return

        icon_path = _icon_path(self._icon_file)
        if not icon_path:
            self.icon_label.clear()
            self.icon_label.setFixedWidth(0)
            return

        icon_px = max(22, min(self._icon_px, int(max(1, self.height()) * 0.56)))
        max_slot = max(40, int(self.width() * 0.35)) if self.width() > 0 else icon_px + 16
        slot_width = min(max_slot, icon_px + 16)
        slot_width = max(36, slot_width)
        if icon_px > slot_width - 8:
            icon_px = max(18, slot_width - 8)

        pixmap = QPixmap(icon_path).scaled(
            icon_px,
            icon_px,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.icon_label.setPixmap(pixmap)
        self.icon_label.setFixedWidth(slot_width)

    def _apply_style(self):
        gradient, _ = _theme_palette(self._theme)
        border_css = "4px solid #f8fafc" if self._active else "3px solid rgba(255, 255, 255, 0.25)"

        self.setStyleSheet(
            f"""
            QPushButton#ServiceButton {{
                background: {gradient};
                border: {border_css};
                border-radius: 12px;
            }}
            QLabel#ServiceText {{
                color: #ffffff;
                font-family: Montserrat, sans-serif;
                font-weight: 800;
                letter-spacing: 0.015em;
                padding: 4px 12px 4px 4px;
            }}
            """
        )

    def _fit_text_font(self):
        text = self.text_label.text().strip()
        if not text:
            self.text_label.setFont(app_font(self._base_font_px, bold=True))
            return

        available_w = max(36, self.text_label.width() - 12)
        available_h = max(28, self.text_label.height() - 8)

        min_px = self._min_font_px
        max_px = self._max_font_px
        chosen_px = None
        has_space = " " in text
        self.text_label.setWordWrap(has_space)

        wrap_flags = int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignCenter)

        for px in range(max_px, min_px - 1, -1):
            font = app_font(px, bold=True)
            fm = QFontMetrics(font)

            if has_space:
                bound = fm.boundingRect(0, 0, available_w, 4096, wrap_flags, text)
                line_h = max(1, fm.lineSpacing())
                lines = max(1, (bound.height() + line_h - 1) // line_h)
                fits = lines <= 2 and bound.height() <= available_h
            else:
                one_line_w = fm.horizontalAdvance(text)
                fits = one_line_w <= available_w and fm.height() <= available_h

            if fits:
                chosen_px = px
                break

        # If a specific label still doesn't fit, allow controlled extra shrink.
        if chosen_px is None:
            safety_min_px = max(14, int(self._base_font_px * 0.55))
            for px in range(min_px - 1, safety_min_px - 1, -1):
                font = app_font(px, bold=True)
                fm = QFontMetrics(font)

                if has_space:
                    bound = fm.boundingRect(0, 0, available_w, 4096, wrap_flags, text)
                    line_h = max(1, fm.lineSpacing())
                    lines = max(1, (bound.height() + line_h - 1) // line_h)
                    fits = lines <= 2 and bound.height() <= available_h
                else:
                    one_line_w = fm.horizontalAdvance(text)
                    fits = one_line_w <= available_w and fm.height() <= available_h

                if fits:
                    chosen_px = px
                    break

            if chosen_px is None:
                chosen_px = safety_min_px

        self.text_label.setFont(app_font(chosen_px, bold=True))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_icon()
        self._fit_text_font()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_icon()
        self._fit_text_font()

class PauseButton(QFrame):
    pressedSignal = pyqtSignal()
    releasedSignal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False
        self._free = False
        self._main_font_px = 56
        self._sub_font_px = 26
        self._mark_font_px = 38

        self.setObjectName("PauseButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self.left_mark = QLabel()
        self.left_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.left_mark.setFixedSize(48, 48)

        self.right_mark = QLabel()
        self.right_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.right_mark.setFixedSize(48, 48)
        
        # Load stop icon
        icon_path = _icon_path("⛔.png")
        if icon_path:
            pixmap = QPixmap(icon_path).scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.left_mark.setPixmap(pixmap)
            self.right_mark.setPixmap(pixmap)

        center = QWidget()
        center_layout = QHBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(10)

        self.main_text = QLabel("PAUZA")
        self.main_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.sub_text = QLabel("")
        self.sub_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        center_layout.addStretch()
        center_layout.addWidget(self.main_text)
        center_layout.addWidget(self.sub_text)
        center_layout.addStretch()

        layout.addWidget(self.left_mark)
        layout.addWidget(center, 1)
        layout.addWidget(self.right_mark)

        self.set_state(False, False, "PAUZA", "")

    def set_font_px(self, main_px, sub_px, mark_px):
        self._main_font_px = max(22, int(main_px))
        self._sub_font_px = max(12, int(sub_px))
        self._mark_font_px = max(22, int(mark_px))
        
        # Keep pause markers at the exact size passed from the service icon sizing logic.
        mark_size = self._mark_font_px
        icon_path = _icon_path("⛔.png")
        if icon_path:
            pixmap = QPixmap(icon_path).scaled(mark_size, mark_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.left_mark.setPixmap(pixmap)
            self.right_mark.setPixmap(pixmap)
            self.left_mark.setFixedSize(mark_size, mark_size)
            self.right_mark.setFixedSize(mark_size, mark_size)
        
        # Update text labels with dynamic font size
        self.main_text.setFont(app_font(self._main_font_px, bold=True))
        self.sub_text.setFont(app_font(self._sub_font_px, bold=True))

    def set_state(self, is_active, is_free, label, sub_label):
        self._active = bool(is_active)
        self._free = bool(is_free)
        self.main_text.setText(label or "PAUZA")
        self.sub_text.setText(sub_label or "")

        if self._free:
            # Free pause - yellow
            border_color = "#f1c232"
            gradient = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ffd84d, stop:1 #f7c534)"
            fg = "#1d1d1d"
        else:
            # Paid pause - red
            border_color = "#f8fafc" if self._active else "#e52235"
            gradient = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f53a46, stop:1 #ed2435)"
            fg = "#ffffff"

        border_width = "4px" if self._active else "3px"
        self.setStyleSheet(
            f"""
            QFrame#PauseButton {{
                background: {gradient};
                border: {border_width} solid {border_color};
                border-radius: 12px;
                color: {fg};
            }}
            QLabel {{
                color: {fg};
                font-weight: 800;
            }}
            """
        )
        self.main_text.setStyleSheet(
            f"font-size: {self._main_font_px}px; font-weight: 800; letter-spacing: 0.01em; color: {fg};"
        )
        self.sub_text.setStyleSheet(
            f"font-size: {self._sub_font_px}px; font-weight: 700; color: {fg};"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.pressedSignal.emit()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.releasedSignal.emit()
        super().mouseReleaseEvent(event)


