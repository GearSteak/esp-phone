#!/usr/bin/env python3
"""Digivice discrete buttons → uinput.

Seven hard keys (each: GPIO → momentary button → GND, input pull-up):

  UP / DOWN / LEFT / RIGHT / CONFIRM / BACK / HOME

BCM defaults (free of 2\" LCD SPI: 8,10,11,18,25,27):

  UP=5  DOWN=6  LEFT=12  RIGHT=13  CONFIRM=16  BACK=19  HOME=20

Override with env DIGI_BTN_UP=… etc. (BCM numbers).
"""

from __future__ import annotations

import os
import sys
import time

# name → default BCM
DEFAULTS = {
    "UP": 5,
    "DOWN": 6,
    "LEFT": 12,
    "RIGHT": 13,
    "CONFIRM": 16,
    "BACK": 19,
    "HOME": 20,
}

DEBOUNCE_S = 0.02
SCAN_S = 0.01


def pin_map() -> dict:
    out = {}
    for name, default in DEFAULTS.items():
        env = os.environ.get(f"DIGI_BTN_{name}", "").strip()
        out[name] = int(env) if env else default
    return out


def main() -> int:
    try:
        import uinput
    except ImportError:
        print("python3-uinput required", file=sys.stderr)
        return 1
    try:
        import RPi.GPIO as GPIO
    except ImportError:
        print("RPi.GPIO required (run on Pi)", file=sys.stderr)
        return 1

    pins = pin_map()
    phone_map = {
        "UP": uinput.KEY_UP,
        "DOWN": uinput.KEY_DOWN,
        "LEFT": uinput.KEY_LEFT,
        "RIGHT": uinput.KEY_RIGHT,
        "CONFIRM": uinput.KEY_ENTER,
        "BACK": uinput.KEY_ESC,
        "HOME": uinput.KEY_HOME,
    }
    events = list(phone_map.values())
    device = uinput.Device(events, name="Digivice-Buttons")

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for name, pin in pins.items():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # name → last stable level (1=released, 0=pressed)
    prev = {n: 1 for n in pins}
    raw = {n: 1 for n in pins}
    stable_since = {n: time.monotonic() for n in pins}

    print(
        "digi-buttons ready "
        + " ".join(f"{n}=GPIO{p}" for n, p in pins.items())
        + "  (CONFIRM=Enter BACK=Esc HOME=Home)",
        flush=True,
    )

    try:
        while True:
            now = time.monotonic()
            for name, pin in pins.items():
                level = GPIO.input(pin)
                if level != raw[name]:
                    raw[name] = level
                    stable_since[name] = now
                    continue
                if now - stable_since[name] < DEBOUNCE_S:
                    continue
                if level == prev[name]:
                    continue
                prev[name] = level
                down = level == 0
                device.emit(phone_map[name], 1 if down else 0)
            time.sleep(SCAN_S)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
