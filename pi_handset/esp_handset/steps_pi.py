"""Pi-local pedometer via SW-520D on BCM17 (momentary switch → GND).

Counted inside handset_app (same GPIO stack as ST7789). The root buttons
daemon cannot reliably read this pin on all Pi builds.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, List, Optional

from esp_handset import store
from esp_handset.hw_pins import STEPS_BCM

_RUN_DEBUG = Path("/run/digivice/steps-debug.json")
_BURST = max(1, int(os.environ.get("DIGI_STEPS_BURST", "64")))
_MIN_INTERVAL_S = float(os.environ.get("DIGI_STEPS_REFRACTORY", "0.07"))
_monitor: Optional["StepsMonitor"] = None
_lock = threading.Lock()


def _active_low() -> bool:
    raw = (os.environ.get("DIGI_STEPS_ACTIVE_LOW") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _pressed(level: int) -> bool:
    return level == 0 if _active_low() else level != 0


def _gui_home() -> Path:
    try:
        raw = Path("/etc/esp-handset/gui-home").read_text(encoding="utf-8").strip()
        if raw:
            return Path(raw)
    except OSError:
        pass
    raw = (os.environ.get("DIGIVICE_USER_HOME") or os.environ.get("HOME") or "").strip()
    if raw and raw != "/root":
        return Path(raw)
    return Path.home()


def user_data_dir() -> Path:
    return _gui_home() / ".esp-handset"


def debug_path() -> Path:
    return _RUN_DEBUG


def _debug_candidates() -> list[Path]:
    paths = [_RUN_DEBUG, user_data_dir() / "steps-debug.json"]
    for name in ("pi", "isaac", "gearsteak"):
        paths.append(Path(f"/home/{name}/.esp-handset/steps-debug.json"))
    paths.append(Path("/root/.esp-handset/steps-debug.json"))
    out: list[Path] = []
    for p in paths:
        if p not in out:
            out.append(p)
    return out


def read_debug() -> dict:
    best: dict = {}
    best_at = 0.0
    for path in _debug_candidates():
        try:
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            at = float(data.get("at") or 0)
            if at >= best_at:
                best_at = at
                best = data
        except Exception:
            continue
    return best


def write_debug(**fields: Any) -> None:
    data = dict(read_debug())
    data.update(fields)
    data["at"] = time.time()
    path = debug_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.chmod(path, 0o644)
    except OSError:
        path = user_data_dir() / "steps-debug.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _pi_counting_enabled() -> bool:
    return store.steps_source() != "heltec"


def sensor_active(max_age_s: float = 8.0) -> bool:
    mon = _monitor
    if mon is not None and mon.ok:
        t = mon._thread
        if t is not None and t.is_alive():
            return True
    d = read_debug()
    if d.get("source") not in ("handset", "buttons_inputd"):
        return False
    at = float(d.get("at") or 0)
    return at > 0 and (time.time() - at) < max_age_s


def daemon_active(max_age_s: float = 8.0) -> bool:
    """Back-compat name — True when the local sensor thread or debug is live."""
    return sensor_active(max_age_s)


def monitor_ok() -> bool:
    return sensor_active()


def record_step(n: int = 1) -> int:
    """Add steps for today. Returns new total."""
    from datetime import date

    data = user_data_dir()
    data.mkdir(parents=True, exist_ok=True)
    path = data / "steps.json"
    today = date.today().isoformat()
    try:
        st = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        st = {"date": today, "count": 0, "esp": 0}
    if st.get("date") != today:
        st = {"date": today, "count": 0, "esp": 0}
    st["count"] = int(st.get("count") or 0) + max(0, int(n))
    path.write_text(json.dumps(st, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o644)
    except OSError:
        pass
    return int(st["count"])


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


class StepsMonitor:
    """Burst-poll BCM17 in the Digivice process (shares gpio_util with LCD)."""

    def __init__(self, bcm: int, on_step: Optional[Callable[[int], None]] = None):
        self.bcm = int(bcm)
        self.on_step = on_step
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._gpio: Any = None
        self.backend = "none"
        self._chip: Optional[int] = None
        self.raw_level = 1
        self.prev_pressed = False
        self.edges = 0
        self.toggles = 0
        self.session = 0
        self._last_t = 0.0
        self.ok = False
        self.error = ""

    def _read(self) -> int:
        if self.backend == "RPi.GPIO" and self._gpio is not None:
            return int(self._gpio.input(self.bcm))
        if self.backend == "lgpio" and self._gpio is not None and self._chip is not None:
            return int(self._gpio.gpio_read(self._chip, self.bcm))
        raise RuntimeError("no gpio backend")

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return self.ok
        if self._try_rpi_gpio():
            return True
        if self._try_lgpio():
            return True
        print(
            f"[steps] all GPIO backends failed for BCM{self.bcm}: {self.error}",
            flush=True,
        )
        write_debug(
            source="handset",
            bcm=self.bcm,
            level=-1,
            pressed=False,
            edges=0,
            toggles=0,
            session_steps=0,
            backend="none",
            init_error=self.error[:120],
        )
        return False

    def _finish_start(self) -> bool:
        self.raw_level = self._read()
        self.prev_pressed = _pressed(self.raw_level)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="digi-steps", daemon=True)
        self._thread.start()
        print(
            f"[steps] monitoring BCM{self.bcm} via {self.backend} "
            f"(lvl={self.raw_level}, tilt→GND)",
            flush=True,
        )
        self._publish_debug()
        return True

    def _try_rpi_gpio(self) -> bool:
        try:
            from esp_handset.gpio_util import get_gpio, last_error

            mod, backend = get_gpio()
            if mod is None or backend != "RPi.GPIO":
                raise RuntimeError(last_error() or "no RPi.GPIO backend")
            mod.setup(self.bcm, mod.IN, pull_up_down=mod.PUD_UP)
            self._gpio = mod
            self.backend = backend
            self._chip = None
            self.ok = True
            self.error = ""
            return self._finish_start()
        except Exception as e:
            self.ok = False
            self.error = str(e)
            return False

    def _try_lgpio(self) -> bool:
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
                self.backend = "lgpio"
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

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.8)
        if self.backend == "lgpio" and self._gpio is not None and self._chip is not None:
            try:
                self._gpio.gpio_free(self._chip, self.bcm)
            except Exception:
                pass
            try:
                self._gpio.gpiochip_close(self._chip)
            except Exception:
                pass
        self._gpio = None
        self._chip = None
        self.backend = "none"
        self.ok = False

    def _publish_debug(self) -> None:
        write_debug(
            source="handset",
            bcm=self.bcm,
            level=int(self.raw_level),
            pressed=bool(self.prev_pressed),
            edges=int(self.edges),
            toggles=int(self.toggles),
            session_steps=int(self.session),
            backend=self.backend,
            init_error=self.error[:120] if self.error else None,
        )

    def _loop(self) -> None:
        while not self._stop.is_set():
            for _ in range(_BURST):
                if self._stop.is_set():
                    break
                try:
                    level = int(self._read())
                except Exception as e:
                    self.error = str(e)
                    time.sleep(0.05)
                    break
                if level != self.raw_level:
                    self.toggles += 1
                    self.raw_level = level
                pressed = _pressed(level)
                if pressed and not self.prev_pressed:
                    self.edges += 1
                    now = time.monotonic()
                    if (now - self._last_t) >= _MIN_INTERVAL_S:
                        self.session += 1
                        self._last_t = now
                        total = record_step(1)
                        if self.on_step:
                            try:
                                self.on_step(total)
                            except Exception:
                                pass
                self.prev_pressed = pressed
            self._publish_debug()
            time.sleep(0.002)


def start_monitor(on_step: Optional[Callable[[int], None]] = None) -> Optional[StepsMonitor]:
    """Start the in-process step monitor (idempotent; retries after failure)."""
    global _monitor
    with _lock:
        if not _pi_counting_enabled() or STEPS_BCM is None:
            return None
        if _monitor is not None and _monitor.ok:
            t = _monitor._thread
            if t is not None and t.is_alive():
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
        return mon


def restart_monitor(on_step: Optional[Callable[[int], None]] = None) -> Optional[StepsMonitor]:
    global _monitor
    with _lock:
        if _monitor is not None:
            _monitor.stop()
            _monitor = None
    return start_monitor(on_step=on_step)


def _live_debug() -> dict:
    mon = _monitor
    if mon is not None and mon.ok:
        return {
            "source": "handset",
            "bcm": mon.bcm,
            "backend": mon.backend,
            "level": mon.raw_level,
            "pressed": mon.prev_pressed,
            "toggles": mon.toggles,
            "edges": mon.edges,
            "session_steps": mon.session,
            "init_error": mon.error,
        }
    return read_debug()


def debug_panel_text() -> str:
    """Large-type lines for the 2\" LCD Steps screen."""
    if STEPS_BCM is None:
        return "Steps disabled"
    d = _live_debug()
    if sensor_active() or (d.get("source") == "handset" and _monitor and _monitor.ok):
        pressed = bool(d.get("pressed"))
        level = int(d.get("level") if d.get("level") is not None else 1)
        toggles = int(d.get("toggles") or 0)
        edges = int(d.get("edges") or 0)
        counted = int(d.get("session_steps") or 0)
        backend = str(d.get("backend") or "?")
        bcm = d.get("bcm", STEPS_BCM)
        sensor = "TILT!" if pressed else "open"
        err = (d.get("init_error") or "").strip()
        lines = [
            f"BCM{bcm} {backend}",
            f"Lvl: {level} ({sensor})",
            f"Toggles: {toggles}",
            f"Edges: {edges}",
            f"Counted: {counted}",
        ]
        if err:
            lines.append(f"Err: {err[:28]}")
        return "\n".join(lines)
    mon = _monitor
    if mon is not None and mon.error:
        return (
            "GPIO failed\n\n"
            f"{mon.error[:80]}\n\n"
            "Reboot Digivice"
        )
    age = time.time() - float(d.get("at") or 0) if d.get("at") else 999
    if d.get("source") in ("handset", "buttons_inputd") and age < 120:
        return (
            "Sensor paused?\n\n"
            f"Last seen {age:.0f}s ago\n\n"
            "Reboot Digivice"
        )
    return (
        "Step sensor\n"
        "OFFLINE\n\n"
        "Reboot Digivice"
    )


def monitor_status() -> str:
    if STEPS_BCM is None:
        return "Steps GPIO disabled"
    d = _live_debug()
    if not d:
        return f"BCM{STEPS_BCM} · not started"
    age = time.time() - float(d.get("at") or 0) if d.get("at") else 0.0
    return (
        f"{d.get('source', '?')} lvl={d.get('level', '?')} "
        f"edges={d.get('edges', 0)} steps={d.get('session_steps', 0)} "
        f"age={age:.1f}s"
    )


def user_status() -> str:
    if STEPS_BCM is None:
        return "Sensor disabled"
    mon = _monitor
    if mon is not None and not mon.ok and mon.error:
        return f"GPIO error: {mon.error[:40]}"
    if not sensor_active():
        return "Sensor offline"
    d = _live_debug()
    n = int(d.get("session_steps") or 0)
    if n > 0:
        return f"{n} from sensor"
    if d.get("pressed"):
        return "Tilt detected!"
    return "Ready — shake"
