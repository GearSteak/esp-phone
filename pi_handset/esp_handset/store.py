"""Shared JSON stores for handset features."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

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


def push_notif(
    title: str,
    body: str,
    kind: str = "info",
    *,
    toast: bool = True,
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
    # Digivice on-screen toast (always when requested — even if ESP also got it)
    if toast:
        cb = globals().get("_toast_cb")
        if callable(cb):
            try:
                cb(title, body, kind)
            except Exception:
                pass
        # Piezo for inbox-style alerts; alarms/timers use play_alert() separately
        if kind in ("sms", "call", "lora"):
            try:
                from esp_handset.buzzer import beep_async

                beep_async("chirp" if kind != "call" else "alert")
            except Exception:
                pass


def set_toast_handler(cb) -> None:
    """Register Digivice UI toast. cb(title, body, kind)."""
    globals()["_toast_cb"] = cb


def set_esp_notif_handler(cb) -> None:
    """Register ESP bridge notify panel. cb(title, body, kind)."""
    globals()["_esp_notif_cb"] = cb


def steps_state() -> dict:
    """Daily step count from Pi tilt GPIO (SW-520D), not Heltec."""
    from datetime import date

    today = date.today().isoformat()
    st = load("steps.json", {"date": today, "count": 0})
    if st.get("date") != today:
        st = {"date": today, "count": 0}
        save("steps.json", st)
    # Drop legacy Heltec session field if present
    if "esp" in st:
        st = {"date": st.get("date") or today, "count": int(st.get("count") or 0)}
        save("steps.json", st)
    return st


def apply_esp_steps(esp_count: int) -> int:
    """Deprecated Heltec path — ignored; returns current Pi total."""
    del esp_count
    return int(steps_state().get("count") or 0)


def add_steps(n: int = 1) -> int:
    """Add steps locally (Pi tilt sensor or UI +1)."""
    from esp_handset.steps_pi import record_step

    return record_step(n)


def reset_steps_today() -> None:
    from datetime import date

    save("steps.json", {"date": date.today().isoformat(), "count": 0})
