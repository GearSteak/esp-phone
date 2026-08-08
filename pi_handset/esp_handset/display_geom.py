"""Digivice multi-output display.

Canonical pipeline:
  1. Digivice always paints a fixed 240×320 (phone) UI.
  2. That real window lives on the SPI panel when Qt can see it (native 1:1).
  3. Every *large* screen (HDMI) gets a fullscreen host that scales the full
     240×320 frame (no crop).

If SPI is not a QScreen, we only get HDMI — run digivice-layout so SPI is on.
"""

from __future__ import annotations

import os
import subprocess
from typing import List, Optional, Tuple

from PyQt5.QtCore import Qt, QTimer, QPoint, QEvent
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

# Screens larger than this area (px) get a *scaled* copy of the phone UI.
# SPI 240×320 = 76800; 320×240 = 76800; 480×320 ≈ 150k; HDMI is millions.
PHONE_AREA_MAX = 200_000

# mipi-dbi-spi often shows as Unknown19-1 (not "SPI-…") under KMS/xrandr/Qt.
_PANEL_NAME_MARKERS = (
    "SPI",
    "DPI",
    "DSI",
    "PANEL",
    "UNKNOWN",  # DRM generic name for SPI bipanel (e.g. Unknown19-1)
)


def _area(screen) -> int:
    s = screen.size()
    return max(1, s.width() * s.height())


def _screens():
    return list(QGuiApplication.screens() or [])


def is_panel_name(name: str) -> bool:
    n = (name or "").upper()
    if any(k in n for k in ("HDMI", "DP-", "DISPLAYPORT", "VGA", "VIRTUAL")):
        return False
    return any(k in n for k in _PANEL_NAME_MARKERS)


def is_phone_screen(screen) -> bool:
    if is_panel_name(screen.name() or ""):
        return True
    if _area(screen) <= PHONE_AREA_MAX:
        return True
    return False


def pick_panel_screen():
    """Prefer small DRM panel (SPI / Unknown*-N) for the real Digivice window."""
    screens = _screens()
    if not screens:
        return None
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
    by_size = [
        s
        for s in screens
        if (s.size().width(), s.size().height()) in wanted
    ]
    if by_size:
        # Prefer Unknown*/SPI name among exact phone resolutions
        named = [s for s in by_size if is_panel_name(s.name() or "")]
        return min(named or by_size, key=_area)

    for s in screens:
        if is_panel_name(s.name() or ""):
            return s

    small = [s for s in screens if is_phone_screen(s)]
    if small:
        return min(small, key=_area)
    return None


def ensure_spi_via_xrandr() -> None:
    """Best-effort: turn SPI on before Qt builds screen list (and on demand)."""
    if os.environ.get("ESP_HANDSET_SKIP_LAYOUT", "").strip() in ("1", "true", "yes"):
        return
    display = os.environ.get("DISPLAY", ":0")
    script = "/usr/local/bin/digivice-layout"
    if not os.path.isfile(script):
        script = os.path.join(
            os.path.dirname(__file__), "..", "session", "digivice-layout.sh"
        )
    if not os.path.isfile(script):
        return
    try:
        subprocess.run(
            ["bash", script],
            env={**os.environ, "DISPLAY": display, "ESP_HANDSET_MIRROR": "0"},
            timeout=15,
            check=False,
            capture_output=True,
        )
    except Exception as e:
        print(f"[handset] ensure_spi: {e}", flush=True)


class ScaledScreenHost(QWidget):
    """Fullscreen: scale full Digivice 240×320 frame onto this large screen."""

    def __init__(self, source: QWidget, screen, parent=None):
        super().__init__(parent)
        self._source = source
        self._screen = screen
        self.setWindowTitle("ESP Digivice (HDMI preview)")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background-color: #000;")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setFocusPolicy(Qt.StrongFocus)
        try:
            self.setScreen(screen)
        except Exception:
            pass
        self.setGeometry(screen.geometry())

    def keyPressEvent(self, event) -> None:  # noqa: N802
        src = self._source
        if src is not None:
            QApplication.sendEvent(src, event)
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
        tw, th = self.width(), self.height()
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
        scaled = img.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        p.drawImage(x, y, scaled)


