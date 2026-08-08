"""Digivice placement: pin UI to SPI/Unknown panel, never full-screen HDMI by accident.

xrandr names the mipi-dbi panel Unknown19-1. Qt often still makes HDMI primary and
showFullScreen() jumps there — SPI stays black. We:

  1) Parse xrandr for a phone-sized / Unknown* rect
  2) Fixed window WxH at that absolute geometry (no HDMI fullscreen)
  3) Optionally open a scaled mirror window on large screens so HDMI still shows UI
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
_PANEL_NAME_MARKERS = ("SPI", "DPI", "DSI", "PANEL", "UNKNOWN")


def _screens():
    try:
        return list(QGuiApplication.screens() or [])
    except Exception:
        return []


def is_panel_name(name: str) -> bool:
    n = (name or "").upper()
    if any(k in n for k in ("HDMI", "DP-", "DISPLAYPORT", "VGA", "VIRTUAL")):
        return False
    return any(k in n for k in _PANEL_NAME_MARKERS)


def is_phone_size(w: int, h: int) -> bool:
    if w * h > PHONE_AREA_MAX:
        return False
    if w * h < 20_000:
        return False
    return True


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


def find_panel_output() -> Optional[OutGeom]:
    """Prefer SPI/Unknown / exact phone mode from xrandr (authoritative)."""
    outs = xrandr_outputs()
    if not outs:
        return None
    name = os.environ.get("ESP_HANDSET_PANEL_OUTPUT", "").strip()
    if not name:
        try:
            name = open("/tmp/digivice-panel-output", encoding="utf-8").read().strip()
        except OSError:
            name = ""
    if name:
        for o in outs:
            if o.name == name:
                return o
    # Exact phone modes
    for o in outs:
        if (o.w, o.h) in {(240, 320), (320, 240), (W, H), (H, W)}:
            if not any(k in o.name.upper() for k in ("HDMI", "DP-")):
                return o
    for o in outs:
        if is_panel_name(o.name):
            return o
    for o in outs:
        if is_phone_size(o.w, o.h) and "HDMI" not in o.name.upper():
            return o
    return None


def pick_panel_screen():
    """Qt QScreen for the phone panel; never return large HDMI as 'panel'."""
    screens = _screens()
    if not screens:
        return None
    panel = find_panel_output()
    if panel is not None:
        for s in screens:
            if s.name() == panel.name:
                return s
        # Match by size + position
        for s in screens:
            g = s.geometry()
            if (
                abs(g.width() - panel.w) <= 2
                and abs(g.height() - panel.h) <= 2
                and abs(g.x() - panel.x) <= 2
                and abs(g.y() - panel.y) <= 2
            ):
                return s
    wanted = {(W, H), (H, W), (240, 320), (320, 240)}
    for s in screens:
        if (s.size().width(), s.size().height()) in wanted:
            if not any(
                k in (s.name() or "").upper() for k in ("HDMI", "DP-")
            ):
                return s
    for s in screens:
        if is_panel_name(s.name() or ""):
            return s
    # Never fall back to huge primary alone — return None so caller uses xrandr rect
    small = [
        s
        for s in screens
        if is_phone_size(s.size().width(), s.size().height())
    ]
    if small:
        return min(small, key=lambda s: s.size().width() * s.size().height())
    return None


def ensure_spi_via_xrandr() -> None:
    if os.environ.get("ESP_HANDSET_SKIP_LAYOUT", "").strip() in ("1", "true", "yes"):
        return
    display = os.environ.get("DISPLAY", ":0")
    for script in (
        "/usr/local/bin/digivice-layout",
        os.path.join(os.path.dirname(__file__), "..", "session", "digivice-layout.sh"),
    ):
        if not os.path.isfile(script):
            continue
        try:
            subprocess.run(
                ["bash", script],
                env={**os.environ, "DISPLAY": display},
                timeout=15,
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception as e:
            print(f"[handset] layout: {e}", flush=True)
        break
    # backlight
    for root, _dirs, files in os.walk("/sys/class/backlight"):
        try:
            if "bl_power" in files:
                open(os.path.join(root, "bl_power"), "w").write("0")
            if "max_brightness" in files and "brightness" in files:
                mx = open(os.path.join(root, "max_brightness")).read().strip()
                open(os.path.join(root, "brightness"), "w").write(mx)
        except OSError:
            pass


class HdmiMirrorHost(QWidget):
    """Fullscreen host on large screen mirroring the Digivice source (optional)."""

    def __init__(self, source: QWidget, screen, parent=None):
        super().__init__(parent)
        self._source = source
        self._screen = screen
        self.setWindowTitle("ESP Digivice (HDMI)")
        self.setStyleSheet("background-color: #000;")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        try:
            self.setScreen(screen)
        except Exception:
            pass
        self.setGeometry(screen.geometry())

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


class DualDisplayController:
    """Digivice fixed on SPI rect; optional HDMI scaled mirror."""

    def __init__(self, source: QMainWindow):
        self.source = source
        self.mirrors: List[HdmiMirrorHost] = []
        self._timer = QTimer()
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        global W, H
        W, H = _default_wh()
        ensure_spi_via_xrandr()
        QApplication.processEvents()

        screens = _screens()
        panel_out = find_panel_output()
        panel_scr = pick_panel_screen()

        print(f"[handset] screens={len(screens)} want={W}x{H}", flush=True)
        for s in screens:
            g = s.geometry()
            print(
                f"[handset]   qt {s.name()!r} {g.width()}x{g.height()}+{g.x()}+{g.y()}",
                flush=True,
            )
        for o in xrandr_outputs():
            print(
                f"[handset]   xrandr {o.name!r} {o.w}x{o.h}+{o.x}+{o.y}",
                flush=True,
            )
        if panel_out:
            print(
                f"[handset] panel target {panel_out.name!r} "
                f"{panel_out.w}x{panel_out.h}+{panel_out.x}+{panel_out.y}",
                flush=True,
            )
        else:
            print(
                "[handset] WARN: no SPI/Unknown active mode in xrandr — "
                "panel may be off. Run digivice-layout; check dmesg | grep mipi",
                flush=True,
            )

        try:
            self.source.setAttribute(Qt.WA_StyledBackground, True)
            self.source.setStyleSheet(
                "QMainWindow { background-color: #0b1a2a; color: #e8eef5; }"
            )
        except Exception:
            pass

        # FIXED phone window — never showFullScreen on HDMI primary
        self.source.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.source.setFixedSize(W, H)

        if panel_out is not None:
            # Prefer full panel pixel size when it matches phone
            if is_phone_size(panel_out.w, panel_out.h):
                self.source.setFixedSize(panel_out.w, panel_out.h)
            rect = panel_out.rect()
            if panel_scr is not None:
                try:
                    self.source.setScreen(panel_scr)
                except Exception:
                    pass
            self.source.setGeometry(rect)
            self.source.show()
            QApplication.processEvents()
            try:
                h = self.source.windowHandle()
                if h is not None and panel_scr is not None:
                    h.setScreen(panel_scr)
                if h is not None:
                    h.setGeometry(rect)
            except Exception:
                pass
            self.source.setGeometry(rect)
            print(
                f"[handset] Digivice SPI-bound {self.source.width()}x"
                f"{self.source.height()}+{rect.x()}+{rect.y()} "
                f"({panel_out.name})",
                flush=True,
            )
        elif panel_scr is not None and is_phone_size(
            panel_scr.size().width(), panel_scr.size().height()
        ):
            g = panel_scr.geometry()
            try:
                self.source.setScreen(panel_scr)
            except Exception:
                pass
            self.source.setGeometry(g)
            self.source.show()
            print(f"[handset] Digivice on QScreen {panel_scr.name()!r}", flush=True)
        else:
            # SPI not active — show on primary so user still has UI on HDMI
            primary = QGuiApplication.primaryScreen()
            self.source.show()
            if primary is not None:
                g = primary.geometry()
                self.source.move(g.x() + 40, g.y() + 40)
            print(
                "[handset] SPI not placed — Digivice on primary (HDMI only). "
                "Fix panel: digivice-layout && xrandr | grep connected",
                flush=True,
            )

        # HDMI mirrors of the phone window (software, not xrandr scale-from)
        mirror = os.environ.get("ESP_HANDSET_HDMI_MIRROR", "1").strip().lower()
        if mirror not in ("0", "false", "no"):
            for s in screens:
                if panel_scr is not None and s.name() == panel_scr.name():
                    continue
                if is_phone_size(s.size().width(), s.size().height()):
                    continue
                if is_panel_name(s.name() or ""):
                    continue
                host = HdmiMirrorHost(self.source, s)
                host.showFullScreen()
                self.mirrors.append(host)
                print(f"[handset] HDMI mirror → {s.name()!r}", flush=True)

        self.source.raise_()
        self._timer.start()
        QTimer.singleShot(500, self._repin)
        QTimer.singleShot(1500, self._repin)
        QTimer.singleShot(3000, self._repin)

    def _repin(self) -> None:
        panel_out = find_panel_output()
        if panel_out is None:
            return
        rect = panel_out.rect()
        scr = pick_panel_screen()
        try:
            if scr is not None:
                self.source.setScreen(scr)
            if is_phone_size(panel_out.w, panel_out.h):
                self.source.setFixedSize(panel_out.w, panel_out.h)
            self.source.setGeometry(rect)
            h = self.source.windowHandle()
            if h is not None:
                if scr is not None:
                    h.setScreen(scr)
                h.setGeometry(rect)
            print(
                f"[handset] re-pin SPI {panel_out.name} "
                f"+{panel_out.x}+{panel_out.y}",
                flush=True,
            )
        except Exception as e:
            print(f"[handset] re-pin: {e}", flush=True)

    def _tick(self) -> None:
        for m in self.mirrors:
            m.update()

    def stop(self) -> None:
        self._timer.stop()
        for m in self.mirrors:
            m.close()
        self.mirrors.clear()


def apply_kiosk(win) -> Optional[object]:
    ctl = DualDisplayController(win)
    ctl.start()
    win._multi_presenter = ctl  # type: ignore[attr-defined]
    return ctl
