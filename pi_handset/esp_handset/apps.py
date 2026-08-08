"""External app launch helpers (maps / browser / desktop)."""

from __future__ import annotations

import os
import shutil
import subprocess
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
    subprocess.Popen([_session_bin(), cmd], start_new_session=True)


def which_any(*names: str) -> Optional[str]:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def exit_to_desktop() -> None:
    run_session("desktop")


def open_maps() -> None:
    run_session("maps")


def open_browser() -> None:
    run_session("browser")


def open_emulators() -> None:
    run_session("emulators")
