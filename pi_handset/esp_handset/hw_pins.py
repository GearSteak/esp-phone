"""Digivice spare GPIO — piezo + tilt steps (Heltec removed).

Defaults avoid LCD SPI, CardKB I2C, and hard buttons:

| Job     | BCM | Board pin | Notes                          |
|---------|-----|-----------|--------------------------------|
| Steps   | 17  | 11        | SW-520D / tilt switch → GND    |
| Buzzer  | 22  | 15        | Passive piezo + → GPIO, − → GND |

Override: DIGI_STEPS_BCM, DIGI_BUZZER_BCM (or `off` to disable).
"""
from __future__ import annotations

import os
from typing import Optional


def _env_bcm(name: str, default: int) -> Optional[int]:
    raw = (os.environ.get(name) or "").strip().lower()
    if raw in ("off", "none", "disable", "0", "-1"):
        return None
    if not raw:
        return int(default)
    try:
        return int(raw)
    except ValueError:
        return int(default)


# Pin 11 — free on Digivice passthrough map
STEPS_BCM: Optional[int] = _env_bcm("DIGI_STEPS_BCM", 17)
# Pin 15 — free; software PWM for passive piezo
BUZZER_BCM: Optional[int] = _env_bcm("DIGI_BUZZER_BCM", 22)
