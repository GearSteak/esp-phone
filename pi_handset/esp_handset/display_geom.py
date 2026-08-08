"""Digivice panel geometry — prefer SPI panel without blanking the only display."""

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
    # Single screen or no SPI: use primary / first so window still appears
    return QGuiApplication.primaryScreen() or screens[0]


def place_on_panel(win) -> Optional[object]:
    from PyQt5.QtCore import Qt

    screen = pick_panel_screen()
    # Keep Window bit so Qt actually maps a top-level window
    try:
        win.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
    except Exception:
        pass

    if screen is not None:
        try:
            win.setScreen(screen)
        except Exception:
            pass
        geo = screen.geometry()
        # If screen is huge (HDMI only), use phone-sized window, not 1080p fullscreen
        if geo.width() * geo.height() > 300_000:
            win.setGeometry(geo.x(), geo.y(), W, H)
            print(
                f"[handset] large screen {screen.name()!r} "
                f"→ window {W}x{H} (not crop full HD)",
                flush=True,
            )
        else:
            win.setGeometry(geo)
            print(
                f"[handset] panel={screen.name()!r} "
                f"{geo.width()}x{geo.height()}+{geo.x()}+{geo.y()}",
                flush=True,
            )
        try:
            handle = win.windowHandle()
            if handle is not None:
                handle.setScreen(screen)
        except Exception:
            pass
        return screen

    win.setGeometry(0, 0, W, H)
    print(f"[handset] fallback {W}x{H}", flush=True)
    return None


def apply_kiosk(win) -> None:
    from PyQt5.QtWidgets import QApplication

    place_on_panel(win)
    win.show()
    QApplication.processEvents()
    place_on_panel(win)
    win.show()
    win.raise_()
    win.activateWindow()