class MultiScreenPresenter:
    """Digivice on SPI (native); scaled full-frame previews on HDMI."""

    def __init__(self, source: QMainWindow):
        self.source = source
        self.hosts: List[ScaledScreenHost] = []
        self._timer = QTimer()
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        global W, H
        W, H = _default_wh()

        ensure_spi_via_xrandr()
        # Give the server a moment / refresh screen list
        QApplication.processEvents()

        self.source.setWindowFlags(Qt.Window)
        try:
            self.source.setAttribute(Qt.WA_StyledBackground, True)
            self.source.setStyleSheet(
                "QMainWindow { background-color: #0b1a2a; color: #e8eef5; }"
            )
        except Exception:
            pass

        self.source.setFixedSize(W, H)
        self.source.resize(W, H)

        panel = pick_panel_screen()
        screens = _screens()
        print(f"[handset] screens={len(screens)} source={W}x{H}", flush=True)
        for s in screens:
            g = s.geometry()
            tag = "PHONE" if is_phone_screen(s) else "LARGE"
            print(
                f"[handset]   [{tag}] {s.name()!r} "
                f"{g.width()}x{g.height()}+{g.x()}+{g.y()}",
                flush=True,
            )

        if panel is not None:
            # Real Digivice window lives ON the SPI panel (native pixels)
            try:
                self.source.setScreen(panel)
            except Exception:
                pass
            geo = panel.geometry()
            # Use full phone panel surface
            if geo.width() <= W + 16 and geo.height() <= H + 16:
                self.source.setFixedSize(geo.size())
                self.source.setGeometry(geo)
                self.source.showFullScreen()
            else:
                # Panel reported odd size: pin phone rect top-left of that screen
                self.source.setFixedSize(W, H)
                self.source.setGeometry(geo.x(), geo.y(), W, H)
                self.source.show()
            print(
                f"[handset] Digivice LIVE on panel {panel.name()!r} "
                f"{self.source.width()}x{self.source.height()}+{geo.x()}+{geo.y()}",
                flush=True,
            )
        else:
            # No SPI in Qt — still show UI on primary so HDMI works;
            # SPI stays blank until digivice-layout exposes SPI as a QScreen.
            primary = QGuiApplication.primaryScreen()
            self.source.setFixedSize(W, H)
            if primary is not None:
                g = primary.geometry()
                self.source.move(g.x() + 20, g.y() + 20)
            self.source.show()
            print(
                "[handset] WARN: no SPI/phone QScreen — Digivice on primary only. "
                "SPI blank until xrandr shows SPI connected. Run: digivice-layout",
                flush=True,
            )

        # Scaled full-frame copy on every LARGE screen (HDMI…)
        self._rebuild_hosts(panel)
        self._timer.start()

        # Retry: layout may attach SPI late
        QTimer.singleShot(1500, self._retry_panel)
        QTimer.singleShot(3500, self._retry_panel)

    def _rebuild_hosts(self, panel) -> None:
        for h in self.hosts:
            h.close()
            h.deleteLater()
        self.hosts.clear()
        for s in _screens():
            if panel is not None and s.name() == panel.name():
                continue  # already has live Digivice window
            if is_phone_screen(s):
                # Extra phone-sized screen without live window: scale host
                host = ScaledScreenHost(self.source, s)
                host.showFullScreen()
                self.hosts.append(host)
                print(f"[handset] scale-host (phone) → {s.name()!r}", flush=True)
                continue
            host = ScaledScreenHost(self.source, s)
            host.showFullScreen()
            self.hosts.append(host)
            print(f"[handset] scale-host (HDMI) → {s.name()!r}", flush=True)

    def _retry_panel(self) -> None:
        if pick_panel_screen() is None:
            print("[handset] retry ensure SPI…", flush=True)
            ensure_spi_via_xrandr()
            QApplication.processEvents()
        panel = pick_panel_screen()
        if panel is None:
            return
        # Move Digivice onto SPI if we were only on HDMI
        try:
            self.source.setScreen(panel)
            geo = panel.geometry()
            self.source.setFixedSize(W, H)
            if geo.width() <= W + 16 and geo.height() <= H + 16:
                self.source.setFixedSize(geo.size())
                self.source.setGeometry(geo)
                self.source.showFullScreen()
            else:
                self.source.setGeometry(geo.x(), geo.y(), W, H)
                self.source.show()
            print(f"[handset] moved Digivice onto {panel.name()!r}", flush=True)
            self._rebuild_hosts(panel)
        except Exception as e:
            print(f"[handset] retry_panel: {e}", flush=True)

    def _tick(self) -> None:
        for h in self.hosts:
            h.update()

    def stop(self) -> None:
        self._timer.stop()
        for h in self.hosts:
            h.close()
        self.hosts.clear()


def apply_kiosk(win) -> Optional[object]:
    mode = (os.environ.get("ESP_HANDSET_DISPLAY", "scale") or "scale").strip().lower()
    if mode in ("0", "legacy", "single"):
        return _apply_kiosk_legacy(win)
    presenter = MultiScreenPresenter(win)
    presenter.start()
    win._multi_presenter = presenter  # type: ignore[attr-defined]
    return presenter


def _apply_kiosk_legacy(win) -> None:
    panel = pick_panel_screen() or QGuiApplication.primaryScreen()
    win.setWindowFlags(Qt.Window)
    win.setFixedSize(W, H)
    if panel is not None:
        try:
            win.setScreen(panel)
        except Exception:
            pass
        win.setGeometry(panel.geometry().x(), panel.geometry().y(), W, H)
    win.show()
