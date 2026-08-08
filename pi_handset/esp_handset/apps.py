"""External app launch helpers (maps / browser / desktop)."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional


def _session_bin() -> str:
    for p in (
        "/usr/local/bin/handset-session",
        str(Path(__file__).resolve().parents[1] / "session" / "handset-session.sh"),
    ):
        if os.path.isfile(p):
            return p
    return "handset-session"


def run_session(cmd: str) -> None:
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")
    bin_path = _session_bin()
    try:
        if bin_path.endswith(".sh"):
            subprocess.Popen(
                ["bash", bin_path, cmd],
                start_new_session=True,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                [bin_path, cmd],
                start_new_session=True,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception as e:
        print(f"[handset] run_session {cmd}: {e}", flush=True)


def which_any(*names: str) -> Optional[str]:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def _write_mode_desktop() -> None:
    """Persist desktop so autostart does not immediately relaunch Digivice."""
    home = Path.home() / ".esp-handset"
    try:
        home.mkdir(parents=True, exist_ok=True)
        (home / "session_mode").write_text("desktop\n", encoding="utf-8")
    except OSError:
        pass
    try:
        p = Path("/etc/esp-handset/ui_mode")
        if p.parent.is_dir() and os.access(p.parent, os.W_OK):
            p.write_text("desktop\n", encoding="utf-8")
    except OSError:
        pass


def _release_all_keyboards() -> None:
    try:
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return
        for w in app.topLevelWidgets():
            try:
                w.releaseKeyboard()
            except Exception:
                pass
    except Exception:
        pass


def exit_to_desktop() -> None:
    """Leave Digivice hard: mode=desktop, restore displays, kill phone UI, quit."""
    print("[handset] EXIT → Linux desktop", flush=True)
    _release_all_keyboards()
    _write_mode_desktop()

    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")

    # Prefer full session helper; also do emergency kill locally so we always leave
    run_session("desktop")

    # Local hard guarantee even if handset-session is missing/broken
    try:
        subprocess.Popen(
            ["bash", "-c", "sleep 0.3; pkill -f handset_app.py || true"],
            start_new_session=True,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

    # Restore HDMI if possible without waiting for session script
    try:
        restore = "/usr/local/bin/digivice-restore-desktop"
        if not os.path.isfile(restore):
            restore = str(
                Path(__file__).resolve().parents[1]
                / "session"
                / "restore-desktop-displays.sh"
            )
        if os.path.isfile(restore):
            subprocess.Popen(
                ["bash", restore],
                start_new_session=True,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass

    try:
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.quit()
    except Exception:
        pass

    # Nuclear: if quit is ignored by a stuck dialog, die after a beat
    try:
        time.sleep(0.15)
        os._exit(0)
    except Exception:
        pass


def open_maps() -> None:
    run_session("maps")


def open_browser() -> None:
    run_session("browser")


def open_emulators() -> None:
    run_session("emulators")
