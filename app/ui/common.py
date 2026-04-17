import os
import re
from PyQt6.QtCore import QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap, QTransform
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
    "suv": {
        "gradient_css": "linear-gradient(90deg, #3366de 0%, #2f62d7 100%)",
        "gradient_qss": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3366de, stop:1 #2f62d7)",
        "swatch_color": "#4c88ff",
        "border_color": "#4c88ff",
    },
    "osmos": {
        "gradient_css": "linear-gradient(90deg, #25a2d8 0%, #2298cf 100%)",
        "gradient_qss": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #25a2d8, stop:1 #2298cf)",
        "swatch_color": "#43caff",
        "border_color": "#43caff",
    },
    "aktiv": {
        "gradient_css": "linear-gradient(90deg, #cf49dc 0%, #c540d8 100%)",
        "gradient_qss": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #cf49dc, stop:1 #c540d8)",
        "swatch_color": "#e8aff3",
        "border_color": "#e8aff3",
    },
    "pena": {
        "gradient_css": "linear-gradient(90deg, #2cadc6 0%, #2aa8c0 100%)",
        "gradient_qss": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2cadc6, stop:1 #2aa8c0)",
        "swatch_color": "#47d8ec",
        "border_color": "#47d8ec",
    },
    "nano": {
        "gradient_css": "linear-gradient(90deg, #6b6de8 0%, #6063df 100%)",
        "gradient_qss": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6b6de8, stop:1 #6063df)",
        "swatch_color": "#878bf7",
        "border_color": "#878bf7",
    },
    "vosk": {
        "gradient_css": "linear-gradient(90deg, #f4a706 0%, #f1a102 100%)",
        "gradient_qss": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f4a706, stop:1 #f1a102)",
        "swatch_color": "#ffd254",
        "border_color": "#ffd254",
    },
    "quritish": {
        "gradient_css": "linear-gradient(90deg, #1f9b6c 0%, #17895c 100%)",
        "gradient_qss": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f9b6c, stop:1 #17895c)",
        "swatch_color": "#3ad89b",
        "border_color": "#3ad89b",
    },
}


def _theme_palette(theme_name):
    default_theme = THEME_COLORS["suv"]
    theme_meta = THEME_COLORS.get(theme_name, default_theme)

    # Backward-compatible fallback in case old tuple format is loaded from elsewhere.
    if isinstance(theme_meta, tuple):
        return default_theme["gradient_qss"], str(theme_meta[1] if len(theme_meta) > 1 else default_theme["border_color"])

    gradient = str(theme_meta.get("gradient_qss") or default_theme["gradient_qss"])
    border_color = str(theme_meta.get("border_color") or default_theme["border_color"])
    return gradient, border_color


_HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")


def _darken_hex(color_hex, amount=0.2):
    amount = max(0.0, min(1.0, float(amount)))
    factor = 1.0 - amount

    color_hex = str(color_hex or "")
    if not _HEX_COLOR_RE.fullmatch(color_hex):
        return color_hex

    r = int(color_hex[1:3], 16)
    g = int(color_hex[3:5], 16)
    b = int(color_hex[5:7], 16)
    return f"#{int(r * factor):02x}{int(g * factor):02x}{int(b * factor):02x}"


def _darken_gradient_qss(gradient_qss, amount=0.2):
    gradient_qss = str(gradient_qss or "")
    return _HEX_COLOR_RE.sub(lambda m: _darken_hex(m.group(0), amount=amount), gradient_qss)


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


class _UnavailableOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event):
        super().paintEvent(event)
        rect = self.rect().adjusted(7, 7, -7, -7)
        if rect.width() <= 0 or rect.height() <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(rect), 10, 10)
        painter.setClipPath(clip_path)
        painter.fillRect(rect, QColor(100, 116, 139, 70))

        pen = QPen(QColor(239, 68, 68, 220))
        pen.setWidth(max(3, int(min(rect.width(), rect.height()) * 0.04)))
        painter.setPen(pen)

        height = int(rect.height())
        step = max(18, int(rect.width() * 0.16))
        start = int(rect.left() - rect.height())
        end = int(rect.right() + rect.height())
        for offset in range(start, end, step):
            painter.drawLine(offset, int(rect.bottom()), offset + height, int(rect.top()))

        painter.end()


