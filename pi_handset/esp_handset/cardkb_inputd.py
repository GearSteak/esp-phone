#!/usr/bin/env python3
"""M5Stack CardKB on Pi I2C → uinput (Digivice nav + typing).

Wiring (Pi 40-pin):
  CardKB 5V  → Pin 2  (5V)
  CardKB GND → Pin 6  (GND)
  CardKB SDA → Pin 3  (GPIO 2 / SDA1)
  CardKB SCL → Pin 5  (GPIO 3 / SCL1)

Poll /dev/i2c-1 @ 0x5F. Survives I2C wedges (reopen bus) and emit errors.
Prefer slower I2C baud on Pi Zero: dtparam=i2c_arm_baudrate=50000
"""

from __future__ import annotations

import argparse
import fcntl
import sys
import time
from typing import Any, Optional

ADDR = 0x5F

# linux/i2c-dev.h — timeout in units of 10 ms
I2C_TIMEOUT = 0x0702

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
    "`": "KEY_ESC",  # CardKB ~/` often used as escape-ish
    "~": "KEY_ESC",
    "[": "KEY_LEFTBRACE",
    "{": "KEY_LEFTBRACE",
    "]": "KEY_RIGHTBRACE",
    "}": "KEY_RIGHTBRACE",
    "\\": "KEY_BACKSLASH",
    "|": "KEY_BACKSLASH",
}
NEEDS_SHIFT = set(':!@#$%^&*()<>?"_+{}|~')


def _open_bus(smbus_mod: Any, bus_id: int) -> Any:
    bus = smbus_mod.SMBus(bus_id)
    # Bound hung clock-stretch / NACK so one bad read cannot freeze the daemon
    try:
        fd = getattr(bus, "fd", None)
        if fd is None and hasattr(bus, "_fd"):
            fd = bus._fd
        if fd is not None:
            fcntl.ioctl(fd, I2C_TIMEOUT, 5)  # 50 ms
    except Exception:
        pass
    return bus


def _read_key(bus: Any) -> int:
    """Raw 1-byte I2C read (CardKB protocol). Prefer i2c_rdwr when available."""
    try:
        from smbus2 import i2c_msg  # type: ignore

        msg = i2c_msg.read(ADDR, 1)
        bus.i2c_rdwr(msg)
        data = list(msg)
        return int(data[0]) if data else 0
    except Exception:
        return int(bus.read_byte(ADDR)) & 0xFF


def main() -> int:
    ap = argparse.ArgumentParser(description="CardKB → uinput for Digivice")
    ap.add_argument("bus", nargs="?", type=int, default=1, help="I2C bus (default 1)")
    ap.add_argument("--hz", type=float, default=40.0, help="Poll rate Hz")
    ap.add_argument("-v", "--verbose", action="store_true", help="Log every keycode")
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
        uinput.KEY_LEFTBRACE,
        uinput.KEY_RIGHTBRACE,
        uinput.KEY_BACKSLASH,
    ]
    device = uinput.Device(events, name="Digivice-CardKB")

    bus: Optional[Any] = None
    try:
        bus = _open_bus(smbus, args.bus)
    except OSError as e:
        print(f"open i2c-{args.bus}: {e} (enable I2C, check wiring)", file=sys.stderr)
        return 1

    print(
        f"cardkb-inputd ready bus={args.bus} addr=0x{ADDR:02X} "
        f"(arrows=nav Enter=confirm Esc=back)",
        flush=True,
    )

    def reopen() -> None:
        nonlocal bus
        try:
            if bus is not None:
                bus.close()
        except Exception:
            pass
        bus = None
        time.sleep(0.15)
        try:
            bus = _open_bus(smbus, args.bus)
            print("CardKB I2C reopened", flush=True)
        except OSError as e:
            print(f"CardKB reopen failed: {e}", flush=True)
            time.sleep(0.5)

    def tap(code: int) -> None:
        device.emit(code, 1)
        time.sleep(0.012)
        device.emit(code, 0)

    def emit_char(ch: str) -> None:
        need_shift = ch.isupper() or ch in NEEDS_SHIFT
        base = ch.lower() if ch.isalpha() else ch
        if ch in ("`", "~"):
            tap(uinput.KEY_ESC)
            return
        if ch in PUNCT:
            name = PUNCT[ch]
            if name == "KEY_ESC":
                tap(uinput.KEY_ESC)
                return
            code = getattr(uinput, name)
        elif "a" <= base <= "z":
            code = getattr(uinput, f"KEY_{base.upper()}")
        elif "0" <= base <= "9":
            code = getattr(uinput, f"KEY_{base}")
        else:
            return
        shift_down = False
        try:
            if need_shift:
                device.emit(uinput.KEY_LEFTSHIFT, 1)
                shift_down = True
            device.emit(code, 1)
            time.sleep(0.01)
            device.emit(code, 0)
        finally:
            if shift_down:
                try:
                    device.emit(uinput.KEY_LEFTSHIFT, 0)
                except Exception:
                    pass

    def handle(raw: int) -> None:
        if raw in ARROW:
            name = ARROW[raw]
            code = {
                "UP": uinput.KEY_UP,
                "DOWN": uinput.KEY_DOWN,
                "LEFT": uinput.KEY_LEFT,
                "RIGHT": uinput.KEY_RIGHT,
            }[name]
            tap(code)
            return
        if raw in (0x0D, 0x0A):
            tap(uinput.KEY_ENTER)
            return
        if raw == 0x1B:
            tap(uinput.KEY_ESC)
            return
        if raw in (0x08, 0x7F):
            tap(uinput.KEY_BACKSPACE)
            return
        if raw == 0x09:
            tap(uinput.KEY_TAB)
            return
        if raw == 0x20:
            tap(uinput.KEY_SPACE)
            return
        if 32 <= raw < 127:
            emit_char(chr(raw))
            return
        # Fn-layer / unknown — ignore quietly (or log)
        if args.verbose:
            print(f"cardkb skip 0x{raw:02X}", flush=True)

    def drain() -> None:
        """Clear any leftover key byte so the unit does not stick."""
        if bus is None:
            return
        for _ in range(4):
            try:
                if _read_key(bus) == 0:
                    return
            except OSError:
                return
            time.sleep(0.01)

    period = 1.0 / max(args.hz, 5.0)
    seen = False
    fail_streak = 0

    while True:
        if bus is None:
            reopen()
            if bus is None:
                continue
        try:
            raw = _read_key(bus)
            fail_streak = 0
        except OSError as e:
            fail_streak += 1
            if seen or fail_streak == 1:
                print(f"CardKB I2C error ({e}) — reopen", flush=True)
            seen = False
            if fail_streak >= 1:
                reopen()
            else:
                time.sleep(0.2)
            continue
        except Exception as e:
            print(f"CardKB read bug: {e!r}", flush=True)
            reopen()
            continue

        if not seen:
            print("CardKB online", flush=True)
            seen = True

        if raw == 0:
            time.sleep(period)
            continue

        if args.verbose:
            print(f"cardkb 0x{raw:02X}", flush=True)

        try:
            handle(raw)
        except Exception as e:
            print(f"CardKB emit error 0x{raw:02X}: {e!r}", flush=True)
            # Release modifiers if a partial emit left them down
            try:
                device.emit(uinput.KEY_LEFTSHIFT, 0)
            except Exception:
                pass

        try:
            drain()
        except Exception:
            pass
        time.sleep(max(0.02, period * 0.5))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
