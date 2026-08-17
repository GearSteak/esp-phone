"""Persisted Digivice call history."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from esp_handset import store

LOG_NAME = "call_log.json"
_MAX = 200


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def list_entries() -> List[dict]:
    raw = store.load(LOG_NAME, [])
    if not isinstance(raw, list):
        return []
    return [e for e in raw if isinstance(e, dict)]


def get(entry_id: str) -> Optional[dict]:
    for e in list_entries():
        if str(e.get("id") or "") == entry_id:
            return e
    return None


def start(
    *,
    direction: str,
    number: str,
    name: str = "",
    status: str = "dialing",
) -> dict:
    """Create a new log row and return it (includes id)."""
    entry = {
        "id": uuid4().hex[:12],
        "dir": "in" if direction == "in" else "out",
        "number": str(number or "").strip(),
        "name": str(name or "").strip(),
        "at": _now(),
        "ended_at": "",
        "status": status,  # dialing|ringing|answered|no_answer|canceled|declined|missed|busy|failed|ended
        "duration_s": 0,
        "answered": False,
    }
    log = list_entries()
    log.insert(0, entry)
    store.save(LOG_NAME, log[:_MAX])
    return entry


def update(entry_id: str, **fields: Any) -> Optional[dict]:
    if not entry_id:
        return None
    log = list_entries()
    for i, e in enumerate(log):
        if str(e.get("id") or "") != entry_id:
            continue
        e = dict(e)
        for k, v in fields.items():
            if v is not None:
                e[k] = v
        if e.get("status") == "answered":
            e["answered"] = True
        log[i] = e
        store.save(LOG_NAME, log[:_MAX])
        return e
    return None


def finish(
    entry_id: str,
    *,
    status: str,
    duration_s: int = 0,
) -> Optional[dict]:
    return update(
        entry_id,
        status=status,
        duration_s=max(0, int(duration_s)),
        ended_at=_now(),
        answered=(status == "answered" or (status == "ended" and duration_s > 0)),
    )


def display_status(entry: Dict[str, Any]) -> str:
    st = str(entry.get("status") or "")
    if not st:
        # Legacy rows from older Digivice (dir/number/at only)
        return "Placed" if entry.get("dir") == "out" else "Received"
    if entry.get("answered") and st in ("", "ended", "answered"):
        dur = int(entry.get("duration_s") or 0)
        if dur > 0:
            m, s = divmod(dur, 60)
            return f"Answered · {m}:{s:02d}"
        return "Answered"
    return {
        "dialing": "Dialing…",
        "ringing": "Ringing…",
        "answered": "Answered",
        "no_answer": "No answer",
        "canceled": "Canceled",
        "declined": "Declined",
        "missed": "Missed",
        "busy": "Busy",
        "failed": "Failed",
        "ended": "Ended",
    }.get(st, st or "Unknown")


def display_when(entry: Dict[str, Any]) -> str:
    at = str(entry.get("at") or "")
    if "T" in at:
        try:
            dt = datetime.fromisoformat(at)
            return dt.strftime("%a %b %d · %H:%M")
        except ValueError:
            return at[:16].replace("T", " ")
    return at[:19]
