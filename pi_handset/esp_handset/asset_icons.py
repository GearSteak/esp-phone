"""Shared custom icon and bubble assets for the Digivice UI."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PyQt5.QtGui import QImage, QPixmap

_ASSET_DIR = Path(__file__).resolve().parents[1] / "Assets"
_CACHE: Dict[str, QPixmap] = {}

# Reuse the supplied main-menu artwork for matching submenu concepts.
_ICON_ALIASES = {
    "phone": "calls",
    "contacts": "calls",
    "call_log": "calls",
    "messages": "sms",
    "clock": "time",
    "timer": "timer",
    "calendar": "time",
    "cam_photo": "camera",
    "cam_timer3": "timer",
    "cam_timer10": "timer",
    "cam_video": "media",
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


def icon_for_key(key: str, *, inverted: bool = False) -> Optional[QPixmap]:
    """Return custom artwork for a menu key, optionally RGB-inverted."""
    name = _ICON_ALIASES.get(key, key)
    pixmap = _load(name)
    if pixmap is None or not inverted:
        return pixmap
    cache_key = f"inverted:{name}"
    if cache_key not in _CACHE:
        image = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
        image.invertPixels(QImage.InvertRgb)
        _CACHE[cache_key] = QPixmap.fromImage(image)
    inverted_pixmap = _CACHE[cache_key]
    return inverted_pixmap if not inverted_pixmap.isNull() else None


def bubble_for_state(focused: bool) -> Optional[QPixmap]:
    """Return the supplied 32×32 focused or unfocused bubble."""
    return _load("focused bubble" if focused else "unfocused bubble")
