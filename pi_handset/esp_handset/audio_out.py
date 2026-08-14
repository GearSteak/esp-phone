"""Digivice playback — must call the same digivice-audio-fix as the terminal."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from shutil import which
from typing import List, Optional, Sequence, Tuple

AUDIO_BUILD = "v7-cli"
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


def _write_log(text: str) -> None:
    try:
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        _LOG.write_text(text, encoding="utf-8")
    except OSError:
        pass


def wake_usb_audio() -> None:
    fix = _fix_bin()
    if not fix:
        return
    try:
        subprocess.run(
            ["sudo", "-n", fix, "--persist-only"],
            capture_output=True,
            timeout=8,
            check=False,
        )
    except Exception:
        pass


def _run(cmd: Sequence[str], timeout: float) -> Tuple[int, str]:
    try:
        r = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        return r.returncode, out
    except subprocess.TimeoutExpired as e:
        out = ""
        for chunk in (e.stdout, e.stderr):
            if not chunk:
                continue
            out += chunk if isinstance(chunk, str) else chunk.decode("utf-8", "replace")
        return 124, (out or "timeout").strip()
    except Exception as e:
        return 1, str(e)


def play_test_tone(*, seconds: float = 2.0) -> bool:
    del seconds
    ok, _ = play_test_tone_detail()
    return ok


def play_test_tone_detail(*, seconds: float = 2.0) -> Tuple[bool, str]:
    """Exact CLI path: sudo digivice-audio-fix (no soft fallback that fakes success)."""
    del seconds
    stamp = datetime.now().isoformat(timespec="seconds")
    lines = [f"build={AUDIO_BUILD}", f"when={stamp}"]

    fix = _fix_bin()
    lines.append(f"fix_bin={fix or 'MISSING'}")
    if not fix:
        msg = "digivice-audio-fix missing"
        _write_log("\n".join(lines + [msg]) + "\n")
        return False, msg

    # Same command that works in the terminal — no --beep, no user-path fallback
    cmd = ["sudo", "-n", fix]
    lines.append(f"try: {' '.join(cmd)}")
    code, out = _run(cmd, timeout=60.0)
    lines.append(f"exit={code}")
    if out:
        lines.append(out[-2000:])
    _write_log("\n".join(lines) + "\n")

    if code in (0, 124):
        # Confirm the script actually ran speaker-test (not a silent early exit)
        if "speaker-test" in out.lower() or "WATCH RED LED" in out or "beep:" in out:
            return True, f"{AUDIO_BUILD} CLI fix OK"
        if code == 124:
            return True, f"{AUDIO_BUILD} timed out (may have played)"
        return True, f"{AUDIO_BUILD} exit 0 · check headphones"

    if "password" in out.lower() or "a password is required" in out.lower():
        return False, "sudo blocked — run: sudo digivice-full-update"
    tail = (out.splitlines()[-1] if out else f"exit {code}")[:40]
    return False, f"fix fail: {tail}"


def play_cmd_for_debug() -> List[str]:
    fix = _fix_bin()
    if fix:
        return ["sudo", "-n", fix]
    return []