class ServiceButton(QPushButton):

    def __init__(self, label, theme, icon_file, show_icon=True, parent=None):
        super().__init__(parent)
        self._theme = str(theme or "suv")
        self._icon_file = str(icon_file or "")
        self._show_icon = bool(show_icon)
        self._available = True
        self._active = False
        self._pulse_active = False
        self._base_font_px = 34
        self._min_font_px = 24
        self._max_font_px = 30
        self._icon_px = 70

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setSingleShot(True)
        self._pulse_timer.timeout.connect(self._clear_pulse)

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

        self._unavailable_overlay = _UnavailableOverlay(self)
        self._unavailable_overlay.hide()

        self._update_icon()
        self._apply_style()
        self._fit_text_font()

    def set_active(self, active):
        self._active = bool(active) and self._available
        self._apply_style()

    def set_available(self, available):
        self._available = bool(available)
        if not self._available:
            self._pulse_timer.stop()
            self._pulse_active = False
            self._active = False
        self.setEnabled(self._available)
        cursor = Qt.CursorShape.PointingHandCursor if self._available else Qt.CursorShape.ForbiddenCursor
        self.setCursor(cursor)
        self._apply_style()

    def pulse_click(self, duration_ms=140):
        if not self._available:
            return
        self._pulse_active = True
        self._apply_style()
        self._pulse_timer.start(max(60, int(duration_ms)))

    def _clear_pulse(self):
        self._pulse_active = False
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
        if self._available:
            gradient, border_color = _theme_palette(self._theme)
            pressed_gradient = _darken_gradient_qss(gradient, amount=0.2)
            display_gradient = pressed_gradient if self._pulse_active else gradient
            highlighted = self._active or self._pulse_active
            active_border_color = "#f8fafc" if highlighted else border_color
            border_width = "12px" if self._pulse_active else "10px"
            border_css = f"{border_width} solid {active_border_color}"
            pressed_border_css = "12px solid #f8fafc"
            text_color = "#ffffff"
        else:
            display_gradient = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8f9db0, stop:1 #758295)"
            pressed_gradient = display_gradient
            border_css = "10px solid #94a3b8"
            pressed_border_css = border_css
            text_color = "#e2e8f0"

        self.setStyleSheet(
            f"""
            QPushButton#ServiceButton {{
                background: {display_gradient};
                border: {border_css};
                border-radius: 12px;
            }}
            QPushButton#ServiceButton:disabled {{
                background: {display_gradient};
                border: {border_css};
                border-radius: 12px;
            }}
            QPushButton#ServiceButton:pressed {{
                background: {pressed_gradient};
                border: {pressed_border_css};
            }}
            QLabel#ServiceText {{
                color: {text_color};
                font-family: Montserrat, sans-serif;
                font-weight: 800;
                letter-spacing: 0.015em;
                padding: 4px 12px 4px 4px;
            }}
            """
        )

        self._unavailable_overlay.setVisible(not self._available)
        self._unavailable_overlay.raise_()

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
        self._unavailable_overlay.setGeometry(self.rect())
        self._unavailable_overlay.raise_()
        self._update_icon()
        self._fit_text_font()

    def showEvent(self, event):
        super().showEvent(event)
        self._unavailable_overlay.setGeometry(self.rect())
        self._unavailable_overlay.raise_()
        self._update_icon()
        self._fit_text_font()

class PauseButton(QFrame):
    pressedSignal = pyqtSignal()
    releasedSignal = pyqtSignal()
    longPressedSignal = pyqtSignal()  # Emitted after 2 seconds of continuous press

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False
        self._free = False
        self._pressed_visual = False
        self._main_font_px = 56
        self._sub_font_px = 26
        self._mark_font_px = 38
        self._label_text = "PAUZA"
        self._sub_label_text = ""
        self._long_press_timer = QTimer()
        self._long_press_timer.setSingleShot(True)
        self._long_press_timer.timeout.connect(self._on_long_press_timeout)
        self._long_press_triggered = False
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setSingleShot(True)
        self._pulse_timer.timeout.connect(self._clear_pulse)

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
        self.main_text.setWordWrap(True)
        self.main_text.setMinimumWidth(1)
        self.main_text.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)


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
        self._label_text = label or "PAUZA"
        self._sub_label_text = sub_label or ""
        self.main_text.setText(self._label_text)
        self.sub_text.setText(self._sub_label_text)
        self.sub_text.setVisible(bool(self._sub_label_text))

        self._apply_style()

    def pulse_click(self, duration_ms=160):
        self._pressed_visual = True
        self._apply_style()
        self._pulse_timer.start(max(80, int(duration_ms)))

    def _clear_pulse(self):
        self._pressed_visual = False
        self._apply_style()

    def _apply_style(self):
        self.main_text.setText(self._label_text)
        self.sub_text.setText(self._sub_label_text)
        self.sub_text.setVisible(bool(self._sub_label_text))

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

        if self._pressed_visual:
            border_color = "#f8fafc"
            border_width = "12px"
            gradient = _darken_gradient_qss(gradient, amount=0.2)
        else:
            border_width = "10px"

        main_font_px = self._main_font_px
        if self._free:
            # "TEKIN PAUZA" is longer; keep it smaller so button geometry stays stable.
            main_font_px = max(16, int(self._main_font_px * 0.56))

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
            f"font-size: {main_font_px}px; font-weight: 800; letter-spacing: 0.01em; color: {fg};"
        )
        self.sub_text.setStyleSheet(
            f"font-size: {self._sub_font_px}px; font-weight: 700; color: {fg};"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._long_press_triggered = False
            self._pressed_visual = True
            self._apply_style()
            self._long_press_timer.start(2000)  # 2 seconds
            self.grabMouse()
            self.pressedSignal.emit()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._long_press_timer.stop()
            self._pressed_visual = False
            self._apply_style()
            if QWidget.mouseGrabber() is self:
                self.releaseMouse()
            self.releasedSignal.emit()
        super().mouseReleaseEvent(event)
    
    def _on_long_press_timeout(self):
        """Triggered after 2 seconds of holding down the button."""
        self._long_press_triggered = True
        self.longPressedSignal.emit()


