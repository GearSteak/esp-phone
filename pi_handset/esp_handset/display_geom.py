"""Digivice multi-output display.

Canonical pipeline:
  1. Digivice paints a fixed 240×320 canvas (source window).
  2. A fullscreen paint host is placed on EVERY output — including the
     SPI panel (often named Unknown19-1 under mipi-dbi-spi).
  3. Each host grabs the source and scales KeepAspectRatio (no crop).

Why SPI was blank:
  Qt often keeps the real main window on HDMI; we previously "skipped"
  a host on the phone panel, so SPI got no pixels. Always painting hosts
  on all outputs fixes that.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
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
_PANEL_NAME_MARKERS = (
    "SPI",
    "DPI",
    "DSI",
    "PANEL",
    "UNKNOWN",  # DRM name, e.g. Unknown19-1
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
    return _area(screen) <= PHONE_AREA_MAX


def is_phone_rect(w: int, h: int, name: str = "") -> bool:
    if is_panel_name(name):
        return True
    if w * h <= PHONE_AREA_MAX and w * h >= 20_000:
        return True
    return (w, h) in {(240, 320), (320, 240), (W, H), (H, W)}


@dataclass
class OutGeom:
    name: str
    w: int
    h: int
    x: int
    y: int

    @property
    def area(self) -> int:
        return max(1, self.w * self.h)

    def rect(self) -> QRect:
        return QRect(self.x, self.y, self.w, self.h)


def xrandr_outputs() -> List[OutGeom]:
    """Parse active modes from xrandr (absolute layout)."""
    display = os.environ.get("DISPLAY", ":0")
    try:
        out = subprocess.check_output(
            ["xrandr", "--query"],
            env={**os.environ, "DISPLAY": display},
            text=True,
            timeout=5,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    found: List[OutGeom] = []
    # HDMI-1 connected primary 1920x1080+240+0 ...
    # Unknown19-1 connected 240x320+0+0 ...
    pat = re.compile(
        r"^(\S+)\s+connected(?:\s+primary)?\s+(\d+)x(\d+)\+(\d+)\+(\d+)",
        re.M,
    )
    for m in pat.finditer(out):
        found.append(
            OutGeom(
                name=m.group(1),
                w=int(m.group(2)),
                h=int(m.group(3)),
                x=int(m.group(4)),
                y=int(m.group(5)),
            )
        )
    return found


def unblank_backlights() -> None:
    for root, _dirs, files in os.walk("/sys/class/backlight"):
        # only top-level devices
        if root.rstrip("/").count("/") > 4:
            continue
        try:
            if "bl_power" in files:
                open(os.path.join(root, "bl_power"), "w").write("0")
            if "max_brightness" in files and "brightness" in files:
                mx = open(os.path.join(root, "max_brightness")).read().strip()
                open(os.path.join(root, "brightness"), "w").write(mx)
        except OSError:
            pass
    # gpio-backlight under /sys/class/leds sometimes
    for root, _dirs, files in os.walk("/sys/class/leds"):
        if "brightness" not in files:
            continue
        name = os.path.basename(root).lower()
        if "backlight" not in name and "bl_" not in name:
            continue
        try:
            open(os.path.join(root, "brightness"), "w").write("1")
        except OSError:
            pass


def ensure_spi_via_xrandr() -> None:
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
        r = subprocess.run(
            ["bash", script],
            env={**os.environ, "DISPLAY": display, "ESP_HANDSET_MIRROR": "0"},
            timeout=15,
            check=False,
            capture_output=True,
            text=True,
        )
        for line in (r.stdout or "").splitlines()[-8:]:
            print(f"[handset] layout> {line}", flush=True)
        for line in (r.stderr or "").splitlines()[-8:]:
            print(f"[handset] layout> {line}", flush=True)
    except Exception as e:
        print(f"[handset] ensure_spi: {e}", flush=True)
    unblank_backlights()


def _bind_window_to_rect(widget: QWidget, rect: QRect, screen=None) -> None:
    """Place a top-level window on absolute rect; setScreen after winId exists."""
    widget.setGeometry(rect)
    widget.show()
    QApplication.processEvents()
    try:
        wh = widget.windowHandle()
        if wh is not None and screen is not None:
            wh.setScreen(screen)
        if wh is not None:
            wh.setGeometry(rect)
    except Exception:
        pass
    widget.setGeometry(rect)
    # Fullscreen only when rect matches a whole QScreen; else fixed rect window
    if screen is not None:
        sg = screen.geometry()
        if (
            abs(sg.width() - rect.width()) <= 2
            and abs(sg.height() - rect.height()) <= 2
            and abs(sg.x() - rect.x()) <= 2
            and abs(sg.y() - rect.y()) <= 2
        ):
            widget.showFullScreen()
            widget.setGeometry(rect)


class ScaledScreenHost(QWidget):
    """Fullscreen (or fixed rect): scale full Digivice frame onto one output."""

    def __init__(
        self,
        source: QWidget,
        rect: QRect,
        screen=None,
        name: str = "?",
        parent=None,
    ):
        super().__init__(parent)
        self._source = source
        self._screen = screen
        self._rect = QRect(rect)
        self._name = name
        self.setWindowTitle(f"ESP Digivice host ({name})")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background-color: #000;")
        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setFocusPolicy(Qt.StrongFocus)

    def place(self) -> None:
        _bind_window_to_rect(self, self._rect, self._screen)
        print(
            f"[handset] host → {self._name!r} "
            f"{self._rect.width()}x{self._rect.height()}"
            f"+{self._rect.x()}+{self._rect.y()}",
            flush=True,
        )

    def reassert(self) -> None:
        if self._screen is not None:
            g = self._screen.geometry()
            self._rect = QRect(g)
        self.setGeometry(self._rect)
        try:
            wh = self.windowHandle()
            if wh is not None:
                if self._screen is not None:
                    wh.setScreen(self._screen)
                wh.setGeometry(self._rect)
        except Exception:
            pass

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
        # One-shot flash so SPI "dead" vs software-host path is obvious
        if os.environ.get("ESP_HANDSET_SPI_TEST", "").strip() in ("1", "true", "yes"):
            p.fillRect(self.rect(), Qt.cyan)
            p.setPen(Qt.black)
            p.drawText(self.rect(), Qt.AlignCenter, self._name)
            return
        src = self._source
        if src is None:
            return
        img: QImage = src.grab().toImage()
        if img.isNull():
            return
        # Native pixel copy on exact phone-size hosts (no blur)
        if self.width() == img.width() and self.height() == img.height():
            p.drawImage(0, 0, img)
            return
        scaled = img.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        p.drawImage(x, y, scaled)


class MultiScreenPresenter:
    """Source canvas + paint host on every physical output."""

    def __init__(self, source: QMainWindow):
        self.source = source
        self.hosts: List[ScaledScreenHost] = []
        self._timer = QTimer()
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._assert_n = 0

    def start(self) -> None:
        global W, H
        W, H = _default_wh()

        ensure_spi_via_xrandr()
        unblank_backlights()
        QApplication.processEvents()

        self.source.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        try:
            self.source.setAttribute(Qt.WA_StyledBackground, True)
            self.source.setStyleSheet(
                "QMainWindow { background-color: #0b1a2a; color: #e8eef5; }"
            )
            self.source.setWindowTitle("ESP Digivice")
        except Exception:
            pass

        self.source.setFixedSize(W, H)
        self.source.resize(W, H)
        # Source must stay *mapped* for grab(); keep it on primary, small Z
        primary = QGuiApplication.primaryScreen()
        if primary is not None:
            g = primary.geometry()
            # Park at 0,0 of primary — hosts cover it where needed
            self.source.move(g.x(), g.y())
        self.source.show()
        self.source.lower()

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
        for o in xrandr_outputs():
            tag = "PHONE" if is_phone_rect(o.w, o.h, o.name) else "LARGE"
            print(
                f"[handset]   xrandr [{tag}] {o.name!r} "
                f"{o.w}x{o.h}+{o.x}+{o.y}",
                flush=True,
            )

        self._rebuild_hosts()
        self._timer.start()
        QTimer.singleShot(800, self._rebuild_hosts)
        QTimer.singleShot(2000, self._rebuild_hosts)
        QTimer.singleShot(4000, lambda: (ensure_spi_via_xrandr(), self._rebuild_hosts()))

    def _targets(self) -> List[Tuple[str, QRect, object]]:
        """List of (name, rect, QScreen|None) to cover with hosts."""
        targets: List[Tuple[str, QRect, object]] = []
        screens = _screens()
        by_name = {s.name(): s for s in screens}

        # Prefer per-QScreen targets (correct for multi-QScreen sessions)
        if len(screens) >= 2:
            for s in screens:
                g = s.geometry()
                targets.append((s.name() or "?", QRect(g), s))
            return targets

        # Single Qt screen: still place a host from xrandr rectangles so SPI
        # (Unknown19-1 at +0+0 240×320) gets pixels even if not a QScreen.
        outs = xrandr_outputs()
        if outs:
            primary = screens[0] if screens else None
            for o in outs:
                sc = by_name.get(o.name, primary)
                targets.append((o.name, o.rect(), sc))
            return targets

        if screens:
            s = screens[0]
            g = s.geometry()
            targets.append((s.name() or "primary", QRect(g), s))
        return targets

    def _rebuild_hosts(self) -> None:
        for h in self.hosts:
            h.close()
            h.deleteLater()
        self.hosts.clear()

        for name, rect, screen in self._targets():
            host = ScaledScreenHost(self.source, rect, screen=screen, name=name)
            host.place()
            self.hosts.append(host)

        if not self.hosts:
            print("[handset] WARN: no hosts created — SPI+HDMI will stay blank", flush=True)
        else:
            print(f"[handset] hosts active: {len(self.hosts)}", flush=True)

    def _tick(self) -> None:
        self._assert_n += 1
        # Re-pin host geometry every ~1s (WM likes to steal windows to HDMI)
        if self._assert_n % 30 == 0:
            for h in self.hosts:
                h.reassert()
            unblank_backlights()
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
    screens = _screens()
    panel = None
    for s in screens:
        if is_phone_screen(s):
            panel = s
            break
    if panel is None and screens:
        panel = min(screens, key=_area)
    win.setWindowFlags(Qt.Window)
    win.setFixedSize(W, H)
    if panel is not None:
        g = panel.geometry()
        _bind_window_to_rect(win, QRect(g.x(), g.y(), W, H), panel)
    else:
        win.show()
