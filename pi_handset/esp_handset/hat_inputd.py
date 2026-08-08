#!/usr/bin/env python3
"""Waveshare 1.3\" LCD HAT → Digivice keys or desktop mouse.

Physical KEY1 / KEY2 / KEY3:
  Digivice (phone):  Confirm / Back / Home
  Desktop:           Left click / Right click / Middle click

Joystick: Digivice = D-pad + press=Confirm; Desktop = mouse move + press=Left click.

Mode file (written by handset-session): /etc/esp-handset/ui_mode
  phone | desktop
"""

from __future__ import annotations

import os
import sys
import time

PINS = {
    6: "UP",
    19: "DOWN",
    5: "LEFT",
    26: "RIGHT",
    13: "PRESS",
    21: "KEY1",  # Confirm / LMB
    20: "KEY2",  # Back / RMB
    16: "KEY3",  # Home / MMB
}

MODE_FILE = "/etc/esp-handset/ui_mode"
MOUSE_STEP = 8


def read_mode() -> str:
    try:
        with open(MODE_FILE, encoding="utf-8") as f:
            m = f.read().strip().lower()
        if m in ("phone", "desktop"):
            return m
    except OSError:
        pass
    return "phone"


def main() -> int:
    try:
        import uinput
    except ImportError:
        print("python3-uinput required", file=sys.stderr)
        return 1

    try:
        import RPi.GPIO as GPIO
    except ImportError:
        print("RPi.GPIO required (run on Raspberry Pi)", file=sys.stderr)
        return 1

    events = [
        uinput.KEY_UP,
        uinput.KEY_DOWN,
        uinput.KEY_LEFT,
        uinput.KEY_RIGHT,
        uinput.KEY_ENTER,
        uinput.KEY_ESC,
        uinput.KEY_HOME,
        uinput.BTN_LEFT,
        uinput.BTN_RIGHT,
        uinput.BTN_MIDDLE,
        uinput.REL_X,
        uinput.REL_Y,
    ]
    device = uinput.Device(events, name="Digivice-HAT")

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in PINS:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    prev = {name: 1 for name in PINS.values()}
    mode = read_mode()
    print(f"hat-inputd ready mode={mode} (KEY1=confirm/LMB KEY2=back/RMB KEY3=home/MMB)", flush=True)
    last_mode_check = time.monotonic()

    try:
        while True:
            now = time.monotonic()
            if now - last_mode_check > 0.5:
                mode = read_mode()
                last_mode_check = now

            held = {}
            for pin, name in PINS.items():
                level = GPIO.input(pin)
                pressed = level == 0
                held[name] = pressed
                was = prev[name]
                if level == was:
                    continue
                prev[name] = level
                down = pressed  # edge into press

                if mode == "desktop":
                    if name == "KEY1" or name == "PRESS":
                        device.emit(uinput.BTN_LEFT, 1 if down else 0)
                    elif name == "KEY2":
                        device.emit(uinput.BTN_RIGHT, 1 if down else 0)
                    elif name == "KEY3":
                        device.emit(uinput.BTN_MIDDLE, 1 if down else 0)
                    # stick directions handled as mouse motion while held
                else:
                    phone_map = {
                        "UP": uinput.KEY_UP,
                        "DOWN": uinput.KEY_DOWN,
                        "LEFT": uinput.KEY_LEFT,
                        "RIGHT": uinput.KEY_RIGHT,
                        "PRESS": uinput.KEY_ENTER,
                        "KEY1": uinput.KEY_ENTER,
                        "KEY2": uinput.KEY_ESC,
                        "KEY3": uinput.KEY_HOME,
                    }
                    device.emit(phone_map[name], 1 if down else 0)

            if mode == "desktop":
                dx = dy = 0
                if held.get("LEFT"):
                    dx -= MOUSE_STEP
                if held.get("RIGHT"):
                    dx += MOUSE_STEP
                if held.get("UP"):
                    dy -= MOUSE_STEP
                if held.get("DOWN"):
                    dy += MOUSE_STEP
                if dx or dy:
                    device.emit(uinput.REL_X, dx, syn=False)
                    device.emit(uinput.REL_Y, dy)

            time.sleep(0.012)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
