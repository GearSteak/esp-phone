"""Digivice multi-output: one phone canvas, full-frame on every large display.

Never leave a floating 240×320 chip on HDMI (that was the “small portion” bug).

Pipeline:
  1. PhoneShell paints at fixed W×H (source).
  2. Every LARGE / primary screen gets a fullscreen host that scales the
     *entire* source (KeepAspectRatio, letterbox) — full Digivice UI, not crop.
  3. Optional ST7789 userspace mirror: blit source 1:1 over SPI (Instructables).

ESP_HANDSET_SPI_BACKEND=userspace|drm|auto  (default auto / flag file)
"""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

from PyQt5.QtCore import Qt, QTimer, QPoint, QEvent, QRect
from PyQt5.QtGui import QPainter, QImage, QGuiApplication, QMouseEvent
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
PHONE_AREA_MAX = 200_000


def _screens():
    try:
        return list(QGuiApplication.screens() or [])
    except Exception:
        return []


def _area(screen) -> int:
    s = screen.size()
    return max(1, s.width() * s.height())


def is_large_screen(screen) -> bool:
    return _area(screen) > PHONE_AREA_MAX


def _backend() -> str:
    b = (os.environ.get("ESP_HANDSET_SPI_BACKEND", "auto") or "auto").strip().lower()
    if b in ("user", "userspace", "spidev", "mirror", "fbcp"):
        return "userspace"
    if b in ("drm", "kms", "panel"):
        return "drm"
    if os.path.isfile("/etc/esp-handset/spi-userspace"):
        return "userspace"
    if os.path.exists("/dev/spidev0.0"):
        return "userspace"
    return "drm"


class ScaledScreenHost(QWidget):
    """Fullscreen: draw full Digivice frame scaled to this screen (no crop)."""

    def __init__(self, source: QWidget, screen, parent=None):
        super().__init__(parent)
        self._source = source
        self._screen = screen
        self.setWindowTitle("ESP Digivice")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background-color: #000;")
        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setFocusPolicy(Qt.StrongFocus)
        try:
            self.setScreen(screen)
        except Exception:
            pass
        self.setGeometry(screen.geometry())

    def place(self) -> None:
        g = self._screen.geometry()
        self.setGeometry(g)
        self.show()
        QApplication.processEvents()
        try:
            h = self.windowHandle()
            if h is not None:
                h.setScreen(self._screen)
                h.setGeometry(g)
        except Exception:
            pass
        self.showFullScreen()
        self.setGeometry(g)
        self.raise_()
        print(
            f"[handset] HDMI/host FULL {self._screen.name()!r} "
            f"{g.width()}x{g.height()}+{g.x()}+{g.y()}",
            flush=True,
        )

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._source is not None:
            QApplication.sendEvent(self._source, event)
            if event.isAccepted():
                return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._map_mouse(event, True)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._map_mouse(event, False)

    def _map_mouse(self, event, press: bool) -> None:
        src = self._source
        if src is None:
            return
        tw, th = max(1, self.width()), max(1, self.height())
        sw, sh = max(1, src.width()), max(1, src.height())
        scale = min(tw / sw, th / sh)
        dw, dh = int(sw * scale), int(sh * scale)
        ox, oy = (tw - dw) // 2, (th - dh) // 2
        x, y = event.x() - ox, event.y() - oy
        if x < 0 or y < 0 or x >= dw or y >= dh:
            return
        local = QPoint(int(x / scale), int(y / scale))
        et = QEvent.MouseButtonPress if press else QEvent.MouseButtonRelease
        me = QMouseEvent(et, local, event.button(), event.buttons(), event.modifiers())
        child = src.childAt(local)
        QApplication.sendEvent(child if child is not None else src, me)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)
        src = self._source
        if src is None:
            return
        img: QImage = src.grab().toImage()
        if img.isNull():
            return
        # Full frame only — never crop top-left of a larger source
        scaled = img.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        p.drawImage(x, y, scaled)


