"""Digivice playback — run audio fix detached (no pkill race, no PIPE stall)."""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from shutil import which
from typing import List, Optional, Tuple

AUDIO_BUILD = "v8-detach"
_LOG = Path.home() / ".esp-handset" / "last-beep.txt"


def _fix_bin() -> Optional[str]:
    for p in (
        "/usr/local/bin/digivice-audio-fix",
        "/opt/esp-handset/session/digivice-audio-fix.sh",
        str(Path(__file__).resolve().parents[1] / "session" / "digivice-audio-fix.sh"),
    ):
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return which("digivice-audio-fix")


def wake_usb_audio() -> None:
    fix = _fix_bin()
    if not fix:
        return
    try:
        subprocess.run(
            ["sudo", "-n", fix, "--persist-only"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
            check=False,
            start_new_session=True,
        )
    except Exception:
        pass


def _run_fix_detached(args: List[str], timeout: float) -> Tuple[int, str]:
    """Run sudo digivice-audio-fix in its own session; log to file (not PIPE)."""
    fix = _fix_bin()
    if not fix:
        return 1, "digivice-audio-fix missing"
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"build={AUDIO_BUILD}\n"
        f"when={datetime.now().isoformat(timespec='seconds')}\n"
        f"cmd=sudo -n {fix} {' '.join(args)}\n"
        f"---\n"
    )
    _LOG.write_text(header, encoding="utf-8")
    cmd = ["sudo", "-n", fix, *args]
    try:
        with open(_LOG, "a", encoding="utf-8") as logf:
            r = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=logf,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
                start_new_session=True,  # survive Digivice pkill of process group
            )
        code = r.returncode
    except subprocess.TimeoutExpired:
        code = 124
    except Exception as e:
        return 1, str(e)
    try:
        out = _LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        out = f"exit {code}"
    return code, out


def play_test_tone(*, seconds: float = 2.0) -> bool:
    del seconds
    ok, _ = play_test_tone_detail()
    return ok


def play_test_tone_detail(*, seconds: float = 2.0) -> Tuple[bool, str]:
    """Prefer soft-beep (no USB yank); then full CLI fix. Never fake OK."""
    del seconds
    fix = _fix_bin()
    if not fix:
        return False, "digivice-audio-fix missing"

    # 1) soft-beep — same exclusive ALSA as terminal, no re-auth
    code, out = _run_fix_detached(["--soft-beep"], timeout=25.0)
    if code in (0, 124) and (
        "speaker-test exit=" in out or "WATCH RED LED" in out or "soft-beep" in out
    ):
        return True, f"{AUDIO_BUILD} soft OK · hear?"

    # 2) full terminal command
    code2, out2 = _run_fix_detached([], timeout=60.0)
    if code2 in (0, 124) and (
        "speaker-test" in out2.lower() or "WATCH RED LED" in out2 or "beep:" in out2
    ):
        return True, f"{AUDIO_BUILD} full OK · hear?"

    combined = (out + "\n" + out2)[-1200:]
    if "password" in combined.lower():
        return False, "sudo blocked — sudo digivice-full-update"
    # Surface last log line on Digivice
    for line in reversed(combined.splitlines()):
        line = line.strip()
        if line and not line.startswith("build=") and line != "---":
            return False, line[:48]
    return False, f"fail soft={code} full={code2}"


def play_cmd_for_debug() -> List[str]:
    fix = _fix_bin()
    if fix:
        return ["sudo", "-n", fix, "--soft-beep"]
    return []


def last_beep_tail(n: int = 6) -> str:
    try:
        lines = _LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except OSError:
        return "(no last-beep.txt)"
