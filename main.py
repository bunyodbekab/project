import os
import subprocess
import sys
from pathlib import Path


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


def _enable_remote_debugging():
    """Expose QtWebEngine remote debugging so Chrome devtools can attach."""
    port = os.environ.get("QTWEBENGINE_REMOTE_DEBUGGING")
    if not port:
        port = os.environ.get("WEBENGINE_REMOTE_DEBUG_PORT", "9222")
        os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = port
    print(f"[WEBENGINE] Remote debugging: http://127.0.0.1:{port}")


def main():
    delegated = _ensure_venv_runtime()
    if delegated is not None:
        return delegated

    _enable_remote_debugging()

    from PyQt6.QtWidgets import QApplication

    from app.settings import app_font, register_montserrat_fonts
    from app.ui.user import RotatedWindow

    app = QApplication(sys.argv)
    register_montserrat_fonts()
    app.setFont(app_font(11))

    window = RotatedWindow()
    window.show_ui()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
