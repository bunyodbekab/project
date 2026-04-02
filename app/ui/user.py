"""Compatibility exports for UI modules."""

from .admin import AdminDialog, PinDialog
from .common import (
    ClickableFrame,
    PauseButton,
    RotatedContainer,
    ServiceButton,
    THEME_COLORS,
    _format_money,
    _icon_path,
    _theme_palette,
    _to_int,
)
from .moykaui import MoykaUI, RotatedWindow

__all__ = [
    "AdminDialog",
    "PinDialog",
    "ClickableFrame",
    "PauseButton",
    "RotatedContainer",
    "ServiceButton",
    "THEME_COLORS",
    "_format_money",
    "_icon_path",
    "_theme_palette",
    "_to_int",
    "MoykaUI",
    "RotatedWindow",
]

