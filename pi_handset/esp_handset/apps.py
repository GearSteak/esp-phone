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
    for path in (Path("/etc/esp-handset/ui_mode"),):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if os.access(path.parent, os.W_OK) or (
                path.exists() and os.access(path, os.W_OK)
            ):
                path.write_text("desktop\n", encoding="utf-8")
            else:
                subprocess.run(
                    ["sudo", "-n", "tee", str(path)],
                    input=b"desktop\n",
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
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


def _stop_cardkb_poller() -> None:
    try:
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return
        for w in app.topLevelWidgets():
            poller = getattr(w, "_cardkb", None)
            if poller is None:
                continue
            try:
                poller.stop()
            except Exception:
                pass
    except Exception:
        pass


def exit_to_desktop() -> None:
    """Leave Digivice: mode=desktop, hand off SPI to desktop mirror, quit."""
    print("[handset] EXIT → Linux desktop (SPI will mirror desktop)", flush=True)
    _release_all_keyboards()
    _stop_cardkb_poller()
    _write_mode_desktop()

    # Release SPI bus without blanking — handset-session starts desktop_spi_mirror
    try:
        from esp_handset import st7789_spi as st

        if st.ready():
            st.close(blank_panel=False)
    except Exception as e:
        print(f"[handset] spi handoff: {e}", flush=True)

    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")

    # Session: kill app, restore chrome, start desktop→SPI mirror
    run_session("desktop")

    try:
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.quit()
    except Exception:
        pass

    try:
        time.sleep(0.15)
        os._exit(0)
    except Exception:
        pass


def open_maps() -> None:
    run_session("maps")


def open_browser() -> None:
    """Leave Digivice, open a light browser fullscreen, return when it exits."""
    print("[handset] OPEN browser…", flush=True)
    _release_all_keyboards()
    _stop_cardkb_poller()
    try:
        from esp_handset import st7789_spi as st

        if st.ready():
            st.close(blank_panel=False)
    except Exception as e:
        print(f"[handset] spi handoff (browser): {e}", flush=True)

    run_session("browser")

    try:
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.quit()
    except Exception:
        pass
    try:
        time.sleep(0.15)
        os._exit(0)
    except Exception:
        pass


def open_emulators() -> None:
    run_session("emulators")
