#!/usr/bin/env python3
"""Digivice discrete buttons → keys Digivice can actually see.

Seven hard keys (each: GPIO → switch → GND, internal pull-up):

  UP / DOWN / LEFT / RIGHT / CONFIRM / BACK / HOME

BCM defaults (free of 2\" LCD SPI: 8,10,11,18,25,27):

  UP=5  DOWN=6  LEFT=12  RIGHT=13  CONFIRM=16  BACK=19  HOME=20

Override with DIGI_BTN_UP=… etc.

Emits:
  1) uinput virtual keyboard "Digivice-Buttons"
  2) xdotool into DISPLAY=:0 (X11 Digivice) — required on many Pi sessions
     where root uinput events never reach the GUI seat

Logs every press to journal so you can confirm wiring.
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys
import time
from typing import Dict, Optional

DEFAULTS = {
    "UP": 5,
    "DOWN": 6,
    "LEFT": 12,
    "RIGHT": 13,
    "CONFIRM": 16,
    "BACK": 19,
    "HOME": 20,
}

# xdotool key names
XDOTOOL = {
    "UP": "Up",
    "DOWN": "Down",
    "LEFT": "Left",
    "RIGHT": "Right",
    "CONFIRM": "Return",
    "BACK": "Escape",
    "HOME": "Home",
}

DEBOUNCE_S = float(os.environ.get("DIGI_BTN_DEBOUNCE", "0.025"))
SCAN_S = float(os.environ.get("DIGI_BTN_SCAN", "0.01"))
# 0 = pressed shorted to GND (default). 1 = pressed = high.
ACTIVE_HIGH = os.environ.get("DIGI_BTN_ACTIVE_HIGH", "0").strip() in (
    "1",
    "true",
    "yes",
)


def log(msg: str) -> None:
    print(f"[digi-buttons] {msg}", flush=True)


def pin_map() -> Dict[str, int]:
    out: Dict[str, int] = {}
    for name, default in DEFAULTS.items():
        env = os.environ.get(f"DIGI_BTN_{name}", "").strip()
        out[name] = int(env) if env else default
    return out


def load_uinput_mod() -> None:
    try:
        subprocess.run(
            ["modprobe", "uinput"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def find_xauthority() -> Optional[str]:
    for cand in (
        os.environ.get("XAUTHORITY"),
        "/home/pi/.Xauthority",
        "/home/isaac/.Xauthority",
    ):
        if cand and os.path.isfile(cand):
            return cand
    # Autologin user(s)
    for path in glob.glob("/home/*/.Xauthority"):
        if os.path.isfile(path):
            return path
    # Xorg root /tmp
    for path in glob.glob("/run/user/*/gdm/Xauthority"):
        if os.path.isfile(path):
            return path
    for path in glob.glob("/run/user/*/Xauthority"):
        if os.path.isfile(path):
            return path
    return None


def find_display() -> str:
    return os.environ.get("DISPLAY") or ":0"


class XInject:
    """Push keys into the graphical session (Qt on X11 / XWayland)."""

    def __init__(self) -> None:
        self.display = find_display()
        self.auth = find_xauthority()
        self.xdotool = _which("xdotool")
        self.ok = bool(self.xdotool)
        if self.ok:
            log(
                f"X inject ON via xdotool display={self.display} "
                f"XAUTHORITY={self.auth or '(none)'}"
            )
        else:
            log("X inject OFF (install xdotool: sudo apt install xdotool)")

    def emit(self, name: str, down: bool) -> None:
        if not self.ok:
            return
        key = XDOTOOL.get(name)
        if not key:
            return
        env = os.environ.copy()
        env["DISPLAY"] = self.display
        if self.auth:
            env["XAUTHORITY"] = self.auth
        # Clear stuck modifiers that can swallow Digivice shortcuts
        action = "keydown" if down else "keyup"
        try:
            subprocess.run(
                [self.xdotool, action, key],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=0.5,
                check=False,
            )
        except Exception as e:
            log(f"xdotool {name}: {e}")


def _which(name: str) -> Optional[str]:
    for d in os.environ.get("PATH", "/usr/bin:/bin").split(":"):
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


class GpioBackend:
    def setup(self, pins: Dict[str, int]) -> None:
        raise NotImplementedError

    def read(self, pin: int) -> int:
        raise NotImplementedError

    def cleanup(self) -> None:
        pass


class RPiGpio(GpioBackend):
    def __init__(self) -> None:
        import RPi.GPIO as GPIO  # type: ignore

        self.GPIO = GPIO

    def setup(self, pins: Dict[str, int]) -> None:
        self.GPIO.setmode(self.GPIO.BCM)
        self.GPIO.setwarnings(False)
        for pin in pins.values():
            self.GPIO.setup(pin, self.GPIO.IN, pull_up_down=self.GPIO.PUD_UP)

    def read(self, pin: int) -> int:
        return int(self.GPIO.input(pin))

    def cleanup(self) -> None:
        try:
            self.GPIO.cleanup()
        except Exception:
            pass


class LgpioBackend(GpioBackend):
    """Bookworm / Pi5 style via lgpio if RPi.GPIO missing."""

    def __init__(self) -> None:
        import lgpio  # type: ignore

        self.lgpio = lgpio
        self.h = lgpio.gpiochip_open(0)
        self._pins: Dict[int, None] = {}

    def setup(self, pins: Dict[str, int]) -> None:
        for pin in pins.values():
            # pull up, input
            self.lgpio.gpio_claim_input(self.h, pin, self.lgpio.SET_PULL_UP)
            self._pins[pin] = None

    def read(self, pin: int) -> int:
        return int(self.lgpio.gpio_read(self.h, pin))

    def cleanup(self) -> None:
        try:
            self.lgpio.gpiochip_close(self.h)
        except Exception:
            pass


def open_gpio() -> GpioBackend:
    try:
        g = RPiGpio()
        log("GPIO backend: RPi.GPIO")
        return g
    except Exception as e:
        log(f"RPi.GPIO unavailable ({e})")
    try:
        g = LgpioBackend()
        log("GPIO backend: lgpio")
        return g
    except Exception as e:
        log(f"lgpio unavailable ({e})")
        raise SystemExit(
            "No GPIO backend — install python3-rpi.gpio or python3-lgpio"
        ) from e


def open_uinput(events):
    import uinput  # type: ignore

    load_uinput_mod()
    # BUS_USB helps some libinput stacks classify as keyboard
    try:
        dev = uinput.Device(
            events,
            name="Digivice-Buttons",
            bustype=0x03,  # BUS_USB
            vendor=0x1D6B,
            product=0x0104,
            version=1,
        )
    except TypeError:
        dev = uinput.Device(events, name="Digivice-Buttons")
    log("uinput device Digivice-Buttons created")
    return dev


def is_pressed(level: int) -> bool:
    if ACTIVE_HIGH:
        return level != 0
    return level == 0


def main() -> int:
    try:
        import uinput
    except ImportError:
        log("FATAL: python3-uinput required (sudo apt install python3-uinput)")
        return 1

    pins = pin_map()
    gpio = open_gpio()
    gpio.setup(pins)

    phone_map = {
        "UP": uinput.KEY_UP,
        "DOWN": uinput.KEY_DOWN,
        "LEFT": uinput.KEY_LEFT,
        "RIGHT": uinput.KEY_RIGHT,
        "CONFIRM": uinput.KEY_ENTER,
        "BACK": uinput.KEY_ESC,
        "HOME": uinput.KEY_HOME,
    }
    device = open_uinput(list(phone_map.values()))
    xinj = XInject()

    # Probe starting levels
    levels = {n: gpio.read(p) for n, p in pins.items()}
    log(
        "ready "
        + " ".join(f"{n}=BCM{p}(lvl={levels[n]})" for n, p in pins.items())
        + f" active_high={int(ACTIVE_HIGH)}"
    )
    stuck = [n for n, lv in levels.items() if is_pressed(lv)]
    if stuck:
        log(
            f"WARN: already 'pressed' at start: {stuck} — "
            "check short-to-GND wiring / wrong pins"
        )
    floating_wrong = []
    # All should be high (1) at rest for pull-up active-low
    if not ACTIVE_HIGH:
        floating_wrong = [n for n, lv in levels.items() if lv not in (0, 1)]
    if all(lv == 0 for lv in levels.values()) and not ACTIVE_HIGH:
        log(
            "WARN: ALL pins read 0 — common GND missing, "
            "or wiring ties signals low"
        )

    prev = {n: levels[n] for n in pins}
    raw = {n: levels[n] for n in pins}
    stable_since = {n: time.monotonic() for n in pins}
    press_count = 0

    try:
        while True:
            now = time.monotonic()
            for name, pin in pins.items():
                try:
                    level = gpio.read(pin)
                except Exception as e:
                    log(f"read BCM{pin}: {e}")
                    continue
                if level != raw[name]:
                    raw[name] = level
                    stable_since[name] = now
                    continue
                if now - stable_since[name] < DEBOUNCE_S:
                    continue
                if level == prev[name]:
                    continue
                prev[name] = level
                down = is_pressed(level)
                try:
                    device.emit(phone_map[name], 1 if down else 0)
                except Exception as e:
                    log(f"uinput emit {name}: {e}")
                xinj.emit(name, down)
                if down:
                    press_count += 1
                    log(
                        f"PRESS {name} BCM{pin} "
                        f"(#{press_count}) → {XDOTOOL.get(name)}"
                    )
                else:
                    log(f"RELEASE {name} BCM{pin}")
            time.sleep(SCAN_S)
    except KeyboardInterrupt:
        pass
    finally:
        gpio.cleanup()
        try:
            device.destroy()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
