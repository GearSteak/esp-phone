"""Pi-local pedometer via SW-520D on BCM17 (momentary switch → GND).

Counted in digi-buttons-inputd (same GPIO stack as the hard buttons).
This module reads/writes the user's steps store + debug file for the UI.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

from esp_handset import store
from esp_handset.hw_pins import STEPS_BCM

_monitor: Optional["_DaemonView"] = None
_lock = __import__("threading").Lock()


def user_data_dir() -> Path:
    """Handset user data (daemon runs as root — use DIGIVICE_USER_HOME)."""
    raw = (os.environ.get("DIGIVICE_USER_HOME") or "").strip()
    if raw:
        return Path(raw) / ".esp-handset"
    return store.DATA


def debug_path() -> Path:
    return user_data_dir() / "steps-debug.json"


def read_debug() -> dict:
    try:
        if debug_path().exists():
            return json.loads(debug_path().read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def write_debug(**fields: Any) -> None:
    data = dict(read_debug())
    data.update(fields)
    data["at"] = time.time()
    p = debug_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def daemon_active(max_age_s: float = 6.0) -> bool:
    d = read_debug()
    if d.get("source") != "buttons_inputd":
        return False
    at = float(d.get("at") or 0)
    return at > 0 and (time.time() - at) < max_age_s


def monitor_ok() -> bool:
    return daemon_active() or (_monitor is not None and _monitor.ok)


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
    return int(st["count"])


class _DaemonView:
    """UI-facing view of the buttons-inputd step counter."""

    ok = True
    error = ""

    def __init__(self, bcm: int, on_step: Optional[Callable[[int], None]] = None):
        self.bcm = bcm
        self.on_step = on_step
        self._backend = "buttons_inputd"

    @property
    def edges(self) -> int:
        return int(read_debug().get("edges") or 0)

    @property
    def steps(self) -> int:
        return int(read_debug().get("session_steps") or 0)

    def current_level(self) -> Optional[int]:
        lvl = read_debug().get("level")
        return int(lvl) if lvl is not None else None

    def _is_closed(self, level: int) -> bool:
        raw = (os.environ.get("DIGI_STEPS_ACTIVE_LOW") or "1").strip().lower()
        active_low = raw not in ("0", "false", "no", "off")
        return level == 0 if active_low else level != 0


def start_monitor(on_step: Optional[Callable[[int], None]] = None) -> Optional[_DaemonView]:
    """Attach UI callbacks; counting runs in digi-buttons-inputd."""
    global _monitor
    with _lock:
        if STEPS_BCM is None or store.steps_source() == "heltec":
            return None
        if _monitor is None:
            _monitor = _DaemonView(STEPS_BCM, on_step=on_step)
        elif on_step:
            _monitor.on_step = on_step
        if not daemon_active():
            write_debug(
                source="handset",
                bcm=STEPS_BCM,
                error="digi-buttons-inputd not reporting — run sudo digivice-ensure-buttons",
            )
        return _monitor


def restart_monitor(on_step: Optional[Callable[[int], None]] = None) -> Optional[_DaemonView]:
    write_debug(
        source="handset",
        bcm=STEPS_BCM,
        note="probe requested — shake sensor; restart buttons daemon if stale",
    )
    return start_monitor(on_step=on_step)


def monitor_status() -> str:
    if STEPS_BCM is None:
        return "Steps GPIO disabled"
    d = read_debug()
    if not d:
        return f"BCM{STEPS_BCM} · no daemon data (sudo digivice-ensure-buttons)"
    age = time.time() - float(d.get("at") or 0)
    lvl = d.get("level", "?")
    pressed = d.get("pressed", "?")
    return (
        f"{d.get('source', '?')} BCM{d.get('bcm', STEPS_BCM)} "
        f"lvl={lvl} pressed={pressed} edges={d.get('edges', 0)} "
        f"steps={d.get('session_steps', 0)} age={age:.1f}s"
        + (f" err={d['error']}" if d.get("error") else "")
    )


def user_status() -> str:
    if STEPS_BCM is None:
        return "Tilt sensor disabled"
    if not daemon_active():
        return "Buttons daemon offline — sudo digivice-ensure-buttons"
    d = read_debug()
    if d.get("error"):
        return str(d["error"])[:72]
    if int(d.get("session_steps") or 0) > 0:
        return f"Counting · {d.get('session_steps')} from sensor"
    if int(d.get("edges") or 0) > 0:
        return f"Edges {d.get('edges')} — check refractory"
    if d.get("pressed"):
        return "Sensor pressed now"
    return "Shake — watch edges below"
