"""Shared JSON stores for handset features."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, List, Optional

DATA = Path.home() / ".esp-handset"
BOOKS = Path.home() / "Books"
AUDIOBOOKS = Path.home() / "Audiobooks"
MUSIC = Path.home() / "Music"
VIDEOS = Path.home() / "Videos"
VOICE = Path.home() / "VoiceNotes"


def ensure() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    for p in (BOOKS, AUDIOBOOKS, MUSIC, VIDEOS, VOICE):
        p.mkdir(parents=True, exist_ok=True)


def load(name: str, default: Any) -> Any:
    ensure()
    path = DATA / name
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return default
    return default


def save(name: str, data: Any) -> None:
    ensure()
    (DATA / name).write_text(json.dumps(data, indent=2))


def _vibe_for_notif(kind: str) -> None:
    """Vibration motor on incoming notifications (respects sounds.json / Silent)."""
    k = (kind or "info").strip().lower()
    # Alarms/timers use play_alert() in handset_app (longer pattern + CM108 fallback).
    if k in ("alarm", "timer"):
        return
    # Settings/security toasts are confirmations, not inbox alerts.
    if k in ("settings", "security"):
        return
    try:
        from esp_handset.vibe import vibe_async

        if k in ("call", "sos"):
            vibe_async("alert")
        else:
            vibe_async("chirp")
    except Exception:
        pass


def push_notif(
    title: str,
    body: str,
    kind: str = "info",
    *,
    toast: bool = True,
    vibe: Optional[bool] = None,
) -> None:
    items: List[dict] = load("notifs.json", [])
    from datetime import datetime

    items.insert(
        0,
        {
            "title": title,
            "body": body,
            "kind": kind,
            "at": datetime.now().isoformat(timespec="seconds"),
            "read": False,
        },
    )
    save("notifs.json", items[:200])
    # Optional Heltec ST7735 panel (if wired)
    esp_cb = globals().get("_esp_notif_cb")
    if callable(esp_cb):
        try:
            esp_cb(title, body, kind)
        except Exception:
            pass
    should_vibe = vibe if vibe is not None else True
    if should_vibe:
        _vibe_for_notif(kind)
    # Digivice on-screen toast (always when requested — even if ESP also got it)
    if toast:
        cb = globals().get("_toast_cb")
        if callable(cb):
            try:
                cb(title, body, kind)
            except Exception:
                pass


def set_toast_handler(cb) -> None:
    """Register Digivice UI toast. cb(title, body, kind)."""
    globals()["_toast_cb"] = cb


def set_esp_notif_handler(cb) -> None:
    """Register ESP bridge notify panel. cb(title, body, kind)."""
    globals()["_esp_notif_cb"] = cb


def set_esp_clear_handler(cb) -> None:
    """Register ESP bridge clear notify panel. cb() -> None."""
    globals()["_esp_clear_cb"] = cb


def clear_esp_notif() -> None:
    """Clear Heltec ST7735 notify panel (if bridge wired)."""
    cb = globals().get("_esp_clear_cb")
    if callable(cb):
        try:
            cb()
        except Exception:
            pass


def push_heltec_notif(
    title: str,
    body: str,
    kind: str = "info",
    *,
    toast: bool = False,
    vibe: bool = True,
) -> None:
    """Push to Heltec panel (optional Digivice toast + vibration)."""
    push_notif(title, body, kind, toast=toast, vibe=vibe)


def steps_source() -> str:
    """pi | heltec | auto — auto prefers Pi GPIO when the monitor is running."""
    raw = (os.environ.get("DIGI_STEPS_SOURCE") or "auto").strip().lower()
    if raw in ("pi", "heltec", "auto"):
        return raw
    return "auto"


def pi_steps_active() -> bool:
    """True when the Pi tilt monitor is counting (not Heltec-only)."""
    if steps_source() == "heltec":
        return False
    try:
        from esp_handset.steps_pi import monitor_ok

        return monitor_ok()
    except Exception:
        return steps_source() == "pi"


def steps_state() -> dict:
    """Daily step total (Pi GPIO and/or Heltec STEPS UART sync)."""
    from datetime import date

    today = date.today().isoformat()
    st = load("steps.json", {"date": today, "count": 0, "esp": 0})
    if st.get("date") != today:
        st = {"date": today, "count": 0, "esp": 0}
        save("steps.json", st)
    st.setdefault("esp", 0)
    return st


def apply_esp_steps(esp_count: int) -> int:
    """Merge Heltec session counter into today's Digivice total."""
    if steps_source() == "pi":
        return int(steps_state().get("count") or 0)
    if steps_source() == "auto" and pi_steps_active():
        return int(steps_state().get("count") or 0)
    st = steps_state()
    prev_esp = int(st.get("esp") or 0)
    esp_count = max(0, int(esp_count))
    if esp_count >= prev_esp:
        st["count"] = int(st.get("count") or 0) + (esp_count - prev_esp)
    else:
        # ESP rebooted / STEPS RESET — treat as new session delta
        st["count"] = int(st.get("count") or 0) + esp_count
    st["esp"] = esp_count
    save("steps.json", st)
    return int(st["count"])


def add_steps(n: int = 1) -> int:
    """Add steps locally (Pi tilt sensor or UI +1)."""
    from esp_handset.steps_pi import record_step

    return record_step(n)


def reset_steps_today() -> None:
    from datetime import date

    save("steps.json", {"date": date.today().isoformat(), "count": 0, "esp": 0})
