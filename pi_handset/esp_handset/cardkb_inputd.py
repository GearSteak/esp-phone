#!/usr/bin/env python3
"""M5Stack CardKB on Pi I2C → Digivice (uinput + xdotool).

Wiring (Pi 40-pin):
  CardKB 5V  → Pin 2  (5V)   — not 3.3V
  CardKB GND → Pin 6  (GND)
  CardKB SDA → Pin 3  (GPIO 2 / SDA1)
  CardKB SCL → Pin 5  (GPIO 3 / SCL1)

Poll /dev/i2c-1 @ 0x5F. Same dual inject as digi-buttons (uinput + xdotool)
so keys reach Digivice on the SPI kiosk display.
Prefer: dtparam=i2c_arm_baudrate=50000
"""

from __future__ import annotations

import argparse
import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, List, Optional

ADDR = 0x5F
I2C_TIMEOUT = 0x0702  # linux/i2c-dev.h — units of 10 ms

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

# xdotool key names for specials / arrows
XDOTOOL_SPECIAL = {
    "UP": "Up",
    "DOWN": "Down",
    "LEFT": "Left",
    "RIGHT": "Right",
    "ENTER": "Return",
    "ESC": "Escape",
    "BACKSPACE": "BackSpace",
    "TAB": "Tab",
    "SPACE": "space",
}


def log(msg: str) -> None:
    print(msg, flush=True)


def _which(name: str) -> Optional[str]:
    for d in os.environ.get("PATH", "/usr/bin:/bin").split(":"):
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def _find_xauthority() -> Optional[str]:
    for cand in (
        os.environ.get("XAUTHORITY") or "",
        "/home/pi/.Xauthority",
        str(Path.home() / ".Xauthority"),
    ):
        if cand and os.path.isfile(cand):
            return cand
    # Common Digivice user homes
    for home in Path("/home").glob("*/.Xauthority"):
        return str(home)
    return None


class XInject:
    """Mirror digi-buttons: push keys into the Digivice X session."""

    def __init__(self) -> None:
        self.display = os.environ.get("DISPLAY") or ":0"
        self.auth = _find_xauthority()
        self.xdotool = _which("xdotool")
        self.ok = bool(self.xdotool)
        if self.ok:
            log(
                f"X inject ON display={self.display} "
                f"XAUTHORITY={self.auth or '(none)'}"
            )
        else:
            log("X inject OFF — sudo apt install xdotool (uinput only)")

    def _env(self) -> dict:
        env = os.environ.copy()
        env["DISPLAY"] = self.display
        if self.auth:
            env["XAUTHORITY"] = self.auth
        return env

    def _run(self, args: List[str]) -> None:
        if not self.ok:
            return
        try:
            subprocess.run(
                [self.xdotool, *args],
                env=self._env(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=0.8,
                check=False,
            )
        except Exception:
            pass

    def key_named(self, name: str) -> None:
        if name:
            self._run(["key", "--clearmodifiers", name])

    def type_char(self, ch: str) -> None:
        if not ch:
            return
        # type is more reliable for letters than synthesizing Shift+key
        self._run(["type", "--clearmodifiers", "--delay", "1", "--", ch])


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
    ap = argparse.ArgumentParser(description="CardKB → Digivice (uinput + xdotool)")
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
    xinj = XInject()

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
        f"(uinput+xdotool · arrows=nav Enter=confirm Esc=back)"
    )

    def tap_uinput(code: int) -> None:
        device.emit(code, 1)
        time.sleep(0.012)
        device.emit(code, 0)

    def emit_special(logical: str, u_code: int) -> None:
        # Prefer xdotool (same path as digi-buttons into Digivice). Avoid
        # dual-fire doubles that plagued Escape.
        if xinj.ok:
            xinj.key_named(XDOTOOL_SPECIAL.get(logical, ""))
            return
        try:
            tap_uinput(u_code)
        except Exception as e:
            log(f"uinput {logical}: {e}")

    def emit_char(ch: str) -> None:
        if ch in ("`", "~"):
            emit_special("ESC", uinput.KEY_ESC)
            return
        if xinj.ok:
            xinj.type_char(ch)
            return
        # Fallback: synthesize via uinput when X inject is unavailable
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
        except Exception as e:
            if args.verbose:
                log(f"uinput char {ch!r}: {e}")

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

    while True:
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
                device.emit(uinput.KEY_LEFTSHIFT, 0)
            except Exception:
                pass

        try:
            drain()
        except Exception:
            pass
        time.sleep(max(0.015, period * 0.4))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
