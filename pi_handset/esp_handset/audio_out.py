"""Digivice playback — recover C-Media stick, then ui-beep."""

from __future__ import annotations

import os
import signal
import subprocess
from datetime import datetime
from pathlib import Path
from shutil import which
from typing import List, Optional, Tuple

AUDIO_BUILD = "v11"
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


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=2)
    except Exception:
        pass


def _run_fix_detached(args: List[str], timeout: float) -> Tuple[int, str]:
    fix = _fix_bin()
    if not fix:
        return 1, "digivice-audio-fix missing"
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"build={AUDIO_BUILD}\n"
        f"when={datetime.now().isoformat(timespec='seconds')}\n"
        f"user={os.environ.get('USER', '?')}\n"
        f"cmd=sudo -n {fix} {' '.join(args)}\n"
        f"---\n"
    )
    _LOG.write_text(header, encoding="utf-8")
    cmd = ["sudo", "-n", fix, *args]
    env = os.environ.copy()
    me = os.environ.get("USER") or os.environ.get("LOGNAME")
    if me and me != "root":
        env["SUDO_USER"] = me
    logf = open(_LOG, "a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=logf,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                logf.write("\n[timeout — killed]\n")
            except Exception:
                pass
            code = 124
    except Exception as e:
        try:
            logf.write(f"\n[error] {e}\n")
        except Exception:
            pass
        return 1, str(e)
    finally:
        try:
            logf.close()
        except Exception:
            pass
    try:
        out = _LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        out = f"exit {code}"
    return code, out


def wake_usb_audio() -> None:
    """Recover C-Media into ALSA (authorized=1 + rebind)."""
    _run_fix_detached(["--recover"], timeout=15.0)


def play_test_tone(*, seconds: float = 2.0) -> bool:
    del seconds
    ok, _ = play_test_tone_detail()
    return ok


def play_test_tone_detail(*, seconds: float = 2.0) -> Tuple[bool, str]:
    del seconds
    if not _fix_bin():
        return False, "fix missing"

    # Recover first if stick vanished from ALSA
    code_r, out_r = _run_fix_detached(["--recover"], timeout=15.0)
    if "OK card=" not in out_r and "ERROR" in out_r:
        # Still try beep — recover logs help
        pass

    code, out = _run_fix_detached(["--ui-beep"], timeout=20.0)
    combined = out_r + "\n" + out
    if "password" in combined.lower():
        return False, "sudo blocked"
    if "ERROR: no USB card" in combined or "FAIL: stick not in ALSA" in combined:
        return False, "No stick — unplug/replug"
    played = (
        "aplay exit=" in out
        or "speaker-test exit=" in out
        or "LISTEN NOW" in out
        or "ui-beep card=" in out
    )
    if played and code in (0, 124):
        for line in out.splitlines():
            if "aplay exit=" in line or "speaker-test exit=" in line:
                return True, f"{AUDIO_BUILD} {line.strip()[-18:]}"
        return True, f"{AUDIO_BUILD} done"
    for line in reversed(combined.splitlines()):
        line = line.strip()
        if line.startswith("[audio-fix]"):
            msg = line.replace("[audio-fix] ", "")
            if "gui_user=" in msg or "mixer:" in msg:
                continue
            return False, msg[:40]
    return False, f"fail exit={code}"


def play_cmd_for_debug() -> List[str]:
    fix = _fix_bin()
    if fix:
        return ["sudo", "-n", fix, "--ui-beep"]
    return []


def last_beep_tail(n: int = 8) -> str:
    try:
        lines = _LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except OSError:
        return "(no last-beep.txt)"
