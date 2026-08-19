#!/usr/bin/env python3
"""M5Stack CardKB on Pi I2C → Linux desktop keyboard (uinput).

Wiring (Pi 40-pin):
  CardKB 5V  → Pin 2  (5V)   — not 3.3V
  CardKB GND → Pin 6  (GND)
  CardKB SDA → Pin 3  (GPIO 2 / SDA1)
  CardKB SCL → Pin 5  (GPIO 3 / SCL1)

Poll /dev/i2c-1 @ 0x5F. Inject via uinput so keys work on Wayland
(labwc / Pi OS Trixie) as well as X11. Do not use xdotool here —
Xwayland "succeeds" then types into nothing native.

Keep this process alive from boot. Digivice only pauses
I2C via /run/digivice/cardkb.pause. Linux desktop typing is injected
through Digivice-Buttons (already on the labwc seat) so we do not
create a second virtual keyboard that steals Bluetooth HID.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

ADDR = 0x5F
I2C_TIMEOUT = 0x0702  # linux/i2c-dev.h — units of 10 ms
# Digivice writes this so we release I2C 0x5F. Do NOT stop this process —
# destroying the uinput keyboard after labwc has started means Wayland
# never types CardKB on the Linux desktop.
# /run/digivice has no sticky bit (unlike /tmp), so gear can delete a
# pause file root created.
PAUSE = Path("/run/digivice/cardkb.pause")
PAUSE_LEGACY = Path("/tmp/digivice-cardkb.pause")
TYPE_SOCK = Path("/run/digivice/type.sock")

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
    "`": "KEY_ESC",
    "~": "KEY_ESC",
    "[": "KEY_LEFTBRACE",
    "{": "KEY_LEFTBRACE",
    "]": "KEY_RIGHTBRACE",
    "}": "KEY_RIGHTBRACE",
    "\\": "KEY_BACKSLASH",
    "|": "KEY_BACKSLASH",
}
NEEDS_SHIFT = set(':!@#$%^&*()<>?"_+{}|~')


def log(msg: str) -> None:
    print(msg, flush=True)


def _ev_code(event) -> int:
    if isinstance(event, tuple) and len(event) >= 2:
        return int(event[1])
    return int(event)


class TypeSink:
    """Prefer Digivice-Buttons (already on the labwc seat). Own uinput is last resort."""

    def __init__(self, uinput_mod: Any):
        self._u = uinput_mod
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._dev: Any = None
        self._logged_path = ""

    def tap(self, event, *, shift: bool = False) -> None:
        code = _ev_code(event)
        msg = f"{'S' if shift else 'T'} {code}".encode("ascii")
        try:
            self._sock.sendto(msg, str(TYPE_SOCK))
            if self._logged_path != "buttons":
                log("CardKB typing via Digivice-Buttons (Bluetooth keyboards stay independent)")
                self._logged_path = "buttons"
            return
        except OSError:
            pass
        self._ensure_fallback()
        if self._dev is None:
            return
        try:
            if shift:
                self._dev.emit(self._u.KEY_LEFTSHIFT, 1)
            self._dev.emit(event, 1)
            time.sleep(0.01)
            self._dev.emit(event, 0)
            if shift:
                self._dev.emit(self._u.KEY_LEFTSHIFT, 0)
        except Exception as e:
            log(f"uinput fallback: {e}")

    def _ensure_fallback(self) -> None:
        if self._dev is not None:
            return
        uinput = self._u
        events = [getattr(uinput, f"KEY_{c}") for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
        events += [getattr(uinput, f"KEY_{d}") for d in "0123456789"]
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
            # Same class as Digivice-Buttons so labwc will hotplug it.
            uinput.BTN_LEFT,
            uinput.REL_X,
            uinput.REL_Y,
        ]
        try:
            self._dev = uinput.Device(
                events,
                name="Digivice-CardKB",
                bustype=0x03,
                vendor=0x1209,
                product=0x5F01,
                version=1,
            )
        except TypeError:
            self._dev = uinput.Device(events, name="Digivice-CardKB")
        log("WARN: type socket missing — CardKB fallback uinput (reboot if Linux ignores it)")
        self._logged_path = "uinput"


def _ensure_pause_dir() -> None:
    try:
        d = PAUSE.parent
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o0777)
    except OSError:
        pass


def _paused() -> bool:
    for p in (PAUSE, PAUSE_LEGACY):
        try:
            if p.is_file():
                return True
        except OSError:
            continue
    return False


def _open_bus(smbus_mod: Any, bus_id: int) -> Any:
    bus = smbus_mod.SMBus(bus_id)
    try:
        fd = getattr(bus, "fd", None)
        if fd is None and hasattr(bus, "_fd"):
            fd = bus._fd
        if fd is not None:
            fcntl.ioctl(fd, I2C_TIMEOUT, 8)  # 80 ms
    except Exception:
        pass
    return bus


def _read_key(bus: Any) -> int:
    try:
        from smbus2 import i2c_msg  # type: ignore

        msg = i2c_msg.read(ADDR, 1)
        bus.i2c_rdwr(msg)
        data = list(msg)
        return int(data[0]) if data else 0
    except Exception:
        return int(bus.read_byte(ADDR)) & 0xFF


def _probe(bus: Any) -> bool:
    """True if something ACKs at 0x5F."""
    try:
        _read_key(bus)
        return True
    except OSError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="CardKB → Linux desktop (uinput keyboard)")
    ap.add_argument("bus", nargs="?", type=int, default=1, help="I2C bus (default 1)")
    ap.add_argument("--hz", type=float, default=50.0, help="Poll rate Hz")
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

    try:
        subprocess.run(
            ["modprobe", "uinput"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

    sink = TypeSink(uinput)
    _ensure_pause_dir()

    bus: Optional[Any] = None

    def reopen() -> bool:
        nonlocal bus
        try:
            if bus is not None:
                bus.close()
        except Exception:
            pass
        bus = None
        time.sleep(0.2)
        try:
            bus = _open_bus(smbus, args.bus)
            return True
        except OSError as e:
            log(f"open i2c-{args.bus}: {e} — waiting (enable I2C / check wiring)")
            time.sleep(1.5)
            return False

    log(
        f"cardkb-inputd ready bus={args.bus} addr=0x{ADDR:02X} "
        f"(types through Digivice-Buttons; no extra keyboard device)"
    )

    def emit_special(logical: str, u_code) -> None:
        try:
            sink.tap(u_code)
        except Exception as e:
            log(f"type {logical}: {e}")

    def emit_char(ch: str) -> None:
        if ch in ("`", "~"):
            emit_special("ESC", uinput.KEY_ESC)
            return
        need_shift = ch.isupper() or ch in NEEDS_SHIFT
        base = ch.lower() if ch.isalpha() else ch
        try:
            if ch in PUNCT:
                name = PUNCT[ch]
                if name == "KEY_ESC":
                    emit_special("ESC", uinput.KEY_ESC)
                    return
                code = getattr(uinput, name)
            elif "a" <= base <= "z":
                code = getattr(uinput, f"KEY_{base.upper()}")
            elif "0" <= base <= "9":
                code = getattr(uinput, f"KEY_{base}")
            else:
                return
            sink.tap(code, shift=need_shift)
        except Exception as e:
            if args.verbose:
                log(f"type char {ch!r}: {e}")

    def handle(raw: int) -> None:
        if raw in ARROW:
            name = ARROW[raw]
            code = {
                "UP": uinput.KEY_UP,
                "DOWN": uinput.KEY_DOWN,
                "LEFT": uinput.KEY_LEFT,
                "RIGHT": uinput.KEY_RIGHT,
            }[name]
            emit_special(name, code)
            return
        if raw in (0x0D, 0x0A):
            emit_special("ENTER", uinput.KEY_ENTER)
            return
        if raw == 0x1B:
            emit_special("ESC", uinput.KEY_ESC)
            return
        if raw in (0x08, 0x7F):
            emit_special("BACKSPACE", uinput.KEY_BACKSPACE)
            return
        if raw == 0x09:
            emit_special("TAB", uinput.KEY_TAB)
            return
        if raw == 0x20:
            emit_special("SPACE", uinput.KEY_SPACE)
            return
        if 32 <= raw < 127:
            emit_char(chr(raw))
            return
        if args.verbose:
            log(f"cardkb skip 0x{raw:02X}")

    def drain() -> None:
        if bus is None:
            return
        for _ in range(4):
            try:
                if _read_key(bus) == 0:
                    return
            except OSError:
                return
            time.sleep(0.008)

    period = 1.0 / max(args.hz, 5.0)
    seen = False
    fail_streak = 0
    last_probe_log = 0.0
    pause_logged = False

    while True:
        if _paused():
            if not pause_logged:
                log("I2C paused — Digivice owns CardKB")
                pause_logged = True
            if bus is not None:
                try:
                    bus.close()
                except Exception:
                    pass
                bus = None
            seen = False
            time.sleep(0.4)
            continue
        if pause_logged:
            log("I2C resume — CardKB → Linux desktop")
            pause_logged = False

        if bus is None:
            if not reopen():
                continue
            if _probe(bus):
                log(f"CardKB ACK at 0x{ADDR:02X} on i2c-{args.bus}")
                seen = True
            else:
                now = time.monotonic()
                if now - last_probe_log > 8.0:
                    log(
                        f"No ACK at 0x{ADDR:02X} — check 5V/GND/SDA/SCL "
                        f"(pin 2/6/3/5) · sudo i2cdetect -y {args.bus}"
                    )
                    last_probe_log = now
                time.sleep(1.0)
                continue

        try:
            raw = _read_key(bus)
            fail_streak = 0
        except OSError as e:
            fail_streak += 1
            if seen or fail_streak <= 2:
                log(f"CardKB I2C error ({e}) — reopen")
            seen = False
            reopen()
            continue
        except Exception as e:
            log(f"CardKB read bug: {e!r}")
            reopen()
            continue

        if not seen:
            log("CardKB online")
            seen = True

        if raw == 0:
            time.sleep(period)
            continue

        if args.verbose:
            log(f"cardkb 0x{raw:02X}")

        try:
            handle(raw)
        except Exception as e:
            log(f"CardKB emit error 0x{raw:02X}: {e!r}")

        try:
            drain()
        except Exception:
            pass
        time.sleep(max(0.015, period * 0.4))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
