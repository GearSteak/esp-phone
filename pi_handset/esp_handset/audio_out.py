"""Mini CM108 USB beep — ALSA wake+retry. PipeWire often has no sink for this chip."""

from __future__ import annotations

import math
import os
import re
import struct
import subprocess
import time
import wave
from datetime import datetime
from pathlib import Path
from shutil import which
from typing import List, Optional, Tuple

AUDIO_BUILD = "v17-quiet"
_LOG = Path.home() / ".esp-handset" / "last-beep.txt"
_WAV = Path.home() / ".esp-handset" / "beep-loud.wav"


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
    _code, out = _run(["aplay", "-l"], timeout=8)
    _log(out or "(aplay -l empty)")
    cards = []
    for line in out.splitlines():
        m = re.match(r"^card (\d+):\s*(\S+)", line)
        if not m:
            continue
        low = line.lower()
        if any(x in low for x in ("hdmi", "vc4", "bcm2835")):
            continue
        cards.append((m.group(1), m.group(2), line))
    return cards


def _usb_card() -> Optional[str]:
    cards = _aplay_cards()
    if not cards:
        return None
    for idx, _name, line in cards:
        low = line.lower()
        if any(x in low for x in ("usb", "device", "c-media", "pn p", "pnp")):
            return idx
    return cards[0][0]


def _card_alsa_name(card: str) -> str:
    for idx, name, _line in _aplay_cards():
        if idx == card:
            return name
    return "Device"


def _make_loud_wav(seconds: float = 4.0) -> Path:
    _WAV.parent.mkdir(parents=True, exist_ok=True)
    rate, freq = 48000, 880.0
    n = int(rate * seconds)
    with wave.open(str(_WAV), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        for i in range(n):
            v = int(7000 * math.sin(2 * math.pi * freq * i / rate))
            w.writeframes(struct.pack("<hh", v, v))
    return _WAV


def _unmute_card(card: str) -> None:
    for ctl in ("Speaker", "PCM", "Master", "Headphone"):
        _run(["amixer", "-c", card, "-q", "sset", ctl, "35%", "unmute"], timeout=3)


def _wake_bin() -> Optional[str]:
    p = "/usr/local/bin/digivice-cm108-wake"
    if os.path.isfile(p):
        return p
    return which("digivice-cm108-wake")


def wake_usb_audio() -> None:
    """Mini CM108: listing the card + pause is the real wake (first open often -524)."""
    _aplay_cards()
    time.sleep(2.0)
    card = _usb_card()
    if card:
        _unmute_card(card)


def software_wake() -> str:
    """Sealed-case wake: nosuspend, wait for ALSA, prime first PCM open. No unplug."""
    wake = _wake_bin()
    if wake:
        _log(f"sudo {wake}")
        code, out = _run(["sudo", "-n", wake], timeout=25.0)
        _log(f"wake exit={code} {(out or '')[-200:]}")
        time.sleep(0.5)
        return (out or f"wake {code}")[-48:]
    _log("wake helper missing — aplay -l only")
    wake_usb_audio()
    return "soft wake"


def _is_524(out: str) -> bool:
    return "-524" in out or "unknown error 524" in out.lower() or "enotsupp" in out.lower()


def play_test_tone(*, seconds: float = 4.0) -> bool:
    ok, _ = play_test_tone_detail(seconds=seconds)
    return ok


def _alsa_play(wav: Path, secs: float) -> Tuple[bool, str]:
    cards = _aplay_cards()
    if not cards:
        return False, "no ALSA card"
    card = cards[0][0]
    alsa_name = cards[0][1]
    _log(f"card={card} name={alsa_name}")
    _unmute_card(card)
    time.sleep(2.0)

    devices = [
        f"plughw:{card},0",
        f"sysdefault:CARD={alsa_name}",
        f"hw:{card},0",
    ]
    last = "no play"
    if not which("aplay"):
        return False, "aplay missing"

    for dev in devices:
        cmd = ["aplay", "-D", dev, "-q", str(wav)]
        for attempt in (1, 2):
            _log(f"try {attempt}: {' '.join(cmd)}")
            code, out = _run(cmd, timeout=secs + 5.0)
            _log(f"exit={code} {out[-160:]}")
            if code in (0, 124):
                return True, f"{AUDIO_BUILD} {dev}"
            last = out[-40:] if out else f"exit {code}"
            if _is_524(out) or "busy" in out.lower() or "device or resource" in out.lower():
                time.sleep(2.0)
                continue
            break

    if which("speaker-test"):
        for ch in ("2", "1"):
            cmd = [
                "speaker-test",
                "-D",
                f"plughw:{card},0",
                "-c",
                ch,
                "-r",
                "48000",
                "-t",
                "sine",
                "-f",
                "880",
                "-l",
                "1",
            ]
            _log(f"try: {' '.join(cmd)}")
            code, out = _run(cmd, timeout=8.0)
            _log(f"exit={code} {out[-160:]}")
            if code in (0, 124):
                return True, f"{AUDIO_BUILD} sine {ch}ch"
            last = out[-40:] if out else f"exit {code}"
            if _is_524(out):
                time.sleep(2.0)
                code, out = _run(cmd, timeout=8.0)
                if code in (0, 124):
                    return True, f"{AUDIO_BUILD} sine retry"

    return False, last[:40]


def play_test_tone_detail(*, seconds: float = 4.0) -> Tuple[bool, str]:
    """Exclusive ALSA for mini CM108. Skip PipeWire (empty sinks = play-to-nowhere)."""
    _reset_log()
    secs = max(3.0, float(seconds))
    wav = _make_loud_wav(secs)
    _log(f"wav={wav}")

    ok, msg = _alsa_play(wav, secs)
    if ok:
        return True, msg
    _log("software wake (sealed case)")
    software_wake()
    ok, msg = _alsa_play(wav, secs)
    if ok:
        return True, f"{AUDIO_BUILD} after wake"
    return False, msg[:40]


def play_cmd_for_debug() -> List[str]:
    return []


def last_beep_tail(n: int = 12) -> str:
    try:
        return "\n".join(
            _LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
        )
    except OSError:
        return "(no log)"
