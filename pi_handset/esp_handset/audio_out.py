"""Digivice beep — PipeWire first (simple), then ALSA. Long loud tone."""

from __future__ import annotations

import math
import os
import re
import struct
import subprocess
import wave
from datetime import datetime
from pathlib import Path
from shutil import which
from typing import List, Optional, Tuple

AUDIO_BUILD = "v13-card0"
_LOG = Path.home() / ".esp-handset" / "last-beep.txt"
_WAV = Path.home() / ".esp-handset" / "beep-loud.wav"


def _fix_bin() -> Optional[str]:
    for p in (
        "/usr/local/bin/digivice-audio-fix",
        "/opt/esp-handset/session/digivice-audio-fix.sh",
    ):
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return which("digivice-audio-fix")


def _log(msg: str) -> None:
    try:
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except OSError:
        pass


def _reset_log() -> None:
    try:
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        _LOG.write_text(
            f"build={AUDIO_BUILD}\n"
            f"when={datetime.now().isoformat(timespec='seconds')}\n"
            f"user={os.environ.get('USER', '?')}\n---\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _run(cmd: List[str], timeout: float = 12.0) -> Tuple[int, str]:
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        return r.returncode, out
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except Exception as e:
        return 1, str(e)


def _aplay_cards() -> list:
    """Live ALSA playback cards from `aplay -l` (never trust a stale file)."""
    _code, out = _run(["aplay", "-l"], timeout=5)
    cards = []
    for line in out.splitlines():
        m = re.match(r"^card (\d+):", line)
        if not m:
            continue
        low = line.lower()
        if any(x in low for x in ("hdmi", "vc4", "bcm2835")):
            continue
        cards.append((m.group(1), low, line))
    return cards


def _usb_card() -> Optional[str]:
    cards = _aplay_cards()
    if not cards:
        return None
    live = {c[0] for c in cards}
    # Saved index is only used if that card still exists (old default was 1; stick is often 0)
    p = Path("/etc/esp-handset/alsa-card")
    try:
        if p.is_file():
            saved = p.read_text().strip()
            if saved in live:
                return saved
    except OSError:
        pass
    for idx, low, _line in cards:
        if any(x in low for x in ("usb", "device", "c-media", "audio", "headset", "pn[p]")):
            return idx
    return cards[0][0]


def _make_loud_wav(seconds: float = 5.0) -> Path:
    """Stereo full-scale 880Hz — hard to miss in headphones."""
    _WAV.parent.mkdir(parents=True, exist_ok=True)
    rate, freq = 48000, 880.0
    n = int(rate * seconds)
    with wave.open(str(_WAV), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        for i in range(n):
            # slight left/right so either channel works
            v = int(31000 * math.sin(2 * math.pi * freq * i / rate))
            w.writeframes(struct.pack("<hh", v, v))
    return _WAV


def _unmute_card(card: str) -> None:
    for ctl in ("Speaker", "PCM", "Master", "Headphone", "Playback"):
        _run(
            ["amixer", "-c", card, "-q", "sset", ctl, "100%", "unmute"],
            timeout=3,
        )
    # raw: set every simple control that looks like playback
    code, out = _run(["amixer", "-c", card, "scontrols"], timeout=3)
    for line in out.splitlines():
        m = re.search(r"Simple mixer control '([^']+)'", line)
        if not m:
            continue
        name = m.group(1)
        if name.lower().startswith(("mic", "capture", "auto")):
            continue
        _run(
            ["amixer", "-c", card, "-q", "sset", name, "100%", "unmute"],
            timeout=2,
        )


def _wpctl_usb_default() -> None:
    """Point PipeWire at USB sink and max volume — no sudo."""
    code, out = _run(["wpctl", "status"], timeout=5)
    _log("wpctl status (sinks excerpt):")
    sink_id = None
    in_sinks = False
    for line in out.splitlines():
        if "Sinks:" in line:
            in_sinks = True
            continue
        if in_sinks and ("Sources:" in line or "Filters:" in line):
            break
        if not in_sinks:
            continue
        _log(f"  {line}")
        low = line.lower()
        if any(x in low for x in ("hdmi", "vc4")):
            continue
        if any(x in low for x in ("usb", "device", "analog", "c-media", "audio")):
            m = re.search(r"\b(\d+)\b", line)
            if m:
                sink_id = m.group(1)
                break
    if sink_id:
        _run(["wpctl", "set-default", sink_id], timeout=3)
        _log(f"wpctl set-default {sink_id}")
    _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"], timeout=3)
    _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "1.0"], timeout=3)
    # some builds allow >100%
    _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "1.5"], timeout=3)


