"""Passive piezo on Digivice GPIO (BCM22 / pin 15 by default)."""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

from esp_handset.hw_pins import BUZZER_BCM

_lock = threading.Lock()
_gpio: Any = None
_backend = ""
_chip = None  # lgpio chip handle
_pwm = None
_ready = False
_last_err = ""


def _setup() -> bool:
    global _gpio, _backend, _chip, _pwm, _ready, _last_err
    if _ready:
        return True
    if BUZZER_BCM is None:
        _last_err = "DIGI_BUZZER_BCM=off"
        return False
    try:
        from esp_handset.gpio_util import get_gpio

        mod, backend = get_gpio()
        if mod is None:
            from esp_handset.gpio_util import last_error

            _last_err = last_error() or "no GPIO backend"
            return False
        bcm = int(BUZZER_BCM)
        if backend == "RPi.GPIO":
            mod.setup(bcm, mod.OUT, initial=mod.LOW)
            _gpio = mod
            _backend = backend
            try:
                _pwm = mod.PWM(bcm, 440)
            except Exception:
                _pwm = None  # bit-bang fallback
            _ready = True
            _last_err = ""
            print(f"[buzzer] ready BCM{bcm} via {backend}", flush=True)
            return True
        if backend == "lgpio":
            chip = mod.gpiochip_open(0)
            mod.gpio_claim_output(chip, bcm, 0)
            _chip = chip
            _gpio = mod
            _backend = backend
            _pwm = None
            _ready = True
            _last_err = ""
            print(f"[buzzer] ready BCM{bcm} via lgpio", flush=True)
            return True
        _last_err = f"unknown backend {backend}"
        return False
    except Exception as e:
        _last_err = str(e)
        print(f"[buzzer] unavailable ({e})", flush=True)
        return False


def _bitbang(freq_hz: float, ms: int) -> bool:
    """Software square wave — works when PWM is unavailable."""
    bcm = int(BUZZER_BCM or 0)
    half = 0.5 / max(80.0, float(freq_hz))
    end = time.monotonic() + max(0.01, ms / 1000.0)
    try:
        if _backend == "RPi.GPIO" and _gpio is not None:
            while time.monotonic() < end:
                _gpio.output(bcm, 1)
                time.sleep(half)
                _gpio.output(bcm, 0)
                time.sleep(half)
            _gpio.output(bcm, 0)
            return True
        if _backend == "lgpio" and _gpio is not None and _chip is not None:
            while time.monotonic() < end:
                _gpio.gpio_write(_chip, bcm, 1)
                time.sleep(half)
                _gpio.gpio_write(_chip, bcm, 0)
                time.sleep(half)
            _gpio.gpio_write(_chip, bcm, 0)
            return True
    except Exception as e:
        _last_err = str(e)
        print(f"[buzzer] bitbang fail: {e}", flush=True)
    return False


def _sounds_enabled() -> bool:
    try:
        from esp_handset import store

        prefs = store.load("sounds.json", {"enabled": True, "profile": "Normal"})
        if prefs.get("profile") == "Silent":
            return False
        return bool(prefs.get("enabled", True))
    except Exception:
        return True


def tone(freq_hz: float, ms: int, duty: float = 50.0) -> bool:
    """Blocking beep. Returns False if no piezo / GPIO / muted."""
    del duty  # bit-bang uses ~50%
    if not _sounds_enabled():
        return False
    if not _setup():
        return False
    freq = max(80.0, min(4000.0, float(freq_hz)))
    ms = max(10, min(2000, int(ms)))
    with _lock:
        # Prefer PWM when available
        if _pwm is not None and _backend == "RPi.GPIO":
            try:
                _pwm.ChangeFrequency(freq)
                _pwm.start(50.0)
                time.sleep(ms / 1000.0)
                _pwm.stop()
                if _gpio is not None and BUZZER_BCM is not None:
                    _gpio.output(int(BUZZER_BCM), 0)
                return True
            except Exception as e:
                print(f"[buzzer] PWM fail → bitbang ({e})", flush=True)
        return _bitbang(freq, ms)


def chirp() -> bool:
    return tone(2400, 50)


def alert() -> bool:
    ok = False
    for i, f in enumerate((1600, 2000, 2400)):
        if tone(f, 130):
            ok = True
        if i < 2:
            time.sleep(0.05)
    return ok


def nav_tick() -> bool:
    return tone(1800, 30)


def beep_async(kind: str = "alert") -> None:
    def _run() -> None:
        try:
            if kind == "chirp":
                chirp()
            elif kind == "nav":
                nav_tick()
            else:
                alert()
        except Exception:
            pass

    threading.Thread(target=_run, name="digi-buzzer", daemon=True).start()


def available() -> bool:
    return BUZZER_BCM is not None and _setup()


def status() -> str:
    if BUZZER_BCM is None:
        return "Piezo disabled"
    if _ready:
        return f"OK BCM{BUZZER_BCM} ({_backend})"
    _setup()
    if _ready:
        return f"OK BCM{BUZZER_BCM} ({_backend})"
    return f"Fail BCM{BUZZER_BCM}: {_last_err or 'unknown'}"
