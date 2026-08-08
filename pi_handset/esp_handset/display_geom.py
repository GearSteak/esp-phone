"""Digivice display placement.

Default kiosk target is the **primary** screen (usually HDMI / what you look at).
Set ESP_HANDSET_TARGET=panel to prefer the SPI 2\" panel instead.
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
    return min(screens, key=lambda s: s.size().width() * s.size().height())


def pick_kiosk_screen():
    """primary = what desktop uses (HDMI); panel = tiny SPI."""
    from PyQt5.QtGui import QGuiApplication

    prefer = (os.environ.get("ESP_HANDSET_TARGET", "primary") or "primary").strip().lower()
    screens = _screens()
    primary = QGuiApplication.primaryScreen()
    panel = pick_panel_screen()

    if prefer in ("panel", "spi", "small"):
        return panel or primary
    if prefer in ("primary", "hdmi", "main", "desktop"):
        return primary or panel
    # auto: if panel is distinct from primary, still use primary so user sees UI
    return primary or panel


def apply_kiosk(win) -> None:
    """Fullscreen Digivice on the chosen screen — always force visible on top."""
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QGuiApplication
    from PyQt5.QtWidgets import QApplication

    # Opaque main window (avoids “transparent over desktop” illusion)
    try:
        win.setAttribute(Qt.WA_StyledBackground, True)
        win.setStyleSheet(
            "QMainWindow { background-color: #0b1a2a; color: #e8eef5; }"
        )
    except Exception:
        pass

    screens = _screens()
    print(f"[handset] screens={len(screens)}", flush=True)
    for s in screens:
        g = s.geometry()
        print(
            f"[handset]   {s.name()!r} {g.width()}x{g.height()}+{g.x()}+{g.y()}"
            f"{' PRIMARY' if s is QGuiApplication.primaryScreen() else ''}",
            flush=True,
        )

    screen = pick_kiosk_screen()
    if screen is None:
        print("[handset] no QScreen — fallback showFullScreen", flush=True)
        win.resize(W, H)
        win.showFullScreen()
        return

    # Normal top-level window (no weird flags that Wayland drops)
    win.setWindowFlags(Qt.Window)
    try:
        win.setScreen(screen)
    except Exception:
        pass

    geo = screen.availableGeometry()
    # Use full screen rect when possible
    geo = screen.geometry()
    win.setGeometry(geo)
    print(
        f"[handset] kiosk on {screen.name()!r} "
        f"{geo.width()}x{geo.height()}+{geo.x()}+{geo.y()} "
        f"(ESP_HANDSET_TARGET={os.environ.get('ESP_HANDSET_TARGET', 'primary')})",
        flush=True,
    )

    win.show()
    win.showFullScreen()
    win.raise_()
    win.activateWindow()
    QApplication.processEvents()

    def _refocus() -> None:
        try:
            handle = win.windowHandle()
            if handle is not None and screen is not None:
                handle.setScreen(screen)
            win.setGeometry(screen.geometry())
            win.showFullScreen()
            win.raise_()
            win.activateWindow()
            win.setFocus(Qt.ActiveWindowFocusReason)
            try:
                win.grabKeyboard()
            except Exception:
                pass
            print("[handset] re-raise fullscreen", flush=True)
        except Exception as e:
            print(f"[handset] refocus: {e}", flush=True)

    QTimer.singleShot(100, _refocus)
    QTimer.singleShot(500, _refocus)
    QTimer.singleShot(1500, _refocus)
