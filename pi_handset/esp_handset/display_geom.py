"""Digivice display: HDMI fullscreen + optional ST7789 SPI userspace mirror.

SPI backend (Instructables / fbcp model):
  Render Digivice for HDMI, push the UI to ST7789 over SPI (spidev),
  without relying on mipi-dbi dual-DRM (which left Unknown19-1 dark).

  ESP_HANDSET_SPI_BACKEND=userspace   (recommended when dual DRM fails)
  ESP_HANDSET_SPI_BACKEND=drm         (native mipi-dbi panel as QScreen)
  ESP_HANDSET_SPI_BACKEND=auto        (try drm panel; else userspace)

See: https://www.instructables.com/How-to-Mirror-the-Desktop-of-RPI-OS-on-Any-St7789-/
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Optional, Tuple, List


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
        from PyQt5.QtGui import QGuiApplication

        return list(QGuiApplication.screens() or [])
    except Exception:
        return []


def is_panel_name(name: str) -> bool:
    n = (name or "").upper()
    if any(k in n for k in ("HDMI", "DP-", "DISPLAYPORT", "VGA", "VIRTUAL")):
        return False
    return any(k in n for k in ("SPI", "DPI", "DSI", "PANEL", "UNKNOWN"))


def _area(screen) -> int:
    s = screen.size()
    return max(1, s.width() * s.height())


def xrandr_connected_names() -> List[str]:
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
    return re.findall(r"^(\S+)\s+connected", out, re.M)


def pick_panel_screen():
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
    for s in screens:
        if is_panel_name(s.name() or ""):
            if (s.size().width(), s.size().height()) in {
                (W, H),
                (H, W),
                (240, 320),
                (320, 240),
            } or _area(s) <= PHONE_AREA_MAX:
                return s
    return None


def _backend() -> str:
    b = (os.environ.get("ESP_HANDSET_SPI_BACKEND", "auto") or "auto").strip().lower()
    if b in ("user", "userspace", "spidev", "mirror", "fbcp"):
        return "userspace"
    if b in ("drm", "kms", "panel"):
        return "drm"
    # auto: prefer userspace if /etc flag or spidev exists and mipi known broken
    if os.path.isfile("/etc/esp-handset/spi-userspace"):
        return "userspace"
    if os.path.exists("/dev/spidev0.0") and not os.path.exists(
        "/sys/class/drm/card0-Unknown-1"
    ):
        # spidev free; likely no DRM panel — use userspace
        return "userspace"
    return "drm"


def ensure_layout() -> None:
    if os.environ.get("ESP_HANDSET_SKIP_LAYOUT", "").strip() in ("1", "true", "yes"):
        return
    if _backend() == "userspace":
        # HDMI only — do not fight mipi DRM that may still be half-probed
        print("[handset] userspace SPI: skip digivice-layout DRM fight", flush=True)
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
            )
        except Exception as e:
            print(f"[handset] layout: {e}", flush=True)
        break


class SpiUserspaceMirror:
    """Mirror Digivice grab → ST7789 SPI (Instructables-style)."""

    def __init__(self, source):
        self.source = source
        self._timer = None
        self._active = False

    def start(self) -> bool:
        from PyQt5.QtCore import QTimer

        try:
            from esp_handset import st7789_spi as st
        except ImportError:
            from . import st7789_spi as st  # type: ignore

        if not st.init():
            print(
                "[handset] userspace ST7789 failed — SPI blank; "
                "run: sudo digivice-install-spi-userspace && sudo reboot",
                flush=True,
            )
            return False
        # Red flash proves SPI path
        try:
            st.fill(255, 0, 0)
        except Exception:
            pass
        self._active = True
        self._st = st
        self._timer = QTimer()
        self._timer.setInterval(int(os.environ.get("ESP_ST7789_FPS_MS", "50")))
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        print("[handset] SPI userspace mirror ON (ST7789 ← Digivice grab)", flush=True)
        return True

    def _tick(self) -> None:
        if not self._active:
            return
        try:
            img = self.source.grab().toImage()
            self._st.blit_qimage(img)
        except Exception as e:
            print(f"[handset] spi mirror tick: {e}", flush=True)

    def stop(self) -> None:
        self._active = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        try:
            self._st.close()
        except Exception:
            pass


def apply_kiosk(win) -> Optional[object]:
    """Fullscreen Digivice on HDMI; SPI via DRM QScreen or userspace mirror."""
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QGuiApplication
    from PyQt5.QtWidgets import QApplication

    global W, H
    W, H = _default_wh()
    backend = _backend()
    print(f"[handset] SPI backend={backend}", flush=True)

    ensure_layout()

    try:
        win.setAttribute(Qt.WA_StyledBackground, True)
        win.setStyleSheet(
            "QMainWindow { background-color: #0b1a2a; color: #e8eef5; }"
        )
    except Exception:
        pass

    screens = _screens()
    print(f"[handset] screens={len(screens)} canvas={W}x{H}", flush=True)
    for s in screens:
        g = s.geometry()
        print(
            f"[handset]   {s.name()!r} {g.width()}x{g.height()}+{g.x()}+{g.y()}",
            flush=True,
        )
    print(f"[handset] xrandr: {xrandr_connected_names()}", flush=True)

    win.setWindowFlags(Qt.Window)
    panel = pick_panel_screen() if backend == "drm" else None
    result: Optional[object] = None

    if panel is not None and backend == "drm":
        try:
            win.setScreen(panel)
        except Exception:
            pass
        win.setGeometry(panel.geometry())
        win.show()
        win.showFullScreen()
        print(f"[handset] DRM fullscreen on {panel.name()!r}", flush=True)
    else:
        # HDMI / primary: phone canvas centered conceptually full kiosk
        primary = QGuiApplication.primaryScreen()
        try:
            win.setMinimumSize(0, 0)
            win.setMaximumSize(16777215, 16777215)
        except Exception:
            pass
        if backend == "userspace":
            # Fixed phone size grab for 1:1 SPI (Instructables scale target)
            win.setFixedSize(W, H)
            if primary is not None:
                g = primary.geometry()
                # Park phone canvas at origin of primary for clean grab OR center
                cx = g.x() + max(0, (g.width() - W) // 2)
                cy = g.y() + max(0, (g.height() - H) // 2)
                win.setGeometry(cx, cy, W, H)
            win.show()
            # Fullscreen host is optional visual scale — use simple showFullScreen for kiosk
            if os.environ.get("ESP_HANDSET_HDMI_FULL", "1").strip() not in (
                "0",
                "false",
                "no",
            ):
                # Soft: enlarge for HDMI while keeping content size for SPI via sizeHint — use host
                try:
                    win.setMinimumSize(0, 0)
                    win.setMaximumSize(16777215, 16777215)
                except Exception:
                    pass
                win.showFullScreen()
            print(
                "[handset] HDMI kiosk + SPI will mirror via userspace ST7789",
                flush=True,
            )
        else:
            if primary is not None:
                try:
                    win.setScreen(primary)
                except Exception:
                    pass
                win.setGeometry(primary.geometry())
            win.show()
            win.showFullScreen()
            print(
                "[handset] DRM panel not found — HDMI fullscreen only",
                flush=True,
            )

    win.raise_()
    win.activateWindow()
    QApplication.processEvents()

    if backend == "userspace":
        mir = SpiUserspaceMirror(win)
        if mir.start():
            win._spi_mirror = mir  # type: ignore[attr-defined]
            result = mir
    elif backend == "auto" or backend == "drm":
        # auto fallthrough if panel missing: try userspace
        if panel is None and backend != "drm":
            mir = SpiUserspaceMirror(win)
            if mir.start():
                win._spi_mirror = mir  # type: ignore[attr-defined]
                result = mir

    def _pin() -> None:
        if backend == "userspace":
            return
        try:
            scr = pick_panel_screen() or QGuiApplication.primaryScreen()
            h = win.windowHandle()
            if h is not None and scr is not None:
                h.setScreen(scr)
                win.setGeometry(scr.geometry())
            win.showFullScreen()
        except Exception as e:
            print(f"[handset] re-pin: {e}", flush=True)

    QTimer.singleShot(200, _pin)
    QTimer.singleShot(800, _pin)
    return result
