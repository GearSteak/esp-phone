"""Cute Digivice boot splash + lightweight update check.

Important: do NOT attach ST7789/SPI kiosk to this window — that stole the panel
and left Digivice looking frozen on the egg after the real UI started.
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
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
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
    """Fetch origin and compare HEAD to origin/main (best-effort, never raises)."""
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


class BootSplash(QWidget):
    """Short overlay: Digivice egg + status. Not an SPI kiosk source."""

    finished = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Tool + topmost for HDMI glance; SPI panel uses PhoneShell kiosk only
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._line = "hello ·"
        self._sub = ""
        self._pulse = 0
        self._result: Optional[UpdateCheck] = None
        self._done = False
        self._awaiting_choice = False
        self._finish_cb: Optional[Callable[[UpdateCheck, bool], None]] = None

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_pulse)
        self._tick.start(80)

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
        w, h = self.width(), self.height()

        p.fillRect(self.rect(), QColor("#0a121c"))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(30, 55, 80, 40))
        p.drawEllipse(int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.55))

        egg_w, egg_h = min(120, w - 40), min(150, h - 70)
        cx, cy = w // 2, h // 2 - 8
        egg = (cx - egg_w // 2, cy - egg_h // 2, egg_w, egg_h)
        p.setBrush(QColor("#1a2838"))
        p.setPen(QPen(QColor("#3a5a7a"), 2))
        p.drawRoundedRect(*egg, egg_w // 2, egg_h // 2)

        inset = (egg[0] + 18, egg[1] + 28, egg_w - 36, int(egg_h * 0.42))
        p.setBrush(QColor("#0e1a14"))
        p.setPen(QPen(QColor("#2a4a3a"), 1))
        p.drawRoundedRect(*inset, 8, 8)

        blink = self._pulse < 36
        p.setPen(QPen(QColor("#7CFC9A" if blink else "#1a3a28"), 2))
        p.setBrush(Qt.NoBrush)
        eye_y = inset[1] + inset[3] // 2
        p.drawEllipse(cx - 14, eye_y - 6, 10, 10 if blink else 3)
        p.drawEllipse(cx + 4, eye_y - 6, 10, 10 if blink else 3)
        p.drawArc(cx - 10, eye_y + 2, 20, 12, 200 * 16, 140 * 16)

        led = QColor("#FFE600") if (self._pulse // 5) % 2 == 0 else QColor("#8a7040")
        p.setBrush(led)
        p.setPen(QPen(QColor("#000000"), 1))
        p.drawEllipse(cx - 5, egg[1] - 6, 10, 10)

        p.setPen(QColor("#e8eef5"))
        p.setFont(QFont("DejaVu Sans", 11, QFont.Bold))
        p.drawText(0, egg[1] + egg_h + 4, w, 16, Qt.AlignHCenter, "DIGIVICE")

        p.setPen(QColor("#9ab"))
        p.setFont(QFont("DejaVu Sans", 10))
        p.drawText(8, h - 36, w - 16, 14, Qt.AlignHCenter, self._line)
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
    """Show splash, check updates (capped), return (UpdateCheck, want_update).

    Does not open modem/SPI — callers do that after so the panel never sticks.
    """
    try:
        from esp_handset import display_geom as geom

        w, h = int(getattr(geom, "W", 320)), int(getattr(geom, "H", 240))
    except Exception:
        w, h = 320, 240

    splash = BootSplash()
    splash.resize(w, h)
    splash.show()
    splash.raise_()
    splash.activateWindow()
    splash.setFocus(Qt.OtherFocusReason)
    app.processEvents()

    splash.set_line("hello ·", "checking updates")
    app.processEvents()

    box: dict = {"result": None}

    def _check() -> None:
        box["result"] = check_for_updates(timeout_s=6.0)

    th = threading.Thread(target=_check, daemon=True)
    th.start()

    # Hard cap so we never sit here forever (git/DNS hang, etc.)
    t0 = time.time()
    while th.is_alive() and (time.time() - t0) < 8.0:
        elapsed = time.time() - t0
        if elapsed > 2.5:
            splash.set_line("looking around ·", "wifi · git")
        app.processEvents()
        time.sleep(0.04)
    th.join(timeout=0.5)

    result = box["result"] or UpdateCheck("offline", "Taking too long")
    splash.apply_result(result)
    app.processEvents()

    outcome: dict = {"done": False, "want": False, "result": result}

    def _fin(res: UpdateCheck, want: bool) -> None:
        outcome["result"] = res
        outcome["want"] = want
        outcome["done"] = True

    splash.set_finish_callback(_fin)

    if result.status == "available":
        splash.set_line("update ready ·", "Confirm = update  ·  Back = later")
        deadline = time.time() + 8.0
        while not outcome["done"] and time.time() < deadline:
            app.processEvents()
            time.sleep(0.04)
        if not outcome["done"]:
            splash.request_finish(want_update=False)
    else:
        _pump(app, 0.9 if result.status == "up_to_date" else 0.7)
        if not outcome["done"]:
            splash.request_finish(want_update=False)

    # Ensure we never block on the callback
    guard = time.time() + 1.0
    while not outcome["done"] and time.time() < guard:
        app.processEvents()
        time.sleep(0.02)
    if not outcome["done"]:
        outcome["done"] = True
        outcome["want"] = False

    try:
        splash.hide()
        splash.close()
        splash.deleteLater()
    except Exception:
        pass
    app.processEvents()
    return outcome["result"], bool(outcome["want"])
