"""Digivice playback helpers — hit the USB C-Media stick the same way the fix beep does."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from shutil import which
from typing import List, Optional, Sequence


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


def wake_usb_audio() -> None:
    """Keep C-Media out of autosuspend (needs passwordless sudo once installed)."""
    for cmd in (
        ["sudo", "-n", "digivice-audio-fix", "--persist-only"],
        ["sudo", "-n", "/usr/local/bin/digivice-audio-fix", "--persist-only"],
    ):
        try:
            subprocess.run(
                cmd,
                capture_output=True,
                timeout=8,
                check=False,
            )
            return
        except Exception:
            continue


def _run(cmd: Sequence[str], timeout: float = 6.0) -> bool:
    try:
        r = subprocess.run(
            list(cmd),
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return r.returncode == 0
    except Exception:
        return False


def play_test_tone(*, seconds: float = 2.0) -> bool:
    """Play a sine the way digivice-audio-fix does (ALSA → USB, not vague default).

    Returns True if a player was started successfully.
    """
    wake_usb_audio()
    card = _usb_card() or "1"
    # Suspend PipeWire/Pulse briefly so ALSA can own the stick (same as fix beep)
    wrap: List[str] = []
    if which("pasuspender"):
        wrap = ["pasuspender", "--"]

    if which("speaker-test"):
        cmd = wrap + [
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
        if _run(cmd, timeout=max(4.0, seconds + 2.5)):
            return True
        # Fallback without pasuspender
        if wrap and _run(cmd[2:], timeout=max(4.0, seconds + 2.5)):
            return True

    wav = Path("/usr/share/sounds/alsa/Front_Center.wav")
    if which("aplay") and wav.is_file():
        cmd = wrap + ["aplay", "-D", f"plughw:{card},0", str(wav)]
        if _run(cmd, timeout=8.0):
            return True
        if wrap and _run(cmd[2:], timeout=8.0):
            return True

    # Last resort: PipeWire, but force default sink first
    oga = Path("/usr/share/sounds/freedesktop/stereo/bell.oga")
    if not oga.is_file():
        oga = Path("/usr/share/sounds/freedesktop/stereo/message.oga")
    if which("paplay") and oga.is_file():
        try:
            subprocess.run(
                ["wpctl", "status"],
                capture_output=True,
                timeout=3,
                check=False,
            )
        except Exception:
            pass
        env = os.environ.copy()
        return _run(["paplay", str(oga)], timeout=8.0)

    return False


def play_cmd_for_debug() -> List[str]:
    """Argv for QProcess-based Debug page (speaker beep)."""
    wake_usb_audio()
    card = _usb_card() or "1"
    if which("pasuspender") and which("speaker-test"):
        return [
            "pasuspender",
            "--",
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
