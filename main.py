import sys
import gpiod
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton,
    QLabel, QVBoxLayout, QGridLayout, QGraphicsView, QGraphicsScene
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

# ─────────────────────────────────────────────
# GPIO sozlamalari
# ─────────────────────────────────────────────
CHIP_NAME = "gpiochip0"

# Tugma nomi → GPIO pin (ketma-ketlik: KO'PIK=227, SUV=75, SHAMPUN=79, VOSK=78, PENA=71, OSMOS=233, QURITISH=74)
PIN_MAP = {
    "KO'PIK":   227,
    "SUV":       75,
    "SHAMPUN":   79,
    "VOSK":      78,
    "PENA":      71,
    "OSMOS":    233,
    "QURITISH":  74,
}

# Xizmat konfiguratsiyasi: (so'm/soniya, umumiy soniya)
SERVICE_CONFIG = {
    "KO'PIK":   (200,  60),
    "SUV":      (150, 100),   # → 01:40 dan orqaga
    "SHAMPUN":  (250,  80),
    "VOSK":     (350,  70),
    "PENA":     (300,  50),   # → 00:50 dan orqaga
    "OSMOS":    (200,  90),
    "QURITISH": (100, 120),
}

LOW_BALANCE = 2000   # 2000 so'mdan kam → blink
BLINK_WARN  = 10     # vaqt tugashiga 10 soniya → blink


# ─────────────────────────────────────────────
# GPIO yordamchi sinf
# ─────────────────────────────────────────────
class GPIOController:
    def __init__(self):
        self.chip = None
        self.lines = {}
        try:
            self.chip = gpiod.Chip(CHIP_NAME)
            for name, pin in PIN_MAP.items():
                line = self.chip.get_line(pin)
                line.request(
                    consumer="moyka",
                    type=gpiod.LINE_REQ_DIR_OUT,
                    default_vals=[0]
                )
                self.lines[name] = line
            print("GPIO tayyor.")
        except Exception as e:
            print(f"GPIO xatosi (simulyatsiya rejimida ishlamoqda): {e}")
            self.chip = None

    def set_pin(self, name, value):
        if name in self.lines:
            try:
                self.lines[name].set_value(int(value))
            except Exception as e:
                print(f"GPIO set xatosi [{name}]: {e}")
        else:
            print(f"[SIM] GPIO {name} → {value}")

    def all_off(self):
        for name in list(self.lines.keys()):
            self.set_pin(name, 0)

    def cleanup(self):
        self.all_off()
        if self.chip:
            try:
                self.chip.close()
            except Exception:
                pass


