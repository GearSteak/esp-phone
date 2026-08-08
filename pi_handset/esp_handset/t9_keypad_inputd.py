#!/usr/bin/env python3
"""4×4 matrix keypad → Digivice T9 + nav (uinput).

Typical membrane / tactile 4×4 (e.g. 43×39 mm): silk 1–9 * 0 # A B C D

  ┌──────┬──────┬──────┬──────┐
  │  1   │  2   │  3   │  A   │
  │ .,?! │ abc  │ def  │  ▲   │
  ├──────┼──────┼──────┼──────┤
  │  4   │  5   │  6   │  B   │
  │ ghi  │ jkl  │ mno  │  ▼   │
  ├──────┼──────┼──────┼──────┤
  │  7   │  8   │  9   │  C   │
  │ pqrs │ tuv  │ wxyz │  OK  │
  ├──────┼──────┼──────┼──────┤
  │  *   │  0   │  #   │  D   │
  │  ◀   │ sp 0 │  ▶   │ Back │
  └──────┴──────┴──────┴──────┘

Mode (long-press *): abc → ABC → 123 → abc
  # short = Right · long # = Backspace
  * short = Left  · long * = cycle mode

GPIO (BCM) avoid LCD SPI 8/10/11/18/25/27:
  Rows (drive LOW):  5, 6, 13, 19
  Cols (pull-up):    12, 16, 20, 21
"""

from __future__ import annotations

import os
import sys
import time
from typing import Dict, List, Optional, Tuple

# Row pins top→bottom, col pins left→right (BCM)
ROWS = [5, 6, 13, 19]
COLS = [12, 16, 20, 21]

# (r,c) → logical name matching silk
KEYS: List[List[str]] = [
    ["1", "2", "3", "A"],
    ["4", "5", "6", "B"],
    ["7", "8", "9", "C"],
    ["*", "0", "#", "D"],
]

# Multi-tap (classic phone). Index cycles while same key within TAP_MS.
ALPHABETS = {
    "1": ".,?!'\"-1",
    "2": "abc2",
    "3": "def3",
    "4": "ghi4",
    "5": "jkl5",
    "6": "mno6",
    "7": "pqrs7",
    "8": "tuv8",
    "9": "wxyz9",
    "0": " 0",
}
ALPHABETS_UP = {k: v.upper() if k != "0" else v for k, v in ALPHABETS.items()}
# 0 still space + "0"; uppercase letters on 2–9
for k in list(ALPHABETS_UP):
    if k in "23456789":
        ALPHABETS_UP[k] = ALPHABETS[k].upper()

