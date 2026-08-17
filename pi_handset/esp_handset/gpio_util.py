"""Shared BCM GPIO access for Digivice (display / steps / piezo).

ST7789 already calls RPi.GPIO.setmode(BCM). Re-calling setmode can fail on
some builds — always reuse the live module when possible.
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

_gpio = None
_backend = ""
_error = ""


def get_gpio() -> Tuple[Optional[Any], str]:
    """Return (GPIO_module_or_lgpio_handle_factory, backend_name)."""
    global _gpio, _backend, _error
    if _gpio is not None:
        return _gpio, _backend
    # Prefer RPi.GPIO (already used by ST7789 / Digivice)
    try:
        import RPi.GPIO as GPIO  # type: ignore

        GPIO.setwarnings(False)
        try:
            GPIO.setmode(GPIO.BCM)
        except Exception:
            # Mode already set elsewhere in this process — OK
            pass
        _gpio = GPIO
        _backend = "RPi.GPIO"
        _error = ""
        return _gpio, _backend
    except Exception as e:
        _error = str(e)
    try:
        import lgpio  # type: ignore

        _gpio = lgpio
        _backend = "lgpio"
        _error = ""
        return _gpio, _backend
    except Exception as e:
        _error = f"{_error}; lgpio: {e}" if _error else str(e)
    return None, ""


def last_error() -> str:
    return _error
