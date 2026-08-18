"""Passive piezo on Digivice GPIO (BCM22 / pin 15 by default).

Must work after the LCD already claimed RPi.GPIO, and after Bookworm
falls back to lgpio (RPi.GPIO often imports then fails on setup).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

from esp_handset.hw_pins import BUZZER_BCM

_lock = threading.Lock()
_gpio: Any = None
_backend = ""
_chip = None  # lgpio chip handle
_pwm: Any = None
_lg_pwm = False
_ready = False
_last_err = ""


def _reset() -> None:
    global _gpio, _backend, _chip, _pwm, _lg_pwm, _ready
    if _pwm is not None and _backend == "RPi.GPIO":
        try:
            _pwm.stop()
        except Exception:
            pass
    if _lg_pwm and _gpio is not None and _chip is not None and BUZZER_BCM is not None:
        try:
            _gpio.tx_pwm(_chip, int(BUZZER_BCM), 0, 0)
        except Exception:
            pass
    if _backend == "lgpio" and _gpio is not None and _chip is not None:
        try:
            _gpio.gpiochip_close(_chip)
        except Exception:
            pass
    _gpio = None
    _backend = ""
    _chip = None
    _pwm = None
    _lg_pwm = False
    _ready = False


def _try_rpi(bcm: int) -> bool:
    global _gpio, _backend, _pwm, _ready, _last_err
    import RPi.GPIO as GPIO  # type: ignore

    GPIO.setwarnings(False)
    try:
        GPIO.setmode(GPIO.BCM)
    except Exception:
        pass
    GPIO.setup(bcm, GPIO.OUT, initial=GPIO.LOW)
    _gpio = GPIO
    _backend = "RPi.GPIO"
    try:
        _pwm = GPIO.PWM(bcm, 440)
    except Exception:
        _pwm = None
    _ready = True
    _last_err = ""
    print(f"[buzzer] ready BCM{bcm} via RPi.GPIO", flush=True)
    return True


def _try_lgpio(bcm: int) -> bool:
    global _gpio, _backend, _chip, _lg_pwm, _ready, _last_err
    import lgpio  # type: ignore

    chip = lgpio.gpiochip_open(0)
    try:
        lgpio.gpio_free(chip, bcm)
    except Exception:
        pass
    lgpio.gpio_claim_output(chip, bcm, 0)
    _chip = chip
    _gpio = lgpio
    _backend = "lgpio"
    _lg_pwm = True
    _ready = True
    _last_err = ""
    print(f"[buzzer] ready BCM{bcm} via lgpio", flush=True)
    return True


def _setup(*, force: bool = False) -> bool:
    global _last_err
    if _ready and not force:
        return True
    if force:
        _reset()
    if BUZZER_BCM is None:
        _last_err = "DIGI_BUZZER_BCM=off"
        return False
    bcm = int(BUZZER_BCM)
    errors = []
    for name, fn in (("RPi.GPIO", _try_rpi), ("lgpio", _try_lgpio)):
        try:
            if fn(bcm):
                return True
        except Exception as e:
            errors.append(f"{name}: {e}")
            _reset()
    _last_err = "; ".join(errors) or "no GPIO backend"
    print(f"[buzzer] unavailable ({_last_err})", flush=True)
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


def _lgpio_pwm(freq: float, ms: int) -> bool:
    bcm = int(BUZZER_BCM or 0)
    try:
        _gpio.tx_pwm(_chip, bcm, float(freq), 50.0)
        time.sleep(ms / 1000.0)
        _gpio.tx_pwm(_chip, bcm, 0, 0)
        _gpio.gpio_write(_chip, bcm, 0)
        return True
    except Exception as e:
        _last_err = str(e)
        print(f"[buzzer] lgpio PWM fail → bitbang ({e})", flush=True)
        try:
            _gpio.tx_pwm(_chip, bcm, 0, 0)
        except Exception:
            pass
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


def tone(freq_hz: float, ms: int, duty: float = 50.0, *, force: bool = False) -> bool:
    """Blocking beep. Returns False if no piezo / GPIO / muted."""
    del duty
    if not force and not _sounds_enabled():
        return False
    if not _setup():
        return False
    freq = max(80.0, min(4000.0, float(freq_hz)))
    ms = max(10, min(2000, int(ms)))
    with _lock:
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
        if _lg_pwm and _gpio is not None and _chip is not None:
            if _lgpio_pwm(freq, ms):
                return True
        return _bitbang(freq, ms)


def chirp(*, force: bool = False) -> bool:
    return tone(2000, 90, force=force)


def alert(*, force: bool = False) -> bool:
    ok = False
    for i, f in enumerate((1200, 1600, 2000)):
        if tone(f, 180, force=force):
            ok = True
        if i < 2:
            time.sleep(0.04)
    return ok


def nav_tick() -> bool:
    return tone(1800, 30)


def beep_async(kind: str = "alert", *, force: bool = False) -> None:
    def _run() -> None:
        try:
            if kind == "chirp":
                chirp(force=force)
            elif kind == "nav":
                nav_tick()
            else:
                alert(force=force)
        except Exception:
            pass

    threading.Thread(target=_run, name="digi-buzzer", daemon=True).start()


def available() -> bool:
    return BUZZER_BCM is not None and _setup()


def status() -> str:
    if BUZZER_BCM is None:
        return "Piezo disabled"
    if _ready:
        how = "PWM" if (_pwm is not None or _lg_pwm) else "bitbang"
        return f"OK pin 15 BCM{BUZZER_BCM} {how} ({_backend})"
    _setup()
    if _ready:
        how = "PWM" if (_pwm is not None or _lg_pwm) else "bitbang"
        return f"OK pin 15 BCM{BUZZER_BCM} {how} ({_backend})"
    return f"Fail pin 15: {_last_err or 'unknown'}"
