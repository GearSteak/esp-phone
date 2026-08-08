"""Digivice panel geometry (Waveshare 2\" ST7789 240×320).

With HDMI + SPI extended desktop, Qt defaults fullscreen to the *HDMI*
primary. The SPI panel then shows only the top-left crop of 1080p.
`place_on_panel()` pins Digivice onto the tiny output instead.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple


def _rotation_degrees() -> str:
    env = os.environ.get("ESP_PANEL_ROTATION", "").strip()
    if env:
        return env
    try:
        with open("/etc/esp-handset/panel-rotation", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "0"


def _default_wh() -> Tuple[int, int]:
    w_env = os.environ.get("ESP_HANDSET_W", "").strip()
    h_env = os.environ.get("ESP_HANDSET_H", "").strip()
    if w_env and h_env:
        return int(w_env), int(h_env)
    if _rotation_degrees() in ("90", "270"):
        return 320, 240
    return 240, 320


W, H = _default_wh()


def panel_size_candidates() -> Tuple[Tuple[int, int], ...]:
    return (
        (W, H),
        (H, W),
        (240, 320),
        (320, 240),
    )


def pick_panel_screen():
    """Prefer native Digivice sizes; else SPI-named; else smallest screen."""
    try:
        from PyQt5.QtGui import QGuiApplication
    except ImportError:
        return None
    screens = list(QGuiApplication.screens() or [])
    if not screens:
        return None
    wanted = set(panel_size_candidates())
    for s in screens:
        sz = s.size()
        if (sz.width(), sz.height()) in wanted:
            return s
    for s in screens:
        n = (s.name() or "").upper()
        if any(k in n for k in ("SPI", "DPI", "DSI", "PANEL")):
            return s
    return min(screens, key=lambda s: s.size().width() * s.size().height())


def place_on_panel(win) -> Optional[object]:
    """Fullscreen Digivice on the small panel only (not a crop of HDMI)."""
    screen = pick_panel_screen()
    if screen is None:
        return None
    try:
        win.setScreen(screen)
    except Exception:
        pass
    geo = screen.geometry()
    win.setGeometry(geo)
    print(
        f"[handset] panel screen={screen.name()!r} "
        f"{geo.width()}x{geo.height()}+{geo.x()}+{geo.y()}",
        flush=True,
    )
    return screen
