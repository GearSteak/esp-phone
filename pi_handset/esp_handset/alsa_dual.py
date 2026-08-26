"""Detect Pi headphone + USB dongle and prefer ALSA default (tee to both)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple

_ROUTE = Path.home() / ".esp-handset" / "audio_route"


def _aplay_lines() -> list[str]:
    try:
        r = subprocess.run(
            ["aplay", "-l"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
        return (r.stdout or "").splitlines()
    except Exception:
        return []


def card_sets() -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Return (hp_short, hp_label, usb_short, usb_label) from aplay -l."""
    hp_short = hp_label = usb_short = usb_label = None
    for line in _aplay_lines():
        m = re.match(r"^card \d+:\s*(\S+)\s*\[([^\]]+)\]", line)
        if not m:
            continue
        low = line.lower()
        if any(x in low for x in ("hdmi", "vc4")):
            continue
        short, label = m.group(1).strip(), m.group(2).strip()
        if "bcm2835" in low or "headphone" in low:
            hp_short = hp_short or short
            hp_label = hp_label or label
        elif any(x in low for x in ("usb", "device", "cm10", "headset", "c-media", "audio")):
            usb_short = usb_short or short
            usb_label = usb_label or label
    return hp_short, hp_label, usb_short, usb_label


def route_mode() -> str:
    """dual | usb | jack | unknown"""
    try:
        raw = _ROUTE.read_text(encoding="utf-8").strip().lower()
        if raw in ("dual", "usb", "jack"):
            return raw
    except OSError:
        pass
    hp_short, _, usb_short, _ = card_sets()
    if hp_short and usb_short:
        return "dual"
    if usb_short:
        return "usb"
    if hp_short:
        return "jack"
    return "unknown"


def dual_playback_ready() -> bool:
    return route_mode() == "dual"


def voip_playback_label() -> Optional[str]:
    """Linphone playback when tee routes to jack + USB."""
    if dual_playback_ready():
        return "ALSA: default"
    return None
