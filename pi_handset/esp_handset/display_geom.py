"""Digivice multi-output: render once at phone size, scale to every screen.

Correct pipeline (works with or without HDMI / with or without SPI xrandr clone):

  1. Digivice paints at fixed 240×320 (phone UI)
  2. Each QScreen gets a fullscreen host that scales that full frame onto itself

So SPI always gets the *entire* UI (scaled 1:1 or fit), never a crop of 1080p.
HDMI gets the same UI scaled up for the desk monitor.
"""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

from PyQt5.QtCore import Qt, QTimer, QRect
from PyQt5.QtGui import QPainter, QImage, QGuiApplication
from PyQt5.QtWidgets import QWidget, QApplication, QMainWindow


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


class ScaledScreenHost(QWidget):
    """Fullscreen host: paints a scaled copy of the Digivice 240×320 source."""

    def __init__(self, source: QWidget, screen, parent=None):
        super().__init__(parent)
        self._source = source
        self._screen = screen
        self.setWindowTitle("ESP Digivice")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background-color: #000;")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        try:
            self.setScreen(screen)
        except Exception:
            pass
        geo = screen.geometry()
        self.setGeometry(geo)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)
        src = self._source
        if src is None:
            return
        # Ensure source has painted (off-screen ok)
        img: QImage = src.grab().toImage()
        if img.isNull():
            return
        # Scale full Digivice frame into this screen (fill; phone aspect letterbox)
        target = self.rect()
        scaled = img.scaled(
            target.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        x = (target.width() - scaled.width()) // 2
        y = (target.height() - scaled.height()) // 2
        p.drawImage(x, y, scaled)


class MultiScreenPresenter:
    """Keeps source Digivice at phone size; mirrors scaled to all screens."""

    def __init__(self, source: QMainWindow):
        self.source = source
        self.hosts: List[ScaledScreenHost] = []
        self._timer = QTimer()
        self._timer.setInterval(33)  # ~30 fps mirror
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        global W, H
        W, H = _default_wh()

        # Source is the real Digivice UI at native phone resolution
        self.source.setWindowFlags(Qt.Window)
        self.source.setFixedSize(W, H)
        self.source.resize(W, H)
        # Keep off visible desktop so only scaled hosts show (avoids double)
        # Still need show() for proper grab(); put it off-screen
        self.source.move(-10000, -10000)
        self.source.show()
        try:
            self.source.setAttribute(Qt.WA_DontShowOnScreen, False)
        except Exception:
            pass

        self._rebuild_hosts()
        self._timer.start()
        print(
            f"[handset] multi-screen: source {W}x{H}, hosts={len(self.hosts)} "
            f"(scale full UI onto each display)",
            flush=True,
        )
        for h in self.hosts:
            g = h.geometry()
            print(
                f"[handset]   host {h._screen.name()!r} "
                f"{g.width()}x{g.height()}+{g.x()}+{g.y()}",
                flush=True,
            )

    def _rebuild_hosts(self) -> None:
        for h in self.hosts:
            h.close()
            h.deleteLater()
        self.hosts.clear()
        screens = list(QGuiApplication.screens() or [])
        if not screens:
            # No multi-head: show source normally
            self.source.move(0, 0)
            self.source.show()
            print("[handset] no QScreens — source window only", flush=True)
            return
        for screen in screens:
            host = ScaledScreenHost(self.source, screen)
            host.showFullScreen()
            host.raise_()
            self.hosts.append(host)

    def _tick(self) -> None:
        # Keep source processing layout; repaint all hosts
        for h in self.hosts:
            h.update()

    def stop(self) -> None:
        self._timer.stop()
        for h in self.hosts:
            h.close()
        self.hosts.clear()


# --- legacy helpers kept for import compatibility ---

def pick_panel_screen():
    screens = list(QGuiApplication.screens() or [])
    if not screens:
        return None
    wanted = {(W, H), (H, W), (240, 320), (320, 240)}
    for s in screens:
        if (s.size().width(), s.size().height()) in wanted:
            return s
    for s in screens:
        n = (s.name() or "").upper()
        if any(k in n for k in ("SPI", "DPI", "DSI", "PANEL")):
            return s
    return min(screens, key=lambda s: s.size().width() * s.size().height())


def apply_kiosk(win) -> Optional[object]:
    """Start multi-screen scaled presenter (preferred Digivice path)."""
    try:
        win.setAttribute(Qt.WA_StyledBackground, True)
        win.setStyleSheet("QMainWindow { background-color: #0b1a2a; color: #e8eef5; }")
    except Exception:
        pass

    # Prefer multi-scale path unless disabled
    mode = (os.environ.get("ESP_HANDSET_DISPLAY", "scale") or "scale").strip().lower()
    if mode in ("0", "legacy", "single"):
        return _apply_kiosk_legacy(win)

    presenter = MultiScreenPresenter(win)
    presenter.start()
    # Keep reference on window so it isn't GC'd
    win._multi_presenter = presenter  # type: ignore[attr-defined]
    return presenter


def _apply_kiosk_legacy(win) -> None:
    """Old single-window fullscreen (avoid unless debugging)."""
    screen = pick_panel_screen() or QGuiApplication.primaryScreen()
    win.setWindowFlags(Qt.Window)
    if screen is not None:
        try:
            win.setScreen(screen)
        except Exception:
            pass
        win.setGeometry(screen.geometry())
    win.setFixedSize(W, H)
    win.show()
    win.showFullScreen()
