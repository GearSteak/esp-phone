"""Digivice on SPI panel when present; HDMI stays a normal desktop head.

Layout script enables HDMI first (never scale-from). Digivice fullscreen
on phone-sized / Unknown panel if available, otherwise primary screen.
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

# mipi-dbi-spi often appears as Unknown19-1 under KMS (not "SPI-1")
_PANEL_NAME_MARKERS = ("SPI", "DPI", "DSI", "PANEL", "UNKNOWN")


def _screens():
    try:
        from PyQt5.QtGui import QGuiApplication

        return list(QGuiApplication.screens() or [])
    except Exception:
        return []


def is_panel_name(name: str) -> bool:
    n = (name or "").upper()
    if any(k in n for k in ("HDMI", "DP-", "DISPLAYPORT", "VGA", "VIRTUAL")):
        return False
    return any(k in n for k in _PANEL_NAME_MARKERS)


def pick_panel_screen():
    """Prefer 240×320 / Unknown* / SPI-named / smallest screen."""
    screens = _screens()
    if not screens:
        return None

    # Explicit name from digivice-layout
    name = os.environ.get("ESP_HANDSET_PANEL_OUTPUT", "").strip()
    if not name:
        try:
            name = open("/tmp/digivice-panel-output", encoding="utf-8").read().strip()
        except OSError:
            name = ""
    if name:
        for s in screens:
            if s.name() == name:
                return s

    wanted = {(W, H), (H, W), (240, 320), (320, 240)}
    for s in screens:
        if (s.size().width(), s.size().height()) in wanted:
            return s

    for s in screens:
        if is_panel_name(s.name() or ""):
            return s

    if len(screens) == 1:
        return screens[0]
    return min(screens, key=lambda s: s.size().width() * s.size().height())


def apply_kiosk(win) -> Optional[object]:
    """Fullscreen Digivice on the phone panel. Primary path that worked on SPI."""
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QGuiApplication
    from PyQt5.QtWidgets import QApplication

    global W, H
    W, H = _default_wh()

    try:
        win.setAttribute(Qt.WA_StyledBackground, True)
        win.setStyleSheet(
            "QMainWindow { background-color: #0b1a2a; color: #e8eef5; }"
        )
    except Exception:
        pass

    screens = _screens()
    print(f"[handset] screens={len(screens)} want={W}x{H}", flush=True)
    for s in screens:
        g = s.geometry()
        p = " PRIMARY" if s is QGuiApplication.primaryScreen() else ""
        tag = " PANEL" if is_panel_name(s.name() or "") else ""
        print(
            f"[handset]   {s.name()!r} {g.width()}x{g.height()}+{g.x()}+{g.y()}{p}{tag}",
            flush=True,
        )

    screen = pick_panel_screen()
    # Real window flags — not frameless multi-host ghosts
    win.setWindowFlags(Qt.Window)

    if screen is None:
        print("[handset] no QScreen — showFullScreen on default", flush=True)
        win.resize(W, H)
        win.showFullScreen()
        return None

    try:
        win.setScreen(screen)
    except Exception:
        pass

    geo = screen.geometry()
    win.setGeometry(geo)
    print(
        f"[handset] Digivice ON PANEL {screen.name()!r} "
        f"{geo.width()}x{geo.height()}+{geo.x()}+{geo.y()}",
        flush=True,
    )

    if geo.width() * geo.height() > 200_000:
        print(
            "[handset] WARN: bound screen is huge (looks like HDMI). "
            "SPI may be missing as QScreen — check digivice-layout / xrandr "
            "for Unknown19-1 or SPI connected primary 240x320",
            flush=True,
        )

    win.show()
    win.showFullScreen()
    win.raise_()
    win.activateWindow()
    QApplication.processEvents()

    def _pin() -> None:
        try:
            scr = pick_panel_screen() or screen
            h = win.windowHandle()
            if h is not None and scr is not None:
                h.setScreen(scr)
                win.setGeometry(scr.geometry())
            win.showFullScreen()
            win.raise_()
            win.activateWindow()
            print(
                f"[handset] re-pin → {(scr.name() if scr else '?')!r}",
                flush=True,
            )
        except Exception as e:
            print(f"[handset] re-pin: {e}", flush=True)

    QTimer.singleShot(200, _pin)
    QTimer.singleShot(800, _pin)
    QTimer.singleShot(2000, _pin)
    return None
