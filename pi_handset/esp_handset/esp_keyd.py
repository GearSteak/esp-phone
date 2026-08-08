#!/usr/bin/env python3
"""CDC → uinput keyboard + volume for ESP handset bridge."""

from __future__ import annotations

import subprocess
import sys
import time

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))

from esp_handset.bridge import EspBridge  # noqa: E402

PUNCT = {
    ";": "KEY_SEMICOLON",
    ":": "KEY_SEMICOLON",  # shift handled by emitting SHIFT+;
    ",": "KEY_COMMA",
    "<": "KEY_COMMA",
    ".": "KEY_DOT",
    ">": "KEY_DOT",
    "/": "KEY_SLASH",
    "?": "KEY_SLASH",
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

# Characters that need Shift held with the base key
NEEDS_SHIFT = set(":!@#$%^&*()<>?")


def volume_cmd(which: str) -> None:
    try:
        if which == "VOL_UP":
            subprocess.run(
                ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%+"],
                check=False,
                capture_output=True,
            )
        elif which == "VOL_DOWN":
            subprocess.run(
                ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%-"],
                check=False,
                capture_output=True,
            )
        elif which == "MUTE":
            subprocess.run(
                ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"],
                check=False,
                capture_output=True,
            )
            subprocess.run(
                ["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "toggle"],
                check=False,
                capture_output=True,
            )
    except FileNotFoundError:
        pass


def main() -> int:
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
        uinput.KEY_LEFTSHIFT,
        uinput.KEY_UP,
        uinput.KEY_DOWN,
        uinput.KEY_LEFT,
        uinput.KEY_RIGHT,
        uinput.KEY_VOLUMEUP,
        uinput.KEY_VOLUMEDOWN,
        uinput.KEY_MUTE,
        uinput.KEY_DOT,
        uinput.KEY_COMMA,
        uinput.KEY_SLASH,
        uinput.KEY_SEMICOLON,
        uinput.KEY_APOSTROPHE,
        uinput.KEY_MINUS,
        uinput.KEY_EQUAL,
    ]

    device = uinput.Device(events, name="ESP-Handset-Keys")
    bridge = EspBridge()
    bridge.open()
    print(f"esp-keyd on {bridge.port}", flush=True)

    def emit_char(ch: str, down: bool) -> None:
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
        if down:
            if need_shift:
                device.emit(uinput.KEY_LEFTSHIFT, 1)
            device.emit(code, 1)
        else:
            device.emit(code, 0)
            if need_shift:
                device.emit(uinput.KEY_LEFTSHIFT, 0)

    def on_event(kind: str, line: str) -> None:
        if kind != "KEY":
            return
        parts = line.split()
        if len(parts) < 3:
            return
        _, state, token = parts[0], parts[1], parts[2]
        down = state.upper() == "DOWN"
        if token in ("VOL_UP", "VOL_DOWN", "MUTE"):
            if down:
                volume_cmd(token)
            return
        if len(token) == 1:
            emit_char(token, down)
            return
        name = token.upper()
        mapping = {
            "UP": uinput.KEY_UP,
            "DOWN": uinput.KEY_DOWN,
            "LEFT": uinput.KEY_LEFT,
            "RIGHT": uinput.KEY_RIGHT,
            "ENTER": uinput.KEY_ENTER,
            "BKSP": uinput.KEY_BACKSPACE,
            "SPACE": uinput.KEY_SPACE,
            "SHIFT": uinput.KEY_LEFTSHIFT,
        }
        code = mapping.get(name)
        if code is None:
            return
        device.emit(code, 1 if down else 0)

    bridge.on_event(on_event)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
