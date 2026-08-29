"""Shared custom icon and bubble assets for the Digivice UI."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PyQt5.QtGui import QPixmap

_ASSET_DIR = Path(__file__).resolve().parents[1] / "Assets"
_CACHE: Dict[str, QPixmap] = {}

# Reuse the supplied main-menu artwork for matching submenu concepts.
_ICON_ALIASES = {
    "phone": "calls",
    "contacts": "calls",
    "call_log": "calls",
    "messages": "sms",
    "clock": "time",
    "timer": "time",
    "calendar": "time",
    "cam_photo": "camera",
    "cam_timer3": "time",
    "cam_timer10": "time",
    "cam_video": "camera",
    "cam_pano": "camera",
    "set_system": "settings",
    "set_display": "settings",
    "set_network": "settings",
    "set_accounts": "settings",
    "set_security": "settings",
    "set_debug": "settings",
    "set_appearance": "settings",
    "set_orientation": "settings",
    "set_mouse": "settings",
    "set_update": "settings",
    "set_power": "settings",
    "set_about": "settings",
    "acct_sip": "calls",
    "acct_email": "email",
}


def _load(name: str) -> Optional[QPixmap]:
    if name not in _CACHE:
        path = _ASSET_DIR / f"{name}.png"
        pixmap = QPixmap(str(path)) if path.is_file() else QPixmap()
        _CACHE[name] = pixmap
    pixmap = _CACHE[name]
    return pixmap if not pixmap.isNull() else None


def icon_for_key(key: str) -> Optional[QPixmap]:
    """Return custom artwork for a menu key, or None for glyph fallback."""
    return _load(_ICON_ALIASES.get(key, key))


def bubble_for_state(focused: bool) -> Optional[QPixmap]:
    """Return the supplied 32×32 focused or unfocused bubble."""
    return _load("focused bubble" if focused else "unfocused bubble")
