"""Digivice panel geometry — always render at native SPI size, not HDMI crop."""

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
    return ((W, H), (H, W), (240, 320), (320, 240))


def pick_panel_screen():
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
    # Prefer file drop from digivice-layout.sh
    try:
        name = open("/tmp/digivice-panel-output", encoding="utf-8").read().strip()
    except OSError:
        name = os.environ.get("ESP_HANDSET_PANEL_OUTPUT", "")
    if name:
        for s in screens:
            if s.name() == name:
                return s
    return min(screens, key=lambda s: s.size().width() * s.size().height())


def place_on_panel(win) -> Optional[object]:
    """Force Digivice window = entire SPI geometry, never 'fullscreen HDMI' crop."""
    from PyQt5.QtCore import Qt

    screen = pick_panel_screen()
    flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    try:
        win.setWindowFlags(flags)
    except Exception:
        pass

    if screen is not None:
        try:
            win.setScreen(screen)
        except Exception:
            pass
        geo = screen.geometry()
        # Hard bind to this output's pixel rect
        win.setGeometry(geo)
        wh = screen.windowHandle() if hasattr(win, "windowHandle") else None
        # After create
        try:
            handle = win.windowHandle()
            if handle is not None:
                handle.setScreen(screen)
        except Exception:
            pass
        print(
            f"[handset] panel={screen.name()!r} "
            f"geo={geo.width()}x{geo.height()}+{geo.x()}+{geo.y()} "
            f"screens={len(__import__('PyQt5.QtGui', fromlist=['QGuiApplication']).QGuiApplication.screens())}",
            flush=True,
        )
        return screen

    # No multihead info — force logical phone size at 0,0
    win.setGeometry(0, 0, W, H)
    print(f"[handset] fallback geometry {W}x{H}", flush=True)
    return None


def apply_kiosk(win) -> None:
    """Show Digivice filling the SPI panel without Qt fullscreen-on-wrong-screen."""
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication

    place_on_panel(win)
    # Prefer normal show + exact geometry over showFullScreen (which often
    # picks HDMI primary and crops SPI).
    win.show()
    QApplication.processEvents()
    place_on_panel(win)
    try:
        handle = win.windowHandle()
        screen = pick_panel_screen()
        if handle is not None and screen is not None:
            handle.setScreen(screen)
            win.setGeometry(screen.geometry())
    except Exception:
        pass
    win.show()
    win.raise_()
    win.activateWindow()
