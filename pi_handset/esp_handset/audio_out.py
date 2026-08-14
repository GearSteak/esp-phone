"""Digivice playback — exclusive USB beep (same as CLI digivice-audio-fix)."""

from __future__ import annotations

import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from shutil import which
from typing import List, Optional, Sequence, Tuple

AUDIO_BUILD = "v6-loud"
_LOG = Path.home() / ".esp-handset" / "last-beep.txt"


def _usb_card() -> Optional[str]:
    p = Path("/etc/esp-handset/alsa-card")
    try:
        if p.is_file():
            c = p.read_text(encoding="utf-8").strip()
            if c.isdigit():
                return c
    except OSError:
        pass
    try:
        r = subprocess.run(
            ["aplay", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return None
    for line in (r.stdout or "").splitlines():
        m = re.match(r"^card (\d+):", line)
        if not m:
            continue
        low = line.lower()
        if any(x in low for x in ("hdmi", "vc4", "bcm2835")):
            continue
        if any(x in low for x in ("usb", "device", "c-media", "audio")):
            return m.group(1)
    return None


def _fix_bin() -> Optional[str]:
    for p in (
        "/usr/local/bin/digivice-audio-fix",
        "/opt/esp-handset/session/digivice-audio-fix.sh",
        str(Path(__file__).resolve().parents[1] / "session" / "digivice-audio-fix.sh"),
    ):
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    w = which("digivice-audio-fix")
    return w


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


def _run(cmd: Sequence[str], timeout: float = 6.0) -> Tuple[int, str]:
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
        if e.stdout:
            out += e.stdout if isinstance(e.stdout, str) else e.stdout.decode(
                "utf-8", "replace"
            )
        if e.stderr:
            out += e.stderr if isinstance(e.stderr, str) else e.stderr.decode(
                "utf-8", "replace"
            )
        return 124, (out or "timeout").strip()
    except Exception as e:
        return 1, str(e)


def _pw(action: str) -> None:
    units = ["pipewire-pulse", "wireplumber", "pipewire"]
    if action == "stop":
        subprocess.run(
            ["systemctl", "--user", "stop", *units],
            capture_output=True,
            timeout=8,
            check=False,
        )
    else:
        subprocess.run(
            ["systemctl", "--user", "start", "pipewire", "wireplumber", "pipewire-pulse"],
            capture_output=True,
            timeout=8,
            check=False,
        )


def _unmute(card: str) -> None:
    for ctl in ("Speaker", "PCM", "Master", "Headphone"):
        subprocess.run(
            ["amixer", "-c", card, "-q", "sset", ctl, "100%", "unmute"],
            capture_output=True,
            timeout=3,
            check=False,
        )


def play_test_tone(*, seconds: float = 2.0) -> bool:
    ok, _ = play_test_tone_detail(seconds=seconds)
    return ok


def play_test_tone_detail(*, seconds: float = 2.0) -> Tuple[bool, str]:
    """Run the same root fix that works from SSH (hard USB reset + exclusive ALSA)."""
    stamp = datetime.now().isoformat(timespec="seconds")
    lines = [f"build={AUDIO_BUILD}", f"when={stamp}"]

    fix = _fix_bin()
    lines.append(f"fix_bin={fix or 'MISSING'}")

    if fix:
        # Prefer --beep (hard re-auth); fall back to full script (no args)
        for args in (["--beep"], []):
            cmd = ["sudo", "-n", fix, *args]
            lines.append(f"try: {' '.join(cmd)}")
            code, out = _run(cmd, timeout=45.0)
            lines.append(f"exit={code}")
            if out:
                lines.append(out[-1500:])
            _write_log("\n".join(lines) + "\n")
            if code in (0, 124):
                return True, f"{AUDIO_BUILD} OK · watch LED"
            # sudo password required / missing NOPASSWD
            if "password" in out.lower() or code == 1 and "sudo" in out.lower():
                lines.append("sudo failed — need NOPASSWD digivice-audio-fix")
            # --beep unknown on ancient script still runs full path; if fail try next
        _write_log("\n".join(lines) + "\n")

    # Last resort without root (often silent on C-Media)
    wake_usb_audio()
    card = _usb_card() or "1"
    if not which("speaker-test"):
        msg = "speaker-test missing"
        lines.append(msg)
        _write_log("\n".join(lines) + "\n")
        return False, msg

    _pw("stop")
    time.sleep(0.7)
    try:
        pcm = f"/dev/snd/pcmC{card}D0p"
        if os.path.exists(pcm):
            subprocess.run(
                ["fuser", "-k", pcm],
                capture_output=True,
                timeout=3,
                check=False,
            )
    except Exception:
        pass
    _unmute(card)
    code, out = _run(
        [
            "speaker-test",
            "-D",
            f"plughw:{card},0",
            "-c",
            "2",
            "-r",
            "48000",
            "-t",
            "sine",
            "-f",
            "880",
            "-l",
            "1",
        ],
        timeout=max(5.0, seconds + 3.0),
    )
    _pw("start")
    lines.append(f"user_path card={card} exit={code}")
    if out:
        lines.append(out[-800:])
    _write_log("\n".join(lines) + "\n")
    if code in (0, 124):
        return True, f"user plughw:{card},0 (no sudo)"
    return False, f"sudo+user fail · see Transfer last-beep"


def play_cmd_for_debug() -> List[str]:
    fix = _fix_bin()
    if fix:
        return ["sudo", "-n", fix, "--beep"]
    return []
