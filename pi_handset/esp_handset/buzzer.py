"""Passive piezo on a Digivice GPIO (until CM108 / speaker is reliable)."""
from __future__ import annotations

import threading
import time
from typing import Optional

from esp_handset.hw_pins import BUZZER_BCM

_lock = threading.Lock()
_gpio = None
_pwm = None
_ready = False
_failed = False


def _setup() -> bool:
    global _gpio, _pwm, _ready, _failed
    if _ready:
        return True
    if _failed or BUZZER_BCM is None:
        return False
    try:
        import RPi.GPIO as GPIO  # type: ignore

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(int(BUZZER_BCM), GPIO.OUT, initial=GPIO.LOW)
        _gpio = GPIO
        _pwm = GPIO.PWM(int(BUZZER_BCM), 440)
        _ready = True
        return True
    except Exception as e:
        print(f"[buzzer] unavailable ({e})", flush=True)
        _failed = True
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
    """Blocking square-wave beep. Returns False if no piezo / GPIO / muted."""
    if not _sounds_enabled():
        return False
    if not _setup() or _pwm is None:
        return False
    freq = max(80.0, min(6000.0, float(freq_hz)))
    ms = max(10, int(ms))
    with _lock:
        try:
            _pwm.ChangeFrequency(freq)
            _pwm.start(max(5.0, min(90.0, duty)))
            time.sleep(ms / 1000.0)
            _pwm.stop()
            if _gpio is not None and BUZZER_BCM is not None:
                _gpio.output(int(BUZZER_BCM), 0)
            return True
        except Exception as e:
            print(f"[buzzer] tone fail: {e}", flush=True)
            return False


def chirp() -> bool:
    """Short notify tick (toasts / SMS)."""
    return tone(2400, 45)


def alert() -> bool:
    """Alarm / timer pattern — three rising beeps."""
    ok = False
    for i, f in enumerate((1600, 2000, 2400)):
        if tone(f, 120):
            ok = True
        if i < 2:
            time.sleep(0.06)
    return ok


def nav_tick() -> bool:
    """Soft UI click alternative."""
    return tone(1800, 25, duty=40.0)


def beep_async(kind: str = "alert") -> None:
    """Fire-and-forget from the UI thread."""

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

    threading.Thread(target=_run, daemon=True).start()


def available() -> bool:
    return BUZZER_BCM is not None and _setup()
