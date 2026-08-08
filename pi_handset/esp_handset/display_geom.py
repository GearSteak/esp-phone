"""Digivice: paint only the SPI phone canvas (never 1080p crop viewport)."""

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
    screens = _screens()
    if not screens:
        return None
    # Prefer exactly phone modes
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
    # After digivice-layout, often only one screen left — use it
    if len(screens) == 1:
        return screens[0]
    return min(screens, key=lambda s: s.size().width() * s.size().height())


def apply_kiosk(win) -> None:
    """Fill the phone canvas. Prefer not using multi-head partial geometry."""
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QGuiApplication
    from PyQt5.QtWidgets import QApplication

    # Re-read W/H from env after digivice-layout
    global W, H
    W, H = _default_wh()

    try:
        win.setAttribute(Qt.WA_StyledBackground, True)
        win.setStyleSheet("QMainWindow { background-color: #0b1a2a; color: #e8eef5; }")
    except Exception:
        pass

    screens = _screens()
    print(f"[handset] screens={len(screens)} want={W}x{H}", flush=True)
    for s in screens:
        g = s.geometry()
        p = " PRIMARY" if s is QGuiApplication.primaryScreen() else ""
        print(
            f"[handset]   {s.name()!r} {g.width()}x{g.height()}+{g.x()}+{g.y()}{p}",
            flush=True,
        )

    screen = pick_panel_screen()
    win.setWindowFlags(Qt.Window)

    if screen is not None:
        try:
            win.setScreen(screen)
        except Exception:
            pass
        geo = screen.geometry()
        # If layout failed and screen is still huge, force phone widget size
        # at top-left of that screen (still wrong for SPI crop-as-viewport,
        # but digivice-layout should have made screen phone-sized).
        if geo.width() > W + 40 or geo.height() > H + 40:
            print(
                f"[handset] WARN screen still large {geo.width()}x{geo.height()} "
                f"— forcing {W}x{H} window (run digivice-layout / use X11)",
                flush=True,
            )
            win.setGeometry(geo.x(), geo.y(), W, H)
            win.setFixedSize(W, H)
        else:
            win.setGeometry(geo)
            try:
                win.setFixedSize(geo.size())
            except Exception:
                pass
        print(
            f"[handset] Digivice → {screen.name()!r} "
            f"win={win.width()}x{win.height()}",
            flush=True,
        )
    else:
        win.setFixedSize(W, H)
        win.setGeometry(0, 0, W, H)

    win.show()
    # Fullscreen only when the output itself is phone-sized
    if screen is not None:
        g = screen.geometry()
        if g.width() <= W + 40 and g.height() <= H + 40:
            win.showFullScreen()
    win.raise_()
    win.activateWindow()
    QApplication.processEvents()

    def _again() -> None:
        try:
            if screen is not None:
                h = win.windowHandle()
                if h is not None:
                    h.setScreen(screen)
                g = screen.geometry()
                if g.width() <= W + 40 and g.height() <= H + 40:
                    win.setGeometry(g)
                    win.showFullScreen()
                else:
                    win.setGeometry(g.x(), g.y(), W, H)
            win.raise_()
            win.activateWindow()
        except Exception:
            pass

    QTimer.singleShot(150, _again)
    QTimer.singleShot(600, _again)
