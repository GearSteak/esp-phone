"""Digivice playback — soft-beep only, hard timeouts, no UI hang."""

from __future__ import annotations

import os
import signal
import subprocess
from datetime import datetime
from pathlib import Path
from shutil import which
from typing import List, Optional, Tuple

AUDIO_BUILD = "v9"
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
    """Run sudo digivice-audio-fix; always return within timeout (kill process group)."""
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
    logf = open(_LOG, "a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=logf,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            logf.write("\n[timeout — killed]\n")
            code = 124
    except Exception as e:
        logf.write(f"\n[error] {e}\n")
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


def play_test_tone(*, seconds: float = 2.0) -> bool:
    del seconds
    ok, _ = play_test_tone_detail()
    return ok


def play_test_tone_detail(*, seconds: float = 2.0) -> Tuple[bool, str]:
    """Soft-beep only (≤12s). Full fix was hanging Digivice on pipewire restart."""
    del seconds
    fix = _fix_bin()
    if not fix:
        return False, "fix missing"

    code, out = _run_fix_detached(["--soft-beep"], timeout=12.0)
    played = (
        "speaker-test exit=" in out
        or "WATCH RED LED" in out
        or "soft-beep" in out
        or "[timeout" in out
    )
    if code in (0, 124) and played:
        return True, f"{AUDIO_BUILD} done"
    if "password" in out.lower():
        return False, "sudo blocked"
    if "no USB" in out.lower() or "ERROR: no USB" in out:
        return False, "no USB card"
    for line in reversed(out.splitlines()):
        line = line.strip()
        if line.startswith("speaker-test exit="):
            return code in (0, 124), f"{AUDIO_BUILD} {line}"
        if line and not line.startswith("build=") and line != "---":
            if "mix " in line or "Stopping" in line:
                continue
            return False, line[:40]
    return False, f"fail exit={code}"


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
