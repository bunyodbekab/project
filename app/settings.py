import os
from PyQt5.QtGui import QFont, QFontDatabase

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
FONT_DIR = os.path.join(BASE_DIR, "font")
ICONS_DIR = os.path.join(BASE_DIR, "icons")

DEFAULT_CONFIG = {
    "services": {
        "KO'PIK": {"display_name": "KO'PIK", "price_per_sec": 200, "duration": 60, "relay_bit": 0},
        "SUV": {"display_name": "SUV", "price_per_sec": 150, "duration": 100, "relay_bit": 1},
        "SHAMPUN": {"display_name": "SHAMPUN", "price_per_sec": 250, "duration": 80, "relay_bit": 2},
        "VOSK": {"display_name": "VOSK", "price_per_sec": 350, "duration": 70, "relay_bit": 3},
        "PENA": {"display_name": "PENA", "price_per_sec": 300, "duration": 50, "relay_bit": 4},
        "OSMOS": {"display_name": "OSMOS", "price_per_sec": 200, "duration": 90, "relay_bit": 5},
        "QURITISH": {"display_name": "QURITISH", "price_per_sec": 100, "duration": 120, "relay_bit": 6},
    },
    "moyka_name": "MOYKA",
    "admin_pin": "1234",
    "total_earned": 0,
    "sessions": [],
    "shift_register": {
        "data_pin": 227,
        "clock_pin": 75,
        "latch_pin": 79,
    },
}

INPUT_GPIO_TO_SERVICE = {
    229: "KO'PIK",
    228: "SUV",
    73: "SHAMPUN",
    70: "VOSK",
    72: "PENA",
    231: "OSMOS",
    232: "QURITISH",
    230: "STOP",
}

CHIP_NAME = "gpiochip1"
LOW_BALANCE = 2000
BLINK_WARN = 10
DEBUG = True

FONT_FAMILY = "Arial"


def register_montserrat_fonts():
    global FONT_FAMILY

    loaded_families = []
    font_files = [
        os.path.join(FONT_DIR, "Montserrat-VariableFont_wght.ttf"),
        os.path.join(FONT_DIR, "Montserrat-Italic-VariableFont_wght.ttf"),
    ]

    for fp in font_files:
        if not os.path.exists(fp):
            continue
        font_id = QFontDatabase.addApplicationFont(fp)
        if font_id != -1:
            loaded_families.extend(QFontDatabase.applicationFontFamilies(font_id))

    for family in loaded_families:
        if "Montserrat" in family:
            FONT_FAMILY = family
            return FONT_FAMILY

    if loaded_families:
        FONT_FAMILY = loaded_families[0]
    return FONT_FAMILY


def app_font(px, bold=False):
    return QFont(FONT_FAMILY, px, QFont.Bold if bold else QFont.Normal)
