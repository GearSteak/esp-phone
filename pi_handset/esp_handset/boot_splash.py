"""Cute Digivice boot splash + lightweight update check."""

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
    # Dedup
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


def check_for_updates(*, timeout_s: float = 18.0) -> UpdateCheck:
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

    def _run(args: list, t: float = timeout_s) -> subprocess.CompletedProcess:
        return subprocess.run(
            args,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=t,
            check=False,
        )

    try:
        # Quiet fetch — fail soft if offline
        fr = _run(
            ["git", "fetch", "--quiet", "origin", "main"],
            min(timeout_s, 16.0),
        )
        if fr.returncode != 0:
            # Try without branch name
            fr = _run(["git", "fetch", "--quiet", "origin"], min(timeout_s, 12.0))
            if fr.returncode != 0:
                err = (fr.stderr or fr.stdout or "offline").strip().splitlines()
                tip = err[-1][:60] if err else "offline"
                return UpdateCheck("offline", tip)

        local = _run(["git", "rev-parse", "HEAD"], 5.0)
        remote = _run(["git", "rev-parse", "origin/main"], 5.0)
        if remote.returncode != 0:
            remote = _run(["git", "rev-parse", "origin/master"], 5.0)
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
    """Fullscreen-ish splash: Digivice egg + status line + optional Confirm."""

    finished = pyqtSignal(object)  # UpdateCheck + want_update bool via tuple

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._phase = "hello"
        self._line = "hello ·"
        self._sub = ""
        self._pulse = 0
        self._result: Optional[UpdateCheck] = None
        self._want_update = False
        self._done = False
        self._awaiting_choice = False

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_pulse)
        self._tick.start(80)

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
        self._want_update = want_update
        self._tick.stop()
        self.finished.emit((self._result or UpdateCheck("skip"), want_update))

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
        # Allow early dismiss once we have a non-choice result
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

        # Soft night gradient
        p.fillRect(self.rect(), QColor("#0a121c"))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(30, 55, 80, 40))
        p.drawEllipse(int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.55))

        # Digivice egg
        egg_w, egg_h = min(120, w - 40), min(150, h - 70)
        cx, cy = w // 2, h // 2 - 8
        egg = (
            cx - egg_w // 2,
            cy - egg_h // 2,
            egg_w,
            egg_h,
        )
        p.setBrush(QColor("#1a2838"))
        p.setPen(QPen(QColor("#3a5a7a"), 2))
        p.drawRoundedRect(*egg, egg_w // 2, egg_h // 2)

        # Screen inset
        inset = (
            egg[0] + 18,
            egg[1] + 28,
            egg_w - 36,
            int(egg_h * 0.42),
        )
        p.setBrush(QColor("#0e1a14"))
        p.setPen(QPen(QColor("#2a4a3a"), 1))
        p.drawRoundedRect(*inset, 8, 8)

        # Tiny creature blink
        blink = self._pulse < 36
        p.setPen(QPen(QColor("#7CFC9A" if blink else "#1a3a28"), 2))
        p.setBrush(Qt.NoBrush)
        eye_y = inset[1] + inset[3] // 2
        p.drawEllipse(cx - 14, eye_y - 6, 10, 10 if blink else 3)
        p.drawEllipse(cx + 4, eye_y - 6, 10, 10 if blink else 3)
        # Smile
        p.drawArc(cx - 10, eye_y + 2, 20, 12, 200 * 16, 140 * 16)

        # Antenna LED
        led = QColor("#FFE600") if (self._pulse // 5) % 2 == 0 else QColor("#8a7040")
        p.setBrush(led)
        p.setPen(QPen(QColor("#000000"), 1))
        p.drawEllipse(cx - 5, egg[1] - 6, 10, 10)

        # Brand
        p.setPen(QColor("#e8eef5"))
        p.setFont(QFont("DejaVu Sans", 11, QFont.Bold))
        p.drawText(0, egg[1] + egg_h + 4, w, 16, Qt.AlignHCenter, "DIGIVICE")

        # Status
        p.setPen(QColor("#9ab"))
        p.setFont(QFont("DejaVu Sans", 10))
        p.drawText(8, h - 36, w - 16, 14, Qt.AlignHCenter, self._line)
        if self._sub:
            p.setPen(QColor("#6a7a8a"))
            p.setFont(QFont("DejaVu Sans", 8))
            p.drawText(8, h - 20, w - 16, 14, Qt.AlignHCenter, self._sub)


def run_boot_splash(
    app: QApplication,
    *,
    prepare: Optional[Callable[[Callable[[str, str], None]], None]] = None,
) -> tuple:
    """Show splash, check updates, optionally run prepare(status_cb).

    Returns (UpdateCheck, want_update: bool).
    """
    splash = BootSplash()
    # Match Digivice canvas size when possible
    try:
        from esp_handset import display_geom as geom

        geom.apply_kiosk(splash)
    except Exception:
        splash.resize(320, 240)
        splash.show()
    else:
        splash.show()
    splash.raise_()
    splash.activateWindow()
    splash.setFocus(Qt.OtherFocusReason)
    app.processEvents()

    splash.set_line("hello ·", "waking up")
    app.processEvents()

    box: dict = {"result": None}

    def _check() -> None:
        box["result"] = check_for_updates()

    th = threading.Thread(target=_check, daemon=True)
    th.start()

    # Bring up radio/UI deps while git fetch runs (same cute screen)
    if prepare is not None:

        def _status(line: str, sub: str = "") -> None:
            # Don't clobber update-check phrases too aggressively
            if th.is_alive():
                splash.set_line(line, sub or "checking updates…")
            else:
                splash.set_line(line, sub)
            app.processEvents()

        try:
            prepare(_status)
        except Exception as e:
            splash.set_line("ready ·", str(e)[:40])
            app.processEvents()

    phrases = [
        ("looking around ·", "wifi · git"),
        ("checking updates ·", "one moment"),
    ]
    t0 = time.time()
    pi = 0
    while th.is_alive() and (time.time() - t0) < 22.0:
        if prepare is None:
            idx = min(pi, len(phrases) - 1)
            if int(time.time() - t0) // 2 != pi:
                splash.set_line(*phrases[idx])
                pi = int(time.time() - t0) // 2
        app.processEvents()
        time.sleep(0.05)
    th.join(timeout=1.0)

    result = box["result"] or UpdateCheck("error", "No result")
    splash.apply_result(result)
    app.processEvents()

    outcome: dict = {"done": False, "want": False, "result": result}

    def _on_fin(payload) -> None:
        res, want = payload
        outcome["result"] = res
        outcome["want"] = want
        outcome["done"] = True

    splash.finished.connect(_on_fin)

    if result.status == "available":
        # Wait for Confirm / Back, max ~10s then later
        deadline = time.time() + 10.0
        while not outcome["done"] and time.time() < deadline:
            app.processEvents()
            time.sleep(0.04)
        if not outcome["done"]:
            splash.request_finish(want_update=False)
            while not outcome["done"]:
                app.processEvents()
                time.sleep(0.02)
    else:
        # Brief beat so the cute screen can be seen
        hold = 1.4 if result.status == "up_to_date" else 1.0
        end = time.time() + hold
        while not outcome["done"] and time.time() < end:
            app.processEvents()
            time.sleep(0.04)
        if not outcome["done"]:
            splash.request_finish(want_update=False)
            while not outcome["done"]:
                app.processEvents()
                time.sleep(0.02)

    try:
        splash.close()
    except Exception:
        pass
    app.processEvents()
    return outcome["result"], bool(outcome["want"])
