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

AUDIO_BUILD = "v18-click"
_LOG = Path.home() / ".esp-handset" / "last-beep.txt"
_WAV = Path.home() / ".esp-handset" / "beep-loud.wav"
_CLICK = Path.home() / ".esp-handset" / "nav-click.wav"
_PRIME = Path.home() / ".esp-handset" / "nav-prime.wav"
_click_dev: Optional[str] = None
_click_proc: Optional[subprocess.Popen] = None
_click_last = 0.0


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


def _usb_plughw() -> Optional[str]:
    global _click_dev
    if _click_dev:
        return _click_dev
    _code, out = _run(["aplay", "-l"], timeout=8)
    for line in out.splitlines():
        m = re.match(r"^card (\d+):\s*(\S+)", line)
        if not m:
            continue
        low = line.lower()
        if any(x in low for x in ("hdmi", "vc4", "bcm2835")):
            continue
        _click_dev = f"plughw:{m.group(1)},0"
        return _click_dev
    return None


def _write_wav(path: Path, seconds: float, amp: int, freq: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 48000
    n = max(32, int(rate * seconds))
    with wave.open(str(path), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        for i in range(n):
            env = 1.0 - (i / n)
            env *= env
            v = int(amp * env * math.sin(2 * math.pi * freq * i / rate)) if amp else 0
            w.writeframes(struct.pack("<hh", v, v))
    return path


def _ensure_click_wav() -> Path:
    if _CLICK.is_file() and _CLICK.stat().st_size > 200:
        return _CLICK
    return _write_wav(_CLICK, 0.024, 3800, 1900.0)


def _ensure_prime_wav() -> Path:
    if _PRIME.is_file() and _PRIME.stat().st_size > 200:
        return _PRIME
    return _write_wav(_PRIME, 0.03, 0, 0.0)


def _sounds_on() -> bool:
    try:
        from esp_handset import store

        prefs = store.load("sounds.json", {"profile": "Normal", "enabled": True})
        if prefs.get("enabled") is False:
            return False
        return str(prefs.get("profile", "Normal")) != "Silent"
    except Exception:
        return True


def play_nav_click() -> None:
    """Quiet menu tick. Never blocks the UI; skips if a click is already playing."""
    global _click_proc, _click_last
    if not _sounds_on():
        return
    now = time.monotonic()
    if now - _click_last < 0.07:
        return
    if _click_proc is not None and _click_proc.poll() is None:
        return
    if not which("aplay"):
        return
    dev = _usb_plughw()
    if not dev:
        return
    wav = _ensure_click_wav()
    try:
        _click_proc = subprocess.Popen(
            ["aplay", "-D", dev, "-q", str(wav)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        _click_last = now
    except Exception:
        _click_proc = None


def prime_nav_click() -> None:
    """Open the USB PCM once so the first scroll click is not eaten by -524."""
    global _click_dev
    _click_dev = None
    dev = _usb_plughw()
    if not dev or not which("aplay"):
        return
    card = dev.split(":")[-1].split(",")[0]
    _unmute_card(card)
    silent = _ensure_prime_wav()
    _run(["aplay", "-D", dev, "-q", str(silent)], timeout=3)
    time.sleep(0.35)
    _run(["aplay", "-D", dev, "-q", str(silent)], timeout=3)


def open_usb_play_stream(
    *, rate: int = 48000, channels: int = 2
) -> Optional[subprocess.Popen]:
    """Persistent aplay stdin for Game Boy PCM (S16 stereo). Mini CM108 first open may -524."""
    if not which("aplay"):
        return None
    dev = _usb_plughw()
    if not dev:
        return None
    card = dev.split(":")[-1].split(",")[0]
    _unmute_card(card)
    cmd = [
        "aplay",
        "-D",
        dev,
        "-q",
        "-t",
        "raw",
        "-f",
        "S16_LE",
        "-c",
        str(channels),
        "-r",
        str(rate),
    ]
    for attempt in (1, 2):
        try:
            p = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                bufsize=0,
            )
            time.sleep(0.15)
            if p.poll() is not None:
                time.sleep(0.5)
                continue
            return p
        except Exception:
            time.sleep(0.5)
    return None


def close_usb_play_stream(proc: Optional[subprocess.Popen]) -> None:
    if proc is None:
        return
    try:
        if proc.stdin:
            proc.stdin.close()
    except Exception:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=1.5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
