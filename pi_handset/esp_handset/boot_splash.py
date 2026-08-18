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


def _network_reachable(timeout: float = 0.6) -> bool:
    """Fast probe — avoid hanging git fetch when there is no route."""
    import socket

    for host, port in (("1.1.1.1", 53), ("8.8.8.8", 53), ("1.1.1.1", 443)):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def _installed_rev() -> str:
    """Best-effort short SHA of the installed Digivice build in /opt."""
    candidates = (
        Path("/etc/esp-handset/last_update"),
        Path.home() / ".esp-handset" / "last_update",
        Path.home() / ".esp-handset" / "last_gui_update",
    )
    for path in candidates:
        try:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        for token in text.replace("\n", " ").split():
            if token.startswith("rev="):
                rev = token.split("=", 1)[-1].strip()
                if rev and rev != "?":
                    return rev[:7]
    return ""


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

    if not _network_reachable(min(0.8, timeout_s * 0.15)):
        inst7 = _installed_rev()
        if inst7:
            return UpdateCheck("offline", "no Wi‑Fi · update later")
        return UpdateCheck("offline", "no Wi‑Fi · booting")

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
        loc7 = loc[:7]
        rem7 = rem[:7]
        inst7 = _installed_rev()

        # Normal case: local repo itself is behind GitHub.
        if loc != rem:
            if inst7 and inst7 != loc7:
                detail = f"installed {inst7} · repo {loc7} · remote {rem7}"
            else:
                detail = f"{loc7} → {rem7}"
            return UpdateCheck("available", detail, loc7, rem7)

        # Repo is current, but the installed /opt copy is still stale.
        if inst7 and inst7 != loc7:
            return UpdateCheck(
                "available",
                f"installed {inst7} → repo {loc7}",
                inst7,
                loc7,
            )

        if loc == rem:
            detail = "You're current"
            if inst7:
                detail = f"installed {inst7} · repo {loc7}"
            return UpdateCheck("up_to_date", detail, loc7, rem7)
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
    """Brand logo + status. Fullscreen overlay (not an SPI kiosk source)."""

    finished = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Normal topmost window — X11BypassWindowManagerHint crashed Digivice on Pi
        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
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
        """Pin this splash to one QScreen and go true fullscreen."""
        try:
            self.setScreen(screen)
        except Exception:
            pass
        g = screen.geometry()
        self.setGeometry(g)
        self.show()
        QApplication.processEvents()
        try:
            h = self.windowHandle()
            if h is not None:
                h.setScreen(screen)
                h.setGeometry(g)
        except Exception:
            pass
        self.showFullScreen()
        self.setGeometry(g)
        self.raise_()
        self.activateWindow()


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
            self.set_line("offline ·", result.detail or "booting without Wi‑Fi")
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


class SplashStatus(QWidget):
    """In-page splash look (Settings → Update)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._line = "hello ·"
        self._sub = "checking updates"
        self._pulse = 0
        self._logo = QPixmap()
        path = _splash_logo_path()
        if path is not None:
            pm = QPixmap(str(path))
            if not pm.isNull():
                self._logo = pm
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_pulse)
        self._tick.start(120)
        self.setMinimumHeight(140)

    def set_line(self, line: str, sub: str = "") -> None:
        self._line = line
        self._sub = sub
        self.update()

    def _on_pulse(self) -> None:
        self._pulse = (self._pulse + 1) % 40
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#000000"))
        glow = 8 + (self._pulse % 16)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(160, 50, 45, glow))
        p.drawEllipse(int(w * 0.16), int(h * 0.04), int(w * 0.68), int(h * 0.55))
        logo_bottom = h // 2
        if not self._logo.isNull():
            scaled = self._logo.scaled(
                max(40, w - 36),
                max(40, h - 48),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            x = (w - scaled.width()) // 2
            y = max(2, (h - 44 - scaled.height()) // 2)
            p.drawPixmap(x, y, scaled)
            logo_bottom = y + scaled.height()
        p.setPen(QColor("#e8eef5"))
        p.setFont(QFont("DejaVu Sans", 10))
        p.drawText(
            6,
            max(logo_bottom + 2, h - 32),
            w - 12,
            14,
            Qt.AlignHCenter,
            self._line,
        )
        if self._sub:
            p.setPen(QColor("#6a7a8a"))
            p.setFont(QFont("DejaVu Sans", 8))
            p.drawText(6, h - 16, w - 12, 14, Qt.AlignHCenter, self._sub)


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

    from PyQt5.QtGui import QGuiApplication

    screens = list(QGuiApplication.screens() or [])
    primary = QGuiApplication.primaryScreen()
    if primary is not None and primary not in screens:
        screens.insert(0, primary)

    overlays: list = []
    splash: Optional[BootSplash] = None

    if not screens:
        # Headless / no QScreen yet — still paint a large black window
        splash = BootSplash()
        splash.resize(1920, 1080)
        splash.move(0, 0)
        splash.showFullScreen()
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
        box["result"] = check_for_updates(timeout_s=4.0)

    th = threading.Thread(target=_check, daemon=True)
    th.start()

    t0 = time.time()
    while th.is_alive() and (time.time() - t0) < 5.0:
        if time.time() - t0 > 1.5:
            _broadcast_line("looking around ·", "wifi · git")
        app.processEvents()
        time.sleep(0.04)
    th.join(timeout=0.3)

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

    online = _network_reachable(0.5)
    if result.status == "available" and online:
        _broadcast_line("update ready ·", "Confirm = update  ·  Back = later")
        # Wait for Confirm / Back (buttons → keys)
        wait_s = 12.0
    elif result.status == "available":
        # Cached git refs can look "available" offline — never block boot for that.
        _broadcast_line("offline ·", "update when online")
        wait_s = 0.35
        QTimer.singleShot(
            int(wait_s * 1000),
            lambda: splash.request_finish(want_update=False),
        )
    else:
        wait_s = 0.35 if result.status == "offline" else 0.9
        QTimer.singleShot(
            int(wait_s * 1000),
            lambda: splash.request_finish(want_update=False),
        )

    t1 = time.time()
    cap = 14.0 if (result.status == "available" and online) else max(wait_s + 0.8, 2.5)
    while not done["ok"] and (time.time() - t1) < cap:
        app.processEvents()
        time.sleep(0.03)

    if not done["ok"]:
        splash.request_finish(want_update=False)

    _close_all()
    # Digivice kiosk will cover again; don't force panel show (phone mode)
    app.processEvents()
    return done["res"], bool(done["want"])
