import os
from PyQt6.QtGui import QFont, QFontDatabase

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
FONT_DIR = os.path.join(BASE_DIR, "font")
ICONS_DIR = os.path.join(BASE_DIR, "icons")

DEFAULT_CONFIG = {
    "services": {
        "XIZMAT1": {"display_name": "SUV", "price_per_sec": 200, "duration": 60, "gpio_out": 227, "icon": "suv.png", "theme": "suv", "active": True},
        "XIZMAT2": {"display_name": "OSMOS", "price_per_sec": 150, "duration": 100, "gpio_out": 75, "icon": "osmos.png", "theme": "osmos", "active": True},
        "XIZMAT3": {"display_name": "AKTIV PENA", "price_per_sec": 250, "duration": 80, "gpio_out": 79, "icon": "aktiv.png", "theme": "aktiv", "active": True},
        "XIZMAT4": {"display_name": "PENA", "price_per_sec": 350, "duration": 70, "gpio_out": 78, "icon": "pena.png", "theme": "pena", "active": True},
        "XIZMAT5": {"display_name": "NANO", "price_per_sec": 300, "duration": 50, "gpio_out": 71, "icon": "nano.png", "theme": "nano", "active": True},
        "XIZMAT6": {"display_name": "VOSK", "price_per_sec": 200, "duration": 90, "gpio_out": 233, "icon": "vosk.png", "theme": "vosk", "active": True},
        "XIZMAT7": {"display_name": "XIZMAT 7", "price_per_sec": 100, "duration": 120, "gpio_out": 74, "icon": "suv.png", "theme": "suv", "active": False},
    },
    "moyka_name": "MOYKA",
    "admin_pin": "1234",
    "admin_pin_alt": "5678",
    "total_earned": 0,
    "show_icons": True,
    "bonus": {"percent": 0, "threshold": 0},
    "pause": {"freeSeconds": 5, "paidSecondsPer5000": 120},
}

# 1:1 mapping with up to 7 physical buttons (PUL = coin/acceptor pulse)
INPUT_GPIO_TO_SERVICE = {
    229: "PUL",        # pul qabul qiluvchi kiritma (har impuls = 1000 so'm)
    228: "XIZMAT1",
    73: "XIZMAT2",
    70: "XIZMAT3",
    72: "XIZMAT4",
    231: "XIZMAT5",
    232: "XIZMAT6",
    230: "STOP",
}

CHIP_NAME = "gpiochip1"
LOW_BALANCE = 2000
BLINK_WARN = 10
DEBUG = False

FONT_FAMILY = "font/Montserrat/static"


def register_montserrat_fonts():
    global FONT_FAMILY

    loaded_families = []
    font_files = [
        os.path.join(FONT_DIR, "Montserrat-Black.ttf"),
        os.path.join(FONT_DIR, "Montserrat-Bold.ttf"),
        os.path.join(FONT_DIR, "Montserrat-ExtraBold.ttf"),
        os.path.join(FONT_DIR, "Montserrat-Regular.ttf"),
        os.path.join(FONT_DIR, "Montserrat-SemiBold.ttf"),
        os.path.join(FONT_DIR, "Montserrat-Thin.ttf"),
        os.path.join(FONT_DIR, "Montserrat-BlackItalic.ttf"),
        os.path.join(FONT_DIR, "Montserrat-BoldItalic.ttf"),
        os.path.join(FONT_DIR, "Montserrat-ExtraBoldItalic.ttf"),
        os.path.join(FONT_DIR, "Montserrat-Italic.ttf"),
        os.path.join(FONT_DIR, "Montserrat-Light.ttf"),
        os.path.join(FONT_DIR, "Montserrat-LightItalic.ttf"),
        os.path.join(FONT_DIR, "Montserrat-Medium.ttf"),
        os.path.join(FONT_DIR, "Montserrat-MediumItalic.ttf"),
        os.path.join(FONT_DIR, "Montserrat-SemiBoldItalic.ttf"),
        os.path.join(FONT_DIR, "Montserrat-ThinItalic.ttf"),
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
    weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
    return QFont(FONT_FAMILY, px, weight)
