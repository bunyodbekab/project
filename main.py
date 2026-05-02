import os
import subprocess
import sys
from pathlib import Path


_QT_MSG_HANDLER = None
_QT_PREV_MSG_HANDLER = None


def _venv_python() -> Path:
    root = Path(__file__).resolve().parent
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def _ensure_venv_runtime():
    if os.environ.get("MOYKA_VENV_BOOTSTRAPPED") == "1":
        return None

    venv_python = _venv_python()
    if not venv_python.exists():
        return None

    current = str(Path(sys.executable).resolve()).lower()
    target = str(venv_python.resolve()).lower()
    if current == target:
        return None

    env = os.environ.copy()
    env["MOYKA_VENV_BOOTSTRAPPED"] = "1"
    result = subprocess.run([target, str(Path(__file__).resolve()), *sys.argv[1:]], env=env)
    return result.returncode


def _force_qt_scale():
    # Keep layout predictable across DPI variants on kiosk screens.
    os.environ.setdefault("QT_SCALE_FACTOR", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
    os.environ.setdefault("QT_SCREEN_SCALE_FACTORS", "1")


def _install_qt_message_filter():
    global _QT_MSG_HANDLER, _QT_PREV_MSG_HANDLER

    from PyQt6.QtCore import qInstallMessageHandler

    def _handler(msg_type, context, message):
        text = str(message or "")
        if "This plugin does not support propagateSizeHints()" in text:
            return

        if _QT_PREV_MSG_HANDLER is not None:
            _QT_PREV_MSG_HANDLER(msg_type, context, message)
            return

        sys.stderr.write(f"{text}\n")

    _QT_MSG_HANDLER = _handler
    _QT_PREV_MSG_HANDLER = qInstallMessageHandler(_QT_MSG_HANDLER)


def _clear_sessions_on_startup():
    """Clear session history file to prevent it from growing too large."""
    try:
        from app.storage import SESSIONS_FILE
        import json
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
    except Exception:
        pass  # Silent fail - session clearing is not critical


def main():
    delegated = _ensure_venv_runtime()
    if delegated is not None:
        return delegated

    _force_qt_scale()
    _install_qt_message_filter()
    _clear_sessions_on_startup()

    from PyQt6.QtWidgets import QApplication, QSplashScreen
    from PyQt6.QtGui import QPixmap, QColor, QFont
    from PyQt6.QtCore import Qt

    from app.settings import app_font, register_montserrat_fonts
    from app.ui.moykaui import RotatedWindow

    app = QApplication(sys.argv)
    register_montserrat_fonts()
    app.setFont(app_font(11, bold=True))

    # Show loading/splash screen
    splash_pixmap = QPixmap(400, 300)
    splash_pixmap.fill(QColor(40, 40, 40))
    splash = QSplashScreen(splash_pixmap)
    
    # Add loading text
    splash.showMessage("Yuklanmoqda...", Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter, QColor(255, 255, 255))
    splash.show()
    app.processEvents()

    window = RotatedWindow()
    window.show_ui()
    splash.finish(window)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
