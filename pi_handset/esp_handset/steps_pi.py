"""Pi-local pedometer via SW-520D (momentary tilt switch → GND, like a button)."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, List, Optional

from esp_handset import store
from esp_handset.hw_pins import STEPS_BCM

# SW-520D pulses are short — count edges, not long "settled" tilts.
_MIN_INTERVAL_S = 0.22

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
    """Watch BCM GPIO; count each brief close (SW-520D = momentary button)."""

    def __init__(self, bcm: int, on_step: Optional[Callable[[int], None]] = None):
        self.bcm = int(bcm)
        self.on_step = on_step
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._gpio: Any = None
        self._backend = ""
        self._chip = None
        self._pigpio_cb: Any = None
        self._was_closed = False
        self._last_step_t = 0.0
        self._count_lock = threading.Lock()
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

    def _count_edge(self) -> None:
        with self._count_lock:
            self.edges += 1
            if not _pi_counting_enabled():
                return
            now = time.monotonic()
            if self._last_step_t and (now - self._last_step_t) < _MIN_INTERVAL_S:
                return
            self._last_step_t = now
            self.steps += 1
            total = record_step(1)
        if self.on_step:
            try:
                self.on_step(total)
            except Exception:
                pass

    def _pigpio_edge(self, _gpio: int, level: int, _tick: int) -> None:
        # pigpio: 0=falling (→GND), 1=rising (→pull-up)
        if level not in (0, 1):
            return
        if _active_low():
            if level != 0:
                return
        elif level != 1:
            return
        self._count_edge()

    def start(self) -> bool:
        if self.ok and (
            self._pigpio_cb is not None
            or (self._thread and self._thread.is_alive())
        ):
            return True
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

    def _finish_start_poll(self) -> bool:
        try:
            self._was_closed = self._is_closed(self._read())
        except Exception as e:
            self.error = str(e)
            self.ok = False
            return False
        self._last_step_t = 0.0
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, name="digi-steps", daemon=True)
        self._thread.start()
        print(
            f"[steps] poll BCM{self.bcm} via {self._backend} "
            f"(closed={int(self._was_closed)}, button edges)",
            flush=True,
        )
        self.ok = True
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
            self._pigpio_cb = pi.callback(self.bcm, pigpio.EITHER_EDGE, self._pigpio_edge)
            self.error = ""
            self.ok = True
            closed = self._is_closed(pi.read(self.bcm))
            print(
                f"[steps] irq BCM{self.bcm} via pigpio "
                f"(closed={int(closed)}, button edges)",
                flush=True,
            )
            return True
        except Exception as e:
            self.error = str(e)
            if pi is not None:
                try:
                    pi.stop()
                except Exception:
                    pass
            self._gpio = None
            self._pigpio_cb = None
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
                return self._finish_start_poll()
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
            return self._finish_start_poll()
        except Exception as e:
            self.ok = False
            self.error = str(e)
            print(f"[steps] GPIO {self.bcm} failed: {e}", flush=True)
            return False

    def stop(self) -> None:
        self._stop.set()
        if self._pigpio_cb is not None:
            try:
                self._pigpio_cb.cancel()
            except Exception:
                pass
            self._pigpio_cb = None
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

    def _poll_loop(self) -> None:
        """Fast poll for backends without hardware edge IRQ."""
        while not self._stop.is_set():
            try:
                closed = self._is_closed(self._read())
            except Exception:
                time.sleep(0.01)
                continue
            if closed != self._was_closed:
                self._was_closed = closed
                # Count on press (→ closed), same as pigpio falling edge.
                if closed:
                    self._count_edge()
            time.sleep(0.002)


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
            if on_step:
                _monitor.on_step = on_step
            return _monitor
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
    if _monitor.steps > 0:
        return f"Counting · { _monitor.steps } steps today"
    if _monitor.edges > 0:
        return f"Edges seen · {_monitor.edges} (shake harder?)"
    return "Shake — Probe shows edges/steps"
