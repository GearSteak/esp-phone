"""Pi-local pedometer via SW-520D on BCM17 (momentary switch → GND).

Counted in digi-buttons-inputd (same GPIO stack as the hard buttons).
This module reads/writes the user's steps store + shared debug file for the UI.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

from esp_handset import store
from esp_handset.hw_pins import STEPS_BCM

_RUN_DEBUG = Path("/run/digivice/steps-debug.json")
_monitor: Optional["_DaemonView"] = None
_lock = __import__("threading").Lock()


def _gui_home() -> Path:
    """Desktop user home — daemon runs as root."""
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
        # Fallback when /run not writable (dev machine)
        path = user_data_dir() / "steps-debug.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def daemon_active(max_age_s: float = 8.0) -> bool:
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
    try:
        os.chmod(path, 0o644)
    except OSError:
        pass
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
        return _monitor


def restart_monitor(on_step: Optional[Callable[[int], None]] = None) -> Optional[_DaemonView]:
    return start_monitor(on_step=on_step)


def debug_panel_text() -> str:
    """Large-type lines for the 2\" LCD Steps screen."""
    if STEPS_BCM is None:
        return "Steps disabled"
    if daemon_active():
        d = read_debug()
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
    d = read_debug()
    age = time.time() - float(d.get("at") or 0) if d.get("at") else 999
    if d.get("source") == "buttons_inputd" and age < 120:
        return (
            "Sensor paused?\n\n"
            f"Last seen {age:.0f}s ago\n\n"
            "Reboot Digivice\nor run ensure-buttons"
        )
    return (
        "Buttons daemon\n"
        "OFFLINE\n\n"
        "Settings → Update\n"
        "then reboot once"
    )


def monitor_status() -> str:
    if STEPS_BCM is None:
        return "Steps GPIO disabled"
    d = read_debug()
    if not d:
        return f"BCM{STEPS_BCM} · no daemon"
    age = time.time() - float(d.get("at") or 0)
    return (
        f"{d.get('source', '?')} lvl={d.get('level', '?')} "
        f"edges={d.get('edges', 0)} steps={d.get('session_steps', 0)} "
        f"age={age:.1f}s"
    )


def user_status() -> str:
    if STEPS_BCM is None:
        return "Sensor disabled"
    if not daemon_active():
        return "Daemon offline"
    d = read_debug()
    n = int(d.get("session_steps") or 0)
    if n > 0:
        return f"{n} from sensor"
    if d.get("pressed"):
        return "Tilt detected!"
    return "Ready — shake"
