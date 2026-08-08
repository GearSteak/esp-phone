"""Digivice display placement — simple and strict.

Rules:
  • If Qt sees a phone panel (Unknown*/SPI, ~240×320): fullscreen ONLY there.
  • Else: fullscreen on primary (HDMI) so you get a full usable UI — never a
    floating 240×320 chip on the big monitor.
  • No multi-host mirrors (those produced confused dual/crop states).
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
    """Phone/SPI QScreen only. Returns None if nothing phone-sized is present.

    Never returns the big HDMI screen — that made Digivice 'look like' it ran
    when SPI was blank, then later a 240×320 chip on HDMI.
    """
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
            if s.name() == name and _area(s) <= PHONE_AREA_MAX:
                return s

    wanted = {(W, H), (H, W), (240, 320), (320, 240)}
    for s in screens:
        if (s.size().width(), s.size().height()) in wanted:
            if is_panel_name(s.name() or "") or _area(s) <= PHONE_AREA_MAX:
                # Reject accidental HDMI name even if mode wrong
                if "HDMI" in (s.name() or "").upper():
                    continue
                return s

    for s in screens:
        if is_panel_name(s.name() or "") and _area(s) <= PHONE_AREA_MAX:
            return s

    small = [s for s in screens if _area(s) <= PHONE_AREA_MAX]
    # Drop anything named HDMI
    small = [s for s in small if "HDMI" not in (s.name() or "").upper()]
    if small:
        return min(small, key=_area)
    return None


def ensure_layout() -> None:
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
            )
        except Exception as e:
            print(f"[handset] layout: {e}", flush=True)
        break


def apply_kiosk(win) -> Optional[object]:
    """Fullscreen Digivice on SPI if present; else fullscreen on primary (HDMI)."""
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QGuiApplication
    from PyQt5.QtWidgets import QApplication

    global W, H
    W, H = _default_wh()

    ensure_layout()

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
    print(f"[handset] xrandr connected: {xrandr_connected_names()}", flush=True)

    panel = pick_panel_screen()
    win.setWindowFlags(Qt.Window)

    if panel is not None:
        # True phone panel — fullscreen ONLY this QScreen
        try:
            win.setScreen(panel)
        except Exception:
            pass
        geo = panel.geometry()
        win.setGeometry(geo)
        print(
            f"[handset] FULLSCREEN on panel {panel.name()!r} "
            f"{geo.width()}x{geo.height()}+{geo.x()}+{geo.y()}",
            flush=True,
        )
        win.show()
        win.showFullScreen()
        target = panel
    else:
        # No SPI in Qt → use primary (HDMI) FULLSCREEN, never a floating 240×320
        primary = QGuiApplication.primaryScreen()
        print(
            "[handset] No phone QScreen (SPI blank/not in Qt). "
            "FULLSCREEN Digivice on primary/HDMI — not a small window.",
            flush=True,
        )
        if primary is not None:
            try:
                win.setScreen(primary)
            except Exception:
                pass
            win.setGeometry(primary.geometry())
            target = primary
        else:
            target = None
        # Allow free resize to fill HDMI kiosk
        try:
            win.setMinimumSize(0, 0)
            win.setMaximumSize(16777215, 16777215)
        except Exception:
            pass
        win.show()
        win.showFullScreen()

    win.raise_()
    win.activateWindow()
    QApplication.processEvents()

    def _pin() -> None:
        try:
            scr = pick_panel_screen()
            if scr is None:
                scr = QGuiApplication.primaryScreen()
            h = win.windowHandle()
            if h is not None and scr is not None:
                h.setScreen(scr)
                win.setGeometry(scr.geometry())
            win.showFullScreen()
            if scr is not None:
                print(f"[handset] re-pin fullscreen → {scr.name()!r}", flush=True)
        except Exception as e:
            print(f"[handset] re-pin: {e}", flush=True)

    QTimer.singleShot(200, _pin)
    QTimer.singleShot(800, _pin)
    return None