def wake_usb_audio() -> None:
    fix = _fix_bin()
    if fix:
        _run(["sudo", "-n", fix, "--recover"], timeout=15)
    card = _usb_card()
    if card:
        _unmute_card(card)
    _wpctl_usb_default()


def play_test_tone(*, seconds: float = 5.0) -> bool:
    ok, _ = play_test_tone_detail(seconds=seconds)
    return ok


def play_test_tone_detail(*, seconds: float = 5.0) -> Tuple[bool, str]:
    """
    Digivice path: do NOT stop PipeWire / sudo dance.
    Max volume → 5s loud stereo wav via pw-play/paplay/aplay.
    LED blink + silence was exclusive-ALSA complexity; this is normal playback.
    """
    _reset_log()
    secs = max(4.0, float(seconds))
    wav = _make_loud_wav(secs)
    _log(f"wav={wav} secs={secs}")

    card = _usb_card()
    _log(f"card={card}")
    if card:
        _unmute_card(card)
        try:
            Path("/etc/esp-handset").mkdir(parents=True, exist_ok=True)
            # best-effort; may need sudo — ignore fail
            Path("/etc/esp-handset/alsa-card").write_text(card)
        except OSError:
            pass

    _wpctl_usb_default()

    # Prefer PipeWire tools (Digivice user session — same as music apps)
    players: List[List[str]] = []
    if which("pw-play"):
        players.append(["pw-play", str(wav)])
    if which("paplay"):
        players.append(["paplay", str(wav)])
    if which("aplay") and card:
        players.append(["aplay", "-D", f"plughw:{card},0", str(wav)])
    if which("aplay"):
        players.append(["aplay", str(wav)])
    if which("speaker-test"):
        players.append(
            [
                "speaker-test",
                "-c",
                "2",
                "-r",
                "48000",
                "-t",
                "sine",
                "-f",
                "880",
                "-l",
                "2",
            ]
        )

    last_err = "no player"
    for cmd in players:
        _log(f"try: {' '.join(cmd)}")
        code, out = _run(cmd, timeout=secs + 4.0)
        _log(f"exit={code} {out[-200:]}")
        if code in (0, 124):
            return True, f"{AUDIO_BUILD} OK"
        last_err = out[-40:] if out else f"exit {code}"

    # Last resort: old sudo exclusive path (only if PW failed)
    fix = _fix_bin()
    if fix:
        _log("fallback sudo --ui-beep")
        env = os.environ.copy()
        me = os.environ.get("USER") or os.environ.get("LOGNAME")
        if me:
            env["SUDO_USER"] = me
        try:
            r = subprocess.run(
                ["sudo", "-n", fix, "--ui-beep"],
                capture_output=True,
                text=True,
                timeout=25,
                check=False,
                env=env,
            )
            _log(f"ui-beep exit={r.returncode}")
            if r.returncode in (0, 124):
                return True, f"{AUDIO_BUILD} alsa OK"
        except Exception as e:
            _log(str(e))

    return False, last_err[:40]


def play_cmd_for_debug() -> List[str]:
    return []


def last_beep_tail(n: int = 10) -> str:
    try:
        return "\n".join(_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return "(no log)"
