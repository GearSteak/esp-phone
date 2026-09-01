"""Pi-local pedometer via SW-520D (or any tilt / vibration switch → GND)."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, List, Optional

from esp_handset import store
from esp_handset.hw_pins import STEPS_BCM

# Match heltec step_tilt.cpp
_DEBOUNCE_S = 0.025
_MIN_INTERVAL_S = 0.28

_monitor: Optional["StepsMonitor"] = None
_lock = threading.Lock()


def _chip_candidates() -> List[int]:
    found: List[int] = []
    for p in sorted(Path("/dev").glob("gpiochip*")):
        try:
            found.append(int(p.name.replace("gpiochip", "")))
        except ValueError:
            continue
    order: List[int] = []
    for n in (0, 4, 5, *found):
        if n not in order:
            order.append(n)
    return order


def _active_low() -> bool:
    raw = (os.environ.get("DIGI_STEPS_ACTIVE_LOW") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _pi_counting_enabled() -> bool:
    return store.steps_source() != "heltec"


def monitor_ok() -> bool:
    return _monitor is not None and _monitor.ok


def record_step(n: int = 1) -> int:
    """Add steps for today. Returns new total."""
    st = store.steps_state()
    st["count"] = int(st.get("count") or 0) + max(0, int(n))
    store.save("steps.json", st)
    return int(st["count"])


class StepsMonitor:
    """Poll BCM GPIO; count settled tilt transitions."""

    def __init__(self, bcm: int, on_step: Optional[Callable[[int], None]] = None):
        self.bcm = int(bcm)
        self.on_step = on_step
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._gpio: Any = None
        self._backend = ""
        self._chip = None
        self._raw_closed = False
        self._stable_closed = False
        self._edge_t = 0.0
        self._last_step_t = 0.0
        self.ok = False
        self.error = ""
        self.edges = 0
        self.steps = 0

    def _is_closed(self, level: int) -> bool:
        if _active_low():
            return level == 0
        return level != 0

    def _read(self) -> int:
        if self._backend == "pigpio" and self._gpio is not None:
            return int(self._gpio.read(self.bcm))
        if self._backend == "RPi.GPIO" and self._gpio is not None:
            return int(self._gpio.input(self.bcm))
        if self._backend == "lgpio" and self._gpio is not None and self._chip is not None:
            return int(self._gpio.gpio_read(self._chip, self.bcm))
        raise RuntimeError("no gpio")

    def current_level(self) -> Optional[int]:
        try:
            return self._read()
        except Exception:
            return None

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return self.ok
        # pigpiod is already up for Heltec soft-UART — most reliable in-process.
        if self._try_start_pigpio():
            return True
        if self._try_start_lgpio():
            return True
        if self._try_start_rpi_gpio():
            return True
        print(
            f"[steps] all GPIO backends failed for BCM{self.bcm}: {self.error}",
            flush=True,
        )
        return False

    def _finish_start(self) -> bool:
        closed = self._is_closed(self._read())
        self._raw_closed = closed
        self._stable_closed = closed
        self._edge_t = time.monotonic()
        self._last_step_t = 0.0
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="digi-steps", daemon=True)
        self._thread.start()
        print(
            f"[steps] monitoring BCM{self.bcm} via {self._backend} "
            f"(closed={int(closed)}, active_low={_active_low()})",
            flush=True,
        )
        return True

    def _try_start_pigpio(self) -> bool:
        try:
            import pigpio  # type: ignore
        except ImportError:
            return False
        pi = None
        try:
            pi = pigpio.pi()
            if not pi.connected:
                self.error = "pigpiod not connected"
                return False
            pi.set_mode(self.bcm, pigpio.INPUT)
            pi.set_pull_up_down(self.bcm, pigpio.PUD_UP)
            self._gpio = pi
            self._backend = "pigpio"
            self._chip = None
            self.ok = True
            self.error = ""
            return self._finish_start()
        except Exception as e:
            self.error = str(e)
            if pi is not None:
                try:
                    pi.stop()
                except Exception:
                    pass
            return False

    def _try_start_lgpio(self) -> bool:
        try:
            import lgpio as mod  # type: ignore
        except ImportError:
            return False
        last = ""
        for n in _chip_candidates():
            chip = None
            try:
                chip = mod.gpiochip_open(n)
                mod.gpio_claim_input(chip, self.bcm, mod.SET_PULL_UP)
                self._chip = chip
                self._gpio = mod
                self._backend = "lgpio"
                self.ok = True
                self.error = ""
                return self._finish_start()
            except Exception as e:
                last = str(e)
                if chip is not None:
                    try:
                        mod.gpiochip_close(chip)
                    except Exception:
                        pass
        self.error = last or "lgpio open failed"
        return False

    def _try_start_rpi_gpio(self) -> bool:
        try:
            from esp_handset.gpio_util import get_gpio, last_error

            mod, backend = get_gpio()
            if mod is None or backend != "RPi.GPIO":
                raise RuntimeError(last_error() or "no RPi.GPIO backend")
            mod.setup(self.bcm, mod.IN, pull_up_down=mod.PUD_UP)
            self._gpio = mod
            self._backend = backend
            self._chip = None
            self.ok = True
            self.error = ""
            return self._finish_start()
        except Exception as e:
            self.ok = False
            self.error = str(e)
            print(f"[steps] GPIO {self.bcm} failed: {e}", flush=True)
            return False

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.6)
        if self._backend == "pigpio" and self._gpio is not None:
            try:
                self._gpio.stop()
            except Exception:
                pass
        if self._backend == "lgpio" and self._gpio is not None and self._chip is not None:
            try:
                self._gpio.gpio_free(self._chip, self.bcm)
            except Exception:
                pass
            try:
                self._gpio.gpiochip_close(self._chip)
            except Exception:
                pass
        self._chip = None
        self._gpio = None
        self._backend = ""
        self.ok = False

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                closed = self._is_closed(self._read())
            except Exception:
                time.sleep(0.05)
                continue
            now = time.monotonic()
            if closed != self._raw_closed:
                self._raw_closed = closed
                self._edge_t = now
            if (now - self._edge_t) < _DEBOUNCE_S:
                time.sleep(0.005)
                continue
            if closed == self._stable_closed:
                time.sleep(0.005)
                continue
            self._stable_closed = closed
            self.edges += 1
            if self._last_step_t != 0.0 and (now - self._last_step_t) < _MIN_INTERVAL_S:
                time.sleep(0.005)
                continue
            if not _pi_counting_enabled():
                time.sleep(0.005)
                continue
            self._last_step_t = now
            self.steps += 1
            total = record_step(1)
            if self.on_step:
                try:
                    self.on_step(total)
                except Exception:
                    pass
            time.sleep(0.005)


def start_monitor(on_step: Optional[Callable[[int], None]] = None) -> Optional[StepsMonitor]:
    """Start the process-wide step monitor (idempotent; retries after failure)."""
    global _monitor
    with _lock:
        if not _pi_counting_enabled():
            return None
        if STEPS_BCM is None:
            print("[steps] disabled (DIGI_STEPS_BCM=off)", flush=True)
            return None
        if _monitor is not None and _monitor.ok:
            alive = _monitor._thread is not None and _monitor._thread.is_alive()
            if alive:
                if on_step:
                    _monitor.on_step = on_step
                return _monitor
            _monitor.stop()
            _monitor = None
        if _monitor is not None:
            _monitor.stop()
            _monitor = None
        mon = StepsMonitor(STEPS_BCM, on_step=on_step)
        if mon.start():
            _monitor = mon
            return mon
        _monitor = mon
        return None


def restart_monitor(on_step: Optional[Callable[[int], None]] = None) -> Optional[StepsMonitor]:
    """Stop any existing monitor and open a fresh one (Probe button)."""
    global _monitor
    with _lock:
        if _monitor is not None:
            _monitor.stop()
            _monitor = None
    return start_monitor(on_step=on_step)


def monitor_status() -> str:
    """Technical status for Probe / logs."""
    if STEPS_BCM is None:
        return "Steps GPIO disabled"
    if _monitor is None:
        return f"Not started (BCM{STEPS_BCM})"
    if _monitor.ok:
        lvl = _monitor.current_level()
        closed = "?"
        if lvl is not None:
            closed = "1" if _monitor._is_closed(lvl) else "0"
        return (
            f"OK BCM{_monitor.bcm} {_monitor._backend} "
            f"lvl={lvl} closed={closed} edges={_monitor.edges} steps={_monitor.steps}"
        )
    return f"Error: {_monitor.error or 'unknown'}"


def user_status() -> str:
    """Short status for the Steps screen (not GPIO debug)."""
    if STEPS_BCM is None:
        return "Tilt sensor disabled in config"
    if _monitor is None:
        return f"Starting sensor (pin {STEPS_BCM})…"
    if not _monitor.ok:
        err = (_monitor.error or "could not open GPIO").strip()
        return f"Sensor error: {err[:56]}"
    lvl = _monitor.current_level()
    if lvl is not None and _monitor._is_closed(lvl):
        return "Tilt detected · shake to count"
    if _monitor.edges > 0:
        return f"Counting · {_monitor.edges} transitions"
    return "Shake sensor — watch edges on Probe"
