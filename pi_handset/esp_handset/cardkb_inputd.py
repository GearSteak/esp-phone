#!/usr/bin/env python3
"""M5Stack CardKB on Pi I2C → uinput (Digivice nav + typing).

Wiring (Pi 40-pin):
  CardKB 5V  → Pin 2  (5V)
  CardKB GND → Pin 6  (GND)
  CardKB SDA → Pin 3  (GPIO 2 / SDA1)
  CardKB SCL → Pin 5  (GPIO 3 / SCL1)

Nav: arrows 0xB4–0xB7, Enter=Confirm, Esc=Back, Fn+Esc or '~' quirk → Home optional.
Poll /dev/i2c-1 @ 0x5F (same protocol as Heltec CardKB).
"""

from __future__ import annotations

import argparse
import sys
import time

ADDR = 0x5F

# CardKB non-ASCII navigation codes (m5 unit table)
ARROW = {
    0xB4: "LEFT",
    0xB5: "UP",
    0xB6: "DOWN",
    0xB7: "RIGHT",
}

PUNCT = {
    ";": "KEY_SEMICOLON",
    ":": "KEY_SEMICOLON",
    ",": "KEY_COMMA",
    "<": "KEY_COMMA",
    ".": "KEY_DOT",
    ">": "KEY_DOT",
    "/": "KEY_SLASH",
    "?": "KEY_SLASH",
    "'": "KEY_APOSTROPHE",
    '"': "KEY_APOSTROPHE",
    "-": "KEY_MINUS",
    "_": "KEY_MINUS",
    "=": "KEY_EQUAL",
    "+": "KEY_EQUAL",
    "!": "KEY_1",
    "@": "KEY_2",
    "#": "KEY_3",
    "$": "KEY_4",
    "%": "KEY_5",
    "^": "KEY_6",
    "&": "KEY_7",
    "*": "KEY_8",
    "(": "KEY_9",
    ")": "KEY_0",
}
NEEDS_SHIFT = set(':!@#$%^&*()<>?"_+')


def main() -> int:
    ap = argparse.ArgumentParser(description="CardKB → uinput for Digivice")
    ap.add_argument("bus", nargs="?", type=int, default=1, help="I2C bus (default 1)")
    ap.add_argument("--hz", type=float, default=50.0, help="Poll rate Hz")
    args = ap.parse_args()

    try:
        import smbus2 as smbus  # type: ignore
    except ImportError:
        try:
            import smbus  # type: ignore
        except ImportError:
            print("Need python3-smbus or smbus2", file=sys.stderr)
            return 1
    try:
        import uinput
    except ImportError:
        print("python3-uinput required", file=sys.stderr)
        return 1

    events = [uinput.KEY_A + i for i in range(26)]
    events += [uinput.KEY_0 + i for i in range(10)]
    events += [
        uinput.KEY_ENTER,
        uinput.KEY_BACKSPACE,
        uinput.KEY_SPACE,
        uinput.KEY_ESC,
        uinput.KEY_HOME,
        uinput.KEY_TAB,
        uinput.KEY_LEFTSHIFT,
        uinput.KEY_UP,
        uinput.KEY_DOWN,
        uinput.KEY_LEFT,
        uinput.KEY_RIGHT,
        uinput.KEY_DOT,
        uinput.KEY_COMMA,
        uinput.KEY_SLASH,
        uinput.KEY_SEMICOLON,
        uinput.KEY_APOSTROPHE,
        uinput.KEY_MINUS,
        uinput.KEY_EQUAL,
    ]
    device = uinput.Device(events, name="Digivice-CardKB")

    try:
        bus = smbus.SMBus(args.bus)
    except OSError as e:
        print(f"open i2c-{args.bus}: {e} (enable I2C, check wiring)", file=sys.stderr)
        return 1

    print(
        f"cardkb-inputd ready bus={args.bus} addr=0x{ADDR:02X} "
        f"(arrows=nav Enter=confirm Esc=back)",
        flush=True,
    )

    def tap(code: int) -> None:
        device.emit(code, 1)
        time.sleep(0.01)
        device.emit(code, 0)

    def emit_char(ch: str) -> None:
        need_shift = ch.isupper() or ch in NEEDS_SHIFT
        base = ch.lower() if ch.isalpha() else ch
        if ch in PUNCT:
            code = getattr(uinput, PUNCT[ch])
        elif "a" <= base <= "z":
            code = getattr(uinput, f"KEY_{base.upper()}")
        elif "0" <= base <= "9":
            code = getattr(uinput, f"KEY_{base}")
        else:
            return
        if need_shift:
            device.emit(uinput.KEY_LEFTSHIFT, 1)
        device.emit(code, 1)
        time.sleep(0.008)
        device.emit(code, 0)
        if need_shift:
            device.emit(uinput.KEY_LEFTSHIFT, 0)

    period = 1.0 / max(args.hz, 5.0)
    seen = False
    while True:
        try:
            raw = bus.read_byte(ADDR)
        except OSError:
            if seen:
                print("CardKB I2C lost — will retry", flush=True)
                seen = False
            time.sleep(0.5)
            continue
        if not seen:
            print("CardKB online", flush=True)
            seen = True
        if raw == 0:
            time.sleep(period)
            continue
        # Navigation / control
        if raw in ARROW:
            name = ARROW[raw]
            code = {
                "UP": uinput.KEY_UP,
                "DOWN": uinput.KEY_DOWN,
                "LEFT": uinput.KEY_LEFT,
                "RIGHT": uinput.KEY_RIGHT,
            }[name]
            tap(code)
        elif raw in (0x0D, 0x0A):
            tap(uinput.KEY_ENTER)
        elif raw == 0x1B:
            tap(uinput.KEY_ESC)
        elif raw == 0x08 or raw == 0x7F:
            tap(uinput.KEY_BACKSPACE)
        elif raw == 0x09:
            tap(uinput.KEY_TAB)
        elif raw == 0x20:
            tap(uinput.KEY_SPACE)
        elif 32 <= raw < 127:
            emit_char(chr(raw))
        time.sleep(period * 0.25)  # slight gap after key to avoid double-fire

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