class SpiUserspaceMirror:
    def __init__(self, source: QWidget):
        self.source = source
        self._timer = None
        self._st = None
        self._active = False

    def start(self) -> bool:
        try:
            from esp_handset import st7789_spi as st
        except ImportError:
            from . import st7789_spi as st  # type: ignore

        if not st.init():
            print(
                "[handset] ST7789 userspace failed — need spidev "
                "(sudo digivice-install-spi-userspace && reboot)",
                flush=True,
            )
            return False
        try:
            st.fill(255, 0, 0)
        except Exception:
            pass
        self._st = st
        self._active = True
        self._timer = QTimer()
        self._timer.setInterval(int(os.environ.get("ESP_ST7789_FPS_MS", "50")))
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        print("[handset] SPI mirror ON (full Digivice → ST7789)", flush=True)
        return True

    def _tick(self) -> None:
        if not self._active or self._st is None:
            return
        try:
            self._st.blit_qimage(self.source.grab().toImage())
        except Exception as e:
            print(f"[handset] spi tick: {e}", flush=True)

    def stop(self) -> None:
        self._active = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        try:
            if self._st is not None:
                # Leave panel as-is so desktop_spi_mirror can take over without black flash
                self._st.close(blank_panel=False)
        except Exception as e:
            print(f"[handset] spi stop: {e}", flush=True)
        self._st = None
        print("[handset] SPI mirror stopped (hand off SPI)", flush=True)

class MultiDisplayKiosk:
    """Source W×H + fullscreen scale hosts on large screens + optional SPI."""

    def __init__(self, source: QMainWindow):
        self.source = source
        self.hosts: List[ScaledScreenHost] = []
        self.spi: Optional[SpiUserspaceMirror] = None
        self._timer = QTimer()
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        global W, H
        W, H = _default_wh()
        backend = _backend()
        print(f"[handset] kiosk start backend={backend} canvas={W}x{H}", flush=True)

        # Source = logical Digivice only — NOT a visible full-screen steal on HDMI
        self.source.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.Tool)
        try:
            self.source.setAttribute(Qt.WA_StyledBackground, True)
            self.source.setStyleSheet(
                "QMainWindow { background-color: #0b1a2a; color: #e8eef5; }"
            )
        except Exception:
            pass
        self.source.setFixedSize(W, H)
        self.source.resize(W, H)

        primary = QGuiApplication.primaryScreen()
        # Park just off the primary corner so it stays mapped for grab() without
        # becoming the "small window" the user stares at (hosts cover the desk).
        if primary is not None:
            g = primary.geometry()
            # Under the host, top-left of primary — hosts stay-on-top cover it
            self.source.move(g.x(), g.y())
        self.source.show()
        self.source.lower()

        screens = _screens()
        for s in screens:
            g = s.geometry()
            print(
                f"[handset]   screen {s.name()!r} "
                f"{g.width()}x{g.height()}+{g.x()}+{g.y()}",
                flush=True,
            )

        # Fullscreen host on every large screen (HDMI). Phone-sized DRM screens
        # also get a host so SPI DRM gets full UI if it ever has a mode.
        for s in screens:
            host = ScaledScreenHost(self.source, s)
            host.place()
            self.hosts.append(host)

        if not self.hosts:
            # No multi-screen API — source must fill alone
            print("[handset] no QScreens for hosts — source fullscreen fallback", flush=True)
            try:
                self.source.setMinimumSize(0, 0)
                self.source.setMaximumSize(16777215, 16777215)
            except Exception:
                pass
            self.source.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
            self.source.showFullScreen()

        if backend == "userspace":
            self.spi = SpiUserspaceMirror(self.source)
            self.spi.start()
        elif backend == "auto":
            # try userspace if spidev present
            if os.path.exists("/dev/spidev0.0"):
                self.spi = SpiUserspaceMirror(self.source)
                self.spi.start()

        self._timer.start()
        # Keep hosts on top of the small source window
        QTimer.singleShot(100, self._raise_hosts)
        QTimer.singleShot(500, self._raise_hosts)
        QTimer.singleShot(1500, self._raise_hosts)

    def _raise_hosts(self) -> None:
        self.source.lower()
        for h in self.hosts:
            try:
                h.raise_()
                h.reassert if False else None
            except Exception:
                pass
            try:
                g = h._screen.geometry()
                h.setGeometry(g)
                h.showFullScreen()
                h.raise_()
            except Exception:
                pass

    def _tick(self) -> None:
        for h in self.hosts:
            h.update()

    def stop(self) -> None:
        self._timer.stop()
        if self.spi is not None:
            self.spi.stop()
        for h in self.hosts:
            h.close()
        self.hosts.clear()


def apply_kiosk(win) -> Optional[object]:
    ctl = MultiDisplayKiosk(win)
    ctl.start()
    win._multi_presenter = ctl  # type: ignore[attr-defined]
    win._kiosk_controller = ctl  # type: ignore[attr-defined]
    return ctl
