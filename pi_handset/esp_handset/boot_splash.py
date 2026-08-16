"""Digivice boot splash + lightweight update check.

Important: do NOT attach ST7789/SPI kiosk to this window — that stole the panel.
Splash is a short X11/Qt overlay; the phone canvas owns SPI after build_app.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QWidget


@dataclass
class UpdateCheck:
    status: str  # checking | up_to_date | available | offline | skip | error
    detail: str = ""
    local: str = ""
    remote: str = ""


def _repo_candidates() -> list:
    home = Path.home()
    out = []
    env = (os.environ.get("ESP_HANDSET_REPO") or "").strip()
    if env:
        out.append(Path(env))
    out.extend(
        [
            home / "esp-phone",
            Path("/opt/esp-phone"),
            Path("/home/pi/esp-phone"),
            Path("/home/gearsteak/esp-phone"),
        ]
    )
    seen = set()
    uniq = []
    for p in out:
        s = str(p)
        if s not in seen:
            seen.add(s)
            uniq.append(p)
    return uniq


def find_git_repo() -> Optional[Path]:
    for cand in _repo_candidates():
        if (cand / ".git").exists() and (cand / "pi_handset").is_dir():
            return cand
    return None


def check_for_updates(*, timeout_s: float = 6.0) -> UpdateCheck:
    if os.environ.get("ESP_HANDSET_SKIP_BOOT_UPDATE", "").strip() in (
        "1",
        "true",
        "yes",
    ):
        return UpdateCheck("skip", "Skipped")

    repo = find_git_repo()
    if repo is None:
        return UpdateCheck("skip", "No git repo")

    def _run(args: list, t: float) -> subprocess.CompletedProcess:
        return subprocess.run(
            args,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=t,
            check=False,
        )

    try:
        fr = _run(["git", "fetch", "--quiet", "origin", "main"], timeout_s)
        if fr.returncode != 0:
            fr = _run(["git", "fetch", "--quiet", "origin"], min(4.0, timeout_s))
            if fr.returncode != 0:
                err = (fr.stderr or fr.stdout or "offline").strip().splitlines()
                tip = err[-1][:60] if err else "offline"
                return UpdateCheck("offline", tip)

        local = _run(["git", "rev-parse", "HEAD"], 3.0)
        remote = _run(["git", "rev-parse", "origin/main"], 3.0)
        if remote.returncode != 0:
            remote = _run(["git", "rev-parse", "origin/master"], 3.0)
        if local.returncode != 0 or remote.returncode != 0:
            return UpdateCheck("error", "Could not read git rev")

        loc = (local.stdout or "").strip()
        rem = (remote.stdout or "").strip()
        if not loc or not rem:
            return UpdateCheck("error", "Empty rev")
        if loc == rem:
            return UpdateCheck("up_to_date", "You're current", loc[:7], rem[:7])
        return UpdateCheck(
            "available",
            f"{loc[:7]} → {rem[:7]}",
            loc[:7],
            rem[:7],
        )
    except subprocess.TimeoutExpired:
        return UpdateCheck("offline", "Network slow")
    except Exception as e:
        return UpdateCheck("error", str(e)[:60])


def _splash_logo_path() -> Optional[Path]:
    here = Path(__file__).resolve().parent
    for p in (
        here / "assets" / "splash_logo.png",
        Path("/opt/esp-handset/esp_handset/assets/splash_logo.png"),
        Path.home()
        / "esp-phone"
        / "pi_handset"
        / "esp_handset"
        / "assets"
        / "splash_logo.png",
    ):
        if p.is_file():
            return p
    return None


class BootSplash(QWidget):
    """Brand logo + status. Fullscreen overlay that covers the taskbar."""

    finished = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Bypass WM so panel struts cannot reserve a strip under/over us
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setFocusPolicy(Qt.StrongFocus)
        try:
            self.setCursor(Qt.BlankCursor)
        except Exception:
            pass
        self._line = "hello ·"
        self._sub = ""
        self._pulse = 0
        self._result: Optional[UpdateCheck] = None
        self._done = False
        self._awaiting_choice = False
        self._finish_cb: Optional[Callable[[UpdateCheck, bool], None]] = None
        self._logo = QPixmap()
        path = _splash_logo_path()
        if path is not None:
            pm = QPixmap(str(path))
            if not pm.isNull():
                self._logo = pm
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_pulse)
        self._tick.start(120)

    def cover_screen(self, screen) -> None:
        """Cover the entire physical screen including taskbar strut area."""
        try:
            self.setScreen(screen)
        except Exception:
            pass
        # Prefer full geometry (not availableGeometry — that excludes the panel)
        g = screen.geometry()
        # Pad a few px past edges — some panels sit outside the reported rect
        self.setGeometry(g.x() - 2, g.y() - 2, g.width() + 4, g.height() + 4)
        self.show()
        QApplication.processEvents()
        try:
            h = self.windowHandle()
            if h is not None:
                h.setScreen(screen)
        except Exception:
            pass
        self.raise_()
        self.activateWindow()
        # Keep re-asserting on top while panels die
        QTimer.singleShot(50, self.raise_)
        QTimer.singleShot(200, self.raise_)
        QTimer.singleShot(500, self.raise_)


    def set_finish_callback(self, cb: Callable[[UpdateCheck, bool], None]) -> None:
        self._finish_cb = cb

    def set_line(self, line: str, sub: str = "") -> None:
        self._line = line
        self._sub = sub
        self.update()

    def apply_result(self, result: UpdateCheck) -> None:
        self._result = result
        if result.status == "available":
            self._awaiting_choice = True
            self.set_line("update ready ·", "Confirm = update  ·  Back = later")
        elif result.status == "up_to_date":
            self.set_line("all set ·", "up to date")
        elif result.status == "offline":
            self.set_line("no signal ·", result.detail or "skipping update check")
        elif result.status == "skip":
            self.set_line("ready ·", result.detail or "")
        else:
            self.set_line("ready ·", result.detail or "couldn't check")

    def request_finish(self, *, want_update: bool = False) -> None:
        if self._done:
            return
        self._done = True
        self._tick.stop()
        res = self._result or UpdateCheck("skip")
        if self._finish_cb is not None:
            try:
                self._finish_cb(res, want_update)
            except Exception:
                pass
        try:
            self.finished.emit((res, want_update))
        except Exception:
            pass

    def _on_pulse(self) -> None:
        self._pulse = (self._pulse + 1) % 40
        self.update()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if self._awaiting_choice:
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self.request_finish(want_update=True)
                event.accept()
                return
            if key in (Qt.Key_Escape, Qt.Key_Backspace):
                self.request_finish(want_update=False)
                event.accept()
                return
        if self._result is not None and not self._awaiting_choice:
            if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
                self.request_finish(want_update=False)
                event.accept()
                return
        super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#000000"))

        glow = 8 + (self._pulse % 16)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(160, 50, 45, glow))
        p.drawEllipse(int(w * 0.18), int(h * 0.1), int(w * 0.64), int(h * 0.5))

        logo_bottom = h // 2
        if not self._logo.isNull():
            scaled = self._logo.scaled(
                max(48, w - 40),
                max(48, h - 64),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            x = (w - scaled.width()) // 2
            y = max(2, (h - 52 - scaled.height()) // 2)
            p.drawPixmap(x, y, scaled)
            logo_bottom = y + scaled.height()
        else:
            p.setPen(QColor("#c44"))
            p.setFont(QFont("DejaVu Sans", 16, QFont.Bold))
            p.drawText(0, h // 2 - 16, w, 24, Qt.AlignHCenter, "DIGIVICE")

        p.setPen(QColor("#e8eef5"))
        p.setFont(QFont("DejaVu Sans", 10))
        p.drawText(
            8,
            max(logo_bottom + 4, h - 36),
            w - 16,
            14,
            Qt.AlignHCenter,
            self._line,
        )
        if self._sub:
            p.setPen(QColor("#6a7a8a"))
            p.setFont(QFont("DejaVu Sans", 8))
            p.drawText(8, h - 20, w - 16, 14, Qt.AlignHCenter, self._sub)


def _pump(app: QApplication, seconds: float) -> None:
    end = time.time() + max(0.0, seconds)
    while time.time() < end:
        app.processEvents()
        time.sleep(0.03)


def run_boot_splash(app: QApplication) -> tuple:
    """Show fullscreen splash on every screen, check updates, return result."""
    try:
        from esp_handset.desktop_chrome import hide_desktop_chrome

        hide_desktop_chrome()
    except Exception:
        pass
    app.processEvents()
    time.sleep(0.15)  # let panels die before we paint
    app.processEvents()

    from PyQt5.QtGui import QGuiApplication

    screens = list(QGuiApplication.screens() or [])
    primary = QGuiApplication.primaryScreen()
    if primary is not None and primary not in screens:
        screens.insert(0, primary)

    overlays: list = []
    splash: Optional[BootSplash] = None

    if not screens:
        splash = BootSplash()
        splash.setGeometry(0, 0, 1920, 1200)
        splash.show()
        splash.raise_()
        overlays.append(splash)
    else:
        for i, scr in enumerate(screens):
            w = BootSplash()
            w.cover_screen(scr)
            overlays.append(w)
            if i == 0 or scr is primary:
                splash = w
        if splash is None:
            splash = overlays[0]

    assert splash is not None
    splash.setFocus(Qt.OtherFocusReason)
    app.processEvents()

    def _broadcast_line(line: str, sub: str = "") -> None:
        for w in overlays:
            try:
                w.set_line(line, sub)
            except Exception:
                pass

    def _close_all() -> None:
        for w in overlays:
            try:
                w.hide()
                w.close()
            except Exception:
                pass
        overlays.clear()

    splash.set_line("hello ·", "checking updates")
    _broadcast_line("hello ·", "checking updates")
    app.processEvents()

    box: dict = {"result": None}

    def _check() -> None:
        box["result"] = check_for_updates(timeout_s=6.0)

    th = threading.Thread(target=_check, daemon=True)
    th.start()

    t0 = time.time()
    while th.is_alive() and (time.time() - t0) < 8.0:
        if time.time() - t0 > 2.5:
            _broadcast_line("looking around ·", "wifi · git")
        app.processEvents()
        time.sleep(0.04)
    th.join(timeout=0.5)

    result = box["result"] or UpdateCheck("error", "check stalled")
    for w in overlays:
        try:
            w.apply_result(result)
        except Exception:
            pass
    app.processEvents()

    done: dict = {"ok": False, "want": False, "res": result}

    def _fin(res: UpdateCheck, want: bool) -> None:
        done["ok"] = True
        done["want"] = bool(want)
        done["res"] = res

    splash.set_finish_callback(_fin)
    # Extra overlays: any key finishes without update
    for w in overlays:
        if w is splash:
            continue
        w.set_finish_callback(_fin)

    if result.status == "available":
        _broadcast_line("update ready ·", "Confirm = update  ·  Back = later")
        # Wait for Confirm / Back (buttons → keys)
        wait_s = 12.0
    else:
        wait_s = 1.4
        QTimer.singleShot(
            int(wait_s * 1000),
            lambda: splash.request_finish(want_update=False),
        )

    t1 = time.time()
    while not done["ok"] and (time.time() - t1) < max(wait_s + 2.0, 14.0):
        app.processEvents()
        time.sleep(0.03)

    if not done["ok"]:
        splash.request_finish(want_update=False)

    _close_all()
    # Digivice kiosk will cover again; don't force panel show (phone mode)
    app.processEvents()
    return done["res"], bool(done["want"])