# ─────────────────────────────────────────────
# Asosiy UI
# ─────────────────────────────────────────────
class MoykaUI(QWidget):
    def __init__(self, width, height):
        super().__init__()
        self.w = width
        self.h = height
        self.setFixedSize(width, height)

        # GPIO
        self.gpio = GPIOController()

        # Holat
        self.balance         = 0
        self.remaining_sec   = 0
        self.cost_per_sec    = 0
        self.active_service  = None
        self.is_running      = False
        self.blink_state     = False
        self.show_timer_mode = False

        # Taymerlar
        self.service_timer = QTimer(self)
        self.service_timer.setInterval(1000)
        self.service_timer.timeout.connect(self._tick)

        self.blink_timer = QTimer(self)
        self.blink_timer.setInterval(400)
        self.blink_timer.timeout.connect(self._blink)

        # Stil
        self.setStyleSheet("""
            QWidget { background-color: #0f172a; }
            QLabel  { color: white; }
            QPushButton {
                background-color: #1e293b;
                color: white;
                border-radius: 25px;
                border: 3px solid #334155;
            }
            QPushButton:hover   { background-color: #2563eb; border: 3px solid #3b82f6; }
            QPushButton:pressed { background-color: #1d4ed8; }
        """)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(10)
        self.main_layout.setContentsMargins(30, 20, 30, 20)

        # Header: pul yoki vaqt
        self.header_label = QLabel("0 so'm")
        self.header_label.setAlignment(Qt.AlignCenter)
        self.header_label.setFont(QFont("Arial", int(height * 0.07), QFont.Bold))
        self.header_label.setStyleSheet("color: #38bdf8;")
        self.main_layout.addWidget(self.header_label)

        # Xizmat nomi / narxi
        self.service_label = QLabel("")
        self.service_label.setAlignment(Qt.AlignCenter)
        self.service_label.setFont(QFont("Arial", int(height * 0.03)))
        self.service_label.setStyleSheet("color: #94a3b8;")
        self.main_layout.addWidget(self.service_label)

        # Grid
        self.grid = QGridLayout()
        self.grid.setSpacing(15)

        names = [
            "KO'PIK",  "SUV",
            "SHAMPUN", "VOSK",
            "PENA",    "OSMOS",
            "QURITISH","STOP",
        ]
        positions = [(i, j) for i in range(4) for j in range(2)]
        btn_height    = int(height * 0.14)
        btn_font_size = int(height * 0.028)

        self.btn_widgets = {}
        for pos, name in zip(positions, names):
            btn = QPushButton(name)
            btn.setFont(QFont("Arial", btn_font_size, QFont.Bold))
            btn.setMinimumHeight(btn_height)
            btn.clicked.connect(lambda checked, n=name: self.button_clicked(n))
            self.grid.addWidget(btn, *pos)
            self.btn_widgets[name] = btn

        # STOP tugmasini qizil
        self.btn_widgets["STOP"].setStyleSheet("""
            QPushButton {
                background-color: #ff2222;
                color: white;
                border-radius: 25px;
                border: 3px solid #ff8888;
            }
            QPushButton:hover   { background-color: #ff4444; }
            QPushButton:pressed { background-color: #cc0000; }
        """)

        self.main_layout.addLayout(self.grid)
        self._update_header()

    # ─── Enter = 5000 so'm ───
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._add_balance()

    def _add_balance(self):
        self.balance += 5000
        if not self.is_running:
            self._update_header()
        # Agar blink to'xtagan bo'lsa qayta tekshir
        self._check_blink()
        print(f"Balance: {self.balance} so'm")

    # ─── Tugma bosildi ───
    def button_clicked(self, name):
        if name == "STOP":
            self._stop_service()
            return

        if name not in SERVICE_CONFIG:
            return

        # Balans yetarlimi?
        if self.balance < LOW_BALANCE:
            self._flash_low_balance()
            return

        cost, duration = SERVICE_CONFIG[name]

        # Avvalgi xizmatni o'chir
        if self.is_running and self.active_service:
            self._deactivate_pin(self.active_service)

        self.active_service  = name
        self.cost_per_sec    = cost
        self.remaining_sec   = duration
        self.is_running      = True
        self.show_timer_mode = True

        self._activate_pin(name)
        self.service_label.setText(f"{name}  |  {cost} so'm/s")
        self.service_timer.start()
        self._update_header()
        self._check_blink()

    # ─── Har 1 soniyada ───
    def _tick(self):
        if not self.is_running:
            return

        charge         = min(self.cost_per_sec, self.balance)
        self.balance  -= charge
        self.balance   = max(0, self.balance)
        self.remaining_sec -= 1

        if self.balance <= 0 or self.remaining_sec <= 0:
            self._stop_service()
            return

        self._update_header()
        self._check_blink()

    # ─── STOP = pausa: vaqtdan puliga qaytadi ───
    def _stop_service(self):
        self.is_running      = False
        self.show_timer_mode = False
        self.service_timer.stop()
        self.blink_timer.stop()
        self.blink_state = False

        if self.active_service:
            self._deactivate_pin(self.active_service)
            self.active_service = None

        self.service_label.setText("")
        self._update_header()
        self._reset_header_color()

    # ─── Header yangilash ───
    def _update_header(self):
        if self.show_timer_mode and self.is_running:
            mins = self.remaining_sec // 60
            secs = self.remaining_sec % 60
            self.header_label.setText(f"{mins:02d}:{secs:02d}")
        else:
            bal_str = f"{self.balance:,}".replace(",", " ")
            self.header_label.setText(f"{bal_str} so'm")

    # ─── Blink tekshiruv ───
    def _check_blink(self):
        should_blink = (
            self.balance < LOW_BALANCE or
            (self.is_running and self.remaining_sec <= BLINK_WARN)
        )
        if should_blink and not self.blink_timer.isActive():
            self.blink_timer.start()
        elif not should_blink and self.blink_timer.isActive():
            self.blink_timer.stop()
            self._reset_header_color()

    def _blink(self):
        self.blink_state = not self.blink_state
        color = "#ff2222" if self.blink_state else "white"
        self.header_label.setStyleSheet(
            f"color: {color}; background-color: transparent;"
        )

    def _reset_header_color(self):
        self.header_label.setStyleSheet("color: #38bdf8;")

    def _flash_low_balance(self):
        self.header_label.setStyleSheet("color: #ff2222;")
        QTimer.singleShot(700, self._reset_header_color)

    # ─── GPIO ───
    def _activate_pin(self, name):
        self.gpio.all_off()
        if name in PIN_MAP:
            self.gpio.set_pin(name, 1)

    def _deactivate_pin(self, name):
        if name in PIN_MAP:
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

        screen_geo = QApplication.primaryScreen().geometry()
        screen_w   = screen_geo.width()
        screen_h   = screen_geo.height()

        self.setScene(QGraphicsScene(self))
        self.setStyleSheet("background-color: #0f172a; border: none;")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(0)

        self.ui = MoykaUI(screen_h, screen_w)
        self.proxy = self.scene().addWidget(self.ui)

        center_x = screen_h / 2
        center_y = screen_w / 2
        self.proxy.setTransformOriginPoint(center_x, center_y)
        self.proxy.setRotation(-90)

        x_offset = (screen_w - screen_h) / 2
        y_offset = (screen_h - screen_w) / 2
        self.proxy.setPos(x_offset, y_offset)

    def show_ui(self):
        self.showFullScreen()

    def keyPressEvent(self, event):
        self.ui.keyPressEvent(event)


# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RotatedWindow()
    window.show_ui()
    sys.exit(app.exec_())