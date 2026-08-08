"""Digivice geometry — SPI phone panel is the real canvas.

HDMI should only *mirror* SPI (see digivice-layout.sh), not host the app at 1080p.
Default kiosk target = panel (SPI). Use ESP_HANDSET_TARGET=primary only to debug.
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


def _screens():
    try:
        from PyQt5.QtGui import QGuiApplication

        return list(QGuiApplication.screens() or [])
    except Exception:
        return []


def pick_panel_screen():
    """Prefer native Digivice resolution / SPI-named output."""
    screens = _screens()
    if not screens:
        return None
    wanted = {(W, H), (H, W), (240, 320), (320, 240)}
    for s in screens:
        sz = s.size()
        if (sz.width(), sz.height()) in wanted:
            return s
    for s in screens:
        n = (s.name() or "").upper()
        if any(k in n for k in ("SPI", "DPI", "DSI", "PANEL")):
            return s
    name = os.environ.get("ESP_HANDSET_PANEL_OUTPUT", "")
    if not name:
        try:
            name = open("/tmp/digivice-panel-output", encoding="utf-8").read().strip()
        except OSError:
            name = ""
    if name:
        for s in screens:
            if s.name() == name:
                return s
    # Smallest connected screen
    return min(screens, key=lambda s: s.size().width() * s.size().height())


def pick_kiosk_screen():
    from PyQt5.QtGui import QGuiApplication

    prefer = (os.environ.get("ESP_HANDSET_TARGET", "panel") or "panel").strip().lower()
    primary = QGuiApplication.primaryScreen()
    panel = pick_panel_screen()
    if prefer in ("primary", "hdmi", "main", "desktop"):
        return primary or panel
    # default panel — SPI owns Digivice; HDMI should be a hardware/xrandr mirror
    return panel or primary


def apply_kiosk(win) -> None:
    """Fullscreen Digivice on SPI (or forced target)."""
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QGuiApplication
    from PyQt5.QtWidgets import QApplication

    try:
        win.setAttribute(Qt.WA_StyledBackground, True)
        win.setStyleSheet("QMainWindow { background-color: #0b1a2a; color: #e8eef5; }")
    except Exception:
        pass

    screens = _screens()
    print(f"[handset] screens={len(screens)}", flush=True)
    for s in screens:
        g = s.geometry()
        flag = " PRIMARY" if s is QGuiApplication.primaryScreen() else ""
        print(
            f"[handset]   {s.name()!r} {g.width()}x{g.height()}+{g.x()}+{g.y()}{flag}",
            flush=True,
        )

    screen = pick_kiosk_screen()
    if screen is None:
        win.resize(W, H)
        win.showFullScreen()
        return

    win.setWindowFlags(Qt.Window)
    try:
        win.setScreen(screen)
    except Exception:
        pass
    geo = screen.geometry()
    win.setGeometry(geo)
    print(
        f"[handset] Digivice canvas → {screen.name()!r} "
        f"{geo.width()}x{geo.height()} "
        f"(target={os.environ.get('ESP_HANDSET_TARGET', 'panel')})",
        flush=True,
    )
    win.show()
    win.showFullScreen()
    win.raise_()
    win.activateWindow()
    QApplication.processEvents()

    def _refocus() -> None:
        try:
            h = win.windowHandle()
            if h is not None:
                h.setScreen(screen)
            win.setGeometry(screen.geometry())
            win.showFullScreen()
            win.raise_()
            win.activateWindow()
        except Exception:
            pass

    QTimer.singleShot(100, _refocus)
    QTimer.singleShot(400, _refocus)
