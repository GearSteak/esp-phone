"""Passive piezo on Digivice GPIO (BCM22 / physical pin 15 by default).

Trixie: classic RPi.GPIO often imports (or is rpi-lgpio) then PWM is a no-op.
GPIO 22 has no hardware PWM (12/13/18/19 are LCD BL + d-pad). Use lgpio
software PWM, then a busy-wait square wave (time.sleep is too coarse at 2 kHz).

Wiring: piezo + → pin 15 (optional 100–220Ω), piezo − → GND.
Pin 22 is LCD DC — do not put the piezo there.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable, List, Optional

from esp_handset.hw_pins import BUZZER_BCM

_lock = threading.Lock()
_gpio: Any = None
_backend = ""
_chip = None
_chip_n = -1
_pwm: Any = None
_lg_pwm = False
_ready = False
_last_err = ""
_write: Optional[Callable[[int], None]] = None


def _reset() -> None:
    global _gpio, _backend, _chip, _chip_n, _pwm, _lg_pwm, _ready, _write
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
            _gpio.gpio_free(_chip, int(BUZZER_BCM))
        except Exception:
            pass
        try:
            _gpio.gpiochip_close(_chip)
        except Exception:
            pass
    _gpio = None
    _backend = ""
    _chip = None
    _chip_n = -1
    _pwm = None
    _lg_pwm = False
    _ready = False
    _write = None


def _chip_candidates() -> List[int]:
    found: List[int] = []
    for p in sorted(Path("/dev").glob("gpiochip*")):
        try:
            found.append(int(p.name.replace("gpiochip", "")))
        except ValueError:
            continue
    # Pi 0/3/Zero: 0. Pi 5: 4 is often pinctrl.
    order: List[int] = []
    for n in (0, 4, 5, *found):
        if n not in order:
            order.append(n)
    return order


def _try_lgpio(bcm: int) -> bool:
    global _gpio, _backend, _chip, _chip_n, _lg_pwm, _ready, _last_err, _write
    import lgpio  # type: ignore

    last = ""
    for n in _chip_candidates():
        chip = None
        try:
            chip = lgpio.gpiochip_open(n)
            try:
                lgpio.gpio_free(chip, bcm)
            except Exception:
                pass
            lgpio.gpio_claim_output(chip, bcm, 0)
            _chip = chip
            _chip_n = n
            _gpio = lgpio
            _backend = "lgpio"
            _lg_pwm = True
            _ready = True
            _last_err = ""

            def _w(level: int, _c=chip, _b=bcm, _lg=lgpio) -> None:
                _lg.gpio_write(_c, _b, 1 if level else 0)

            _write = _w
            print(f"[buzzer] ready BCM{bcm} via lgpio gpiochip{n}", flush=True)
            return True
        except Exception as e:
            last = f"gpiochip{n}: {e}"
            if chip is not None:
                try:
                    lgpio.gpiochip_close(chip)
                except Exception:
                    pass
    _last_err = last or "lgpio: no gpiochip"
    return False


def _try_rpi(bcm: int) -> bool:
    global _gpio, _backend, _pwm, _ready, _last_err, _write
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
        _pwm = GPIO.PWM(bcm, 2500)
    except Exception:
        _pwm = None
    _ready = True
    _last_err = ""

    def _w(level: int, _g=GPIO, _b=bcm) -> None:
        _g.output(_b, 1 if level else 0)

    _write = _w
    print(f"[buzzer] ready BCM{bcm} via RPi.GPIO", flush=True)
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
    # lgpio first — Trixie RPi.GPIO PWM is often silent
    for name, fn in (("lgpio", _try_lgpio), ("RPi.GPIO", _try_rpi)):
        try:
            if fn(bcm):
                return True
        except Exception as e:
            errors.append(f"{name}: {e}")
            _reset()
    _last_err = "; ".join(errors) or "no GPIO backend"
    print(f"[buzzer] unavailable ({_last_err})", flush=True)
    return False


def _busy_wait_until(t_end: float) -> None:
    while time.monotonic() < t_end:
        pass


def _bitbang(freq_hz: float, ms: int) -> bool:
    """Busy-wait square wave — time.sleep cannot hit 2–4 kHz on the Pi."""
    if _write is None:
        return False
    half = 0.5 / max(200.0, float(freq_hz))
    end = time.monotonic() + max(0.02, ms / 1000.0)
    high = True
    nxt = time.monotonic()
    try:
        while time.monotonic() < end:
            _write(1 if high else 0)
            high = not high
            nxt += half
            _busy_wait_until(nxt)
        _write(0)
        return True
    except Exception as e:
        _last_err = str(e)
        print(f"[buzzer] bitbang fail: {e}", flush=True)
        try:
            _write(0)
        except Exception:
            pass
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
    # Cheap passive discs are loudest around 3–4 kHz
    freq = max(200.0, min(5000.0, float(freq_hz)))
    ms = max(20, min(2500, int(ms)))
    with _lock:
        if _lg_pwm and _gpio is not None and _chip is not None:
            if _lgpio_pwm(freq, ms):
                return True
        if _pwm is not None and _backend == "RPi.GPIO":
            try:
                _pwm.ChangeFrequency(freq)
                _pwm.start(50.0)
                time.sleep(ms / 1000.0)
                _pwm.stop()
                if _write is not None:
                    _write(0)
                return True
            except Exception as e:
                print(f"[buzzer] PWM fail → bitbang ({e})", flush=True)
        return _bitbang(freq, ms)


def chirp(*, force: bool = False) -> bool:
    return tone(3200, 120, force=force)


def alert(*, force: bool = False) -> bool:
    ok = False
    for i, f in enumerate((2500, 3200, 4000)):
        if tone(f, 220, force=force):
            ok = True
        if i < 2:
            time.sleep(0.03)
    return ok


def nav_tick() -> bool:
    return tone(2800, 40)


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


def reopen() -> bool:
    """Drop and re-claim the GPIO (Debug → Sound test)."""
    return _setup(force=True)


def available() -> bool:
    return BUZZER_BCM is not None and _setup()


def status() -> str:
    if BUZZER_BCM is None:
        return "Piezo disabled"
    if not _ready:
        _setup()
    if _ready:
        how = "PWM" if (_pwm is not None or _lg_pwm) else "bitbang"
        chip = f" gpiochip{_chip_n}" if _chip_n >= 0 else ""
        return f"OK pin15 BCM{BUZZER_BCM} {how} ({_backend}{chip})"
    return f"Fail pin15 BCM{BUZZER_BCM}: {_last_err or 'unknown'}"


if __name__ == "__main__":
    print(status())
    print("alert", alert(force=True))
    print(status())
