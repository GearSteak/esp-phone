"""Digivice playback — exclusive USB beep (stop PipeWire, ALSA plughw)."""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from shutil import which
from typing import List, Optional, Sequence, Tuple


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
    ):
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return which("digivice-audio-fix")


def wake_usb_audio() -> None:
    """Best-effort C-Media wake (sudo if NOPASSWD is set)."""
    fix = _fix_bin()
    if fix:
        try:
            subprocess.run(
                ["sudo", "-n", fix, "--persist-only"],
                capture_output=True,
                timeout=8,
                check=False,
            )
            return
        except Exception:
            pass
    # Without sudo: try writing power/control if writable
    try:
        for d in Path("/sys/bus/usb/devices").iterdir():
            vend = d / "idVendor"
            if not vend.is_file():
                continue
            if vend.read_text().strip() != "0d8c":
                continue
            ctrl = d / "power" / "control"
            if ctrl.is_file() and os.access(ctrl, os.W_OK):
                ctrl.write_text("on")
    except Exception:
        pass


def _run(cmd: Sequence[str], timeout: float = 6.0) -> Tuple[bool, str]:
    try:
        r = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        return r.returncode in (0, 124), out[-200:] if out else f"exit {r.returncode}"
    except subprocess.TimeoutExpired:
        return True, "timeout (tone may have played)"
    except Exception as e:
        return False, str(e)


def _pw(action: str) -> None:
    """Stop/start user PipeWire so ALSA can own the USB stick."""
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
    """Exclusive beep. Prefer in-process PW stop (no sudo). Fallback: fix --beep.

    Returns (ok, short status message).
    """
    # 1) Root fix script (same as CLI) if passwordless sudo works
    fix = _fix_bin()
    if fix:
        ok, msg = _run(["sudo", "-n", fix, "--beep"], timeout=22.0)
        if ok:
            return True, "fix --beep OK"
        # sudo failed (no NOPASSWD / missing) — fall through to user path

    wake_usb_audio()
    card = _usb_card()
    if card is None:
        # last resort: first non-HDMI card from aplay -l already failed
        card = "1"
    if not which("speaker-test"):
        return False, "speaker-test missing (alsa-utils)"

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
            time.sleep(0.15)
    except Exception:
        pass
    _unmute(card)
    cmd = [
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
    ]
    ok, msg = _run(cmd, timeout=max(5.0, seconds + 3.0))
    _pw("start")
    if ok:
        return True, f"plughw:{card},0 OK"
    return False, f"card {card}: {msg}"


def play_cmd_for_debug() -> List[str]:
    """Deprecated for UI — prefer play_test_tone_detail in a thread."""
    fix = _fix_bin()
    if fix:
        return ["sudo", "-n", fix, "--beep"]
    card = _usb_card() or "1"
    if which("speaker-test"):
        return [
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
        ]
    return []