TAP_MS = 0.85
LONG_MS = 0.55
SCAN_S = 0.012
DEBOUNCE_S = 0.025


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

    # Override pin lists from env if board wiring differs
    rows = [int(x) for x in os.environ.get("T9_ROWS", "").split(",") if x.strip()] or ROWS
    cols = [int(x) for x in os.environ.get("T9_COLS", "").split(",") if x.strip()] or COLS
    if len(rows) != 4 or len(cols) != 4:
        print("T9_ROWS / T9_COLS need 4 GPIO each", file=sys.stderr)
        return 1

    events = [uinput.KEY_A + i for i in range(26)]
    events += [uinput.KEY_0 + i for i in range(10)]
    events += [
        uinput.KEY_UP,
        uinput.KEY_DOWN,
        uinput.KEY_LEFT,
        uinput.KEY_RIGHT,
        uinput.KEY_ENTER,
        uinput.KEY_ESC,
        uinput.KEY_HOME,
        uinput.KEY_BACKSPACE,
        uinput.KEY_SPACE,
        uinput.KEY_DOT,
        uinput.KEY_COMMA,
        uinput.KEY_SLASH,
        uinput.KEY_APOSTROPHE,
        uinput.KEY_MINUS,
        uinput.KEY_LEFTSHIFT,
        uinput.KEY_KPASTERISK,  # *
        uinput.KEY_EQUAL,  # proxy for #
    ]
    device = uinput.Device(events, name="Digivice-T9")

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for r in rows:
        GPIO.setup(r, GPIO.OUT, initial=GPIO.HIGH)
    for c in cols:
        GPIO.setup(c, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    mode = "abc"  # abc | ABC | 123
    # multi-tap state
    last_key: Optional[str] = None
    last_tap_t = 0.0
    multi_idx = 0
    # long-press detection: first detect edge then time held
    held: Dict[str, float] = {}
    stable: Dict[str, bool] = {}
    raw_count: Dict[str, int] = {}

    def tap_code(code, down: bool = True) -> None:
        device.emit(code, 1 if down else 0)
        if down:
            device.emit(code, 0)

    def emit_char(ch: str) -> None:
        if ch == " ":
            tap_code(uinput.KEY_SPACE)
            return
        punct = {
            ".": uinput.KEY_DOT,
            ",": uinput.KEY_COMMA,
            "?": uinput.KEY_SLASH,  # shift+/ often ?
            "!": uinput.KEY_1,
            "'": uinput.KEY_APOSTROPHE,
            '"': uinput.KEY_APOSTROPHE,
            "-": uinput.KEY_MINUS,
            "/": uinput.KEY_SLASH,
        }
        if ch in punct:
            if ch in "!?\"":
                # best-effort shifted glyphs
                if ch == "!":
                    device.emit(uinput.KEY_LEFTSHIFT, 1)
                    tap_code(uinput.KEY_1)
                    device.emit(uinput.KEY_LEFTSHIFT, 0)
                elif ch == "?":
                    device.emit(uinput.KEY_LEFTSHIFT, 1)
                    tap_code(uinput.KEY_SLASH)
                    device.emit(uinput.KEY_LEFTSHIFT, 0)
                else:
                    device.emit(uinput.KEY_LEFTSHIFT, 1)
                    tap_code(uinput.KEY_APOSTROPHE)
                    device.emit(uinput.KEY_LEFTSHIFT, 0)
            else:
                tap_code(punct[ch])
            return
        if ch.isdigit():
            tap_code(getattr(uinput, f"KEY_{ch}"))
            return
        if ch.isalpha():
            code = getattr(uinput, f"KEY_{ch.upper()}")
            if ch.isupper():
                device.emit(uinput.KEY_LEFTSHIFT, 1)
                tap_code(code)
                device.emit(uinput.KEY_LEFTSHIFT, 0)
            else:
                tap_code(code)

    def multi_tap(key: str) -> None:
        nonlocal last_key, last_tap_t, multi_idx, mode
        now = time.monotonic()
        table = ALPHABETS if mode == "abc" else ALPHABETS_UP if mode == "ABC" else None
        if mode == "123":
            emit_char(key)
            last_key = None
            return
        assert table is not None
        chars = table.get(key, key)
        if key == last_key and (now - last_tap_t) < TAP_MS:
            # replace previous char
            tap_code(uinput.KEY_BACKSPACE)
            multi_idx = (multi_idx + 1) % len(chars)
        else:
            multi_idx = 0
        last_key = key
        last_tap_t = now
        emit_char(chars[multi_idx])

    def cycle_mode() -> None:
        nonlocal mode, last_key
        mode = {"abc": "ABC", "ABC": "123", "123": "abc"}[mode]
        last_key = None
        print(f"T9 mode={mode}", flush=True)

    # Keys that wait for release (short vs long): * # D only
    HOLD_KEYS = {"*", "#", "D"}

    def fire_nav_digit(name: str) -> None:
        nonlocal last_key
        if name == "A":
            last_key = None
            tap_code(uinput.KEY_UP)
        elif name == "B":
            last_key = None
            tap_code(uinput.KEY_DOWN)
        elif name == "C":
            last_key = None
            tap_code(uinput.KEY_ENTER)
        elif name in "0123456789":
            multi_tap(name)

    def on_hold_short(name: str) -> None:
        nonlocal last_key
        if name == "*":
            last_key = None
            tap_code(uinput.KEY_LEFT)
        elif name == "#":
            last_key = None
            tap_code(uinput.KEY_RIGHT)
        elif name == "D":
            last_key = None
            tap_code(uinput.KEY_ESC)

    def on_hold_long(name: str) -> None:
        nonlocal last_key
        if name == "*":
            cycle_mode()
        elif name == "#":
            last_key = None
            tap_code(uinput.KEY_BACKSPACE)
        elif name == "D":
            last_key = None
            tap_code(uinput.KEY_HOME)

    def scan() -> List[str]:
        found: List[str] = []
        for ri, rp in enumerate(rows):
            GPIO.output(rp, GPIO.LOW)
            time.sleep(0.0003)
            for ci, cp in enumerate(cols):
                if GPIO.input(cp) == GPIO.LOW:
                    found.append(KEYS[ri][ci])
            GPIO.output(rp, GPIO.HIGH)
        return found

    print(
        f"t9-keypad ready mode={mode} rows={rows} cols={cols} "
        f"(A↑ B↓ C OK D Back · *◀ #▶ · long* mode long# ⌫)",
        flush=True,
    )

    try:
        while True:
            pressed = set(scan())
            now = time.monotonic()
            all_names = [KEYS[r][c] for r in range(4) for c in range(4)]
            for name in all_names:
                is_down = name in pressed
                if is_down:
                    raw_count[name] = raw_count.get(name, 0) + 1
                else:
                    raw_count[name] = 0

                was = stable.get(name, False)
                is_stable = raw_count.get(name, 0) >= 2
                if is_stable and not was:
                    stable[name] = True
                    held[name] = now
                    if name not in HOLD_KEYS:
                        fire_nav_digit(name)
                elif not is_down and was:
                    stable[name] = False
                    t0 = held.pop(name, now)
                    dt = now - t0
                    if name in HOLD_KEYS:
                        if dt >= LONG_MS:
                            on_hold_long(name)
                        else:
                            on_hold_short(name)
                elif not is_down:
                    stable[name] = False

            if last_key and (now - last_tap_t) >= TAP_MS:
                last_key = None

            time.sleep(SCAN_S)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
