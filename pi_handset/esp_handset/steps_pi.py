"""Pi-local pedometer via SW-520D (or any tilt / vibration switch → GND)."""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from esp_handset import store
from esp_handset.hw_pins import STEPS_BCM

# SW-520D chatters — ignore edges closer than this
_MIN_INTERVAL_S = 0.28

_monitor: Optional["StepsMonitor"] = None
_lock = threading.Lock()


def record_step(n: int = 1) -> int:
    """Add steps for today. Returns new total."""
    st = store.steps_state()
    st["count"] = int(st.get("count") or 0) + max(0, int(n))
    store.save("steps.json", st)
    return int(st["count"])


class StepsMonitor:
    """Poll a pull-up GPIO; count open/close transitions as steps."""

    def __init__(self, bcm: int, on_step: Optional[Callable[[int], None]] = None):
        self.bcm = int(bcm)
        self.on_step = on_step
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._gpio = None
        self._last_level: Optional[int] = None
        self._last_t = 0.0
        self.ok = False
        self.error = ""

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return self.ok
        try:
            import RPi.GPIO as GPIO  # type: ignore

            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.bcm, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            self._gpio = GPIO
            self._last_level = int(GPIO.input(self.bcm))
            self.ok = True
            self.error = ""
        except Exception as e:
            self.ok = False
            self.error = str(e)
            print(f"[steps] GPIO {self.bcm} failed: {e}", flush=True)
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="digi-steps", daemon=True)
        self._thread.start()
        print(f"[steps] monitoring BCM{self.bcm} (tilt → GND)", flush=True)
        return True

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        gpio = self._gpio
        if gpio is None:
            return
        while not self._stop.is_set():
            try:
                level = int(gpio.input(self.bcm))
            except Exception:
                time.sleep(0.05)
                continue
            if self._last_level is None:
                self._last_level = level
                time.sleep(0.02)
                continue
            if level != self._last_level:
                now = time.monotonic()
                if now - self._last_t >= _MIN_INTERVAL_S:
                    total = record_step(1)
                    self._last_t = now
                    if self.on_step:
                        try:
                            self.on_step(total)
                        except Exception:
                            pass
                self._last_level = level
            time.sleep(0.015)


def start_monitor(on_step: Optional[Callable[[int], None]] = None) -> Optional[StepsMonitor]:
    """Start the process-wide step monitor (idempotent)."""
    global _monitor
    with _lock:
        if STEPS_BCM is None:
            print("[steps] disabled (DIGI_STEPS_BCM=off)", flush=True)
            return None
        if _monitor is not None and _monitor.ok:
            if on_step and _monitor.on_step is None:
                _monitor.on_step = on_step
            return _monitor
        mon = StepsMonitor(STEPS_BCM, on_step=on_step)
        if mon.start():
            _monitor = mon
            return mon
        return None


def monitor_status() -> str:
    if STEPS_BCM is None:
        return "Steps GPIO disabled"
    if _monitor is None:
        return f"Not started (BCM{STEPS_BCM})"
    if _monitor.ok:
        return f"Listening BCM{_monitor.bcm}"
    return f"Error: {_monitor.error or 'unknown'}"
