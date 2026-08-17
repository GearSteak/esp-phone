"""Linphone helpers for Digivice voice calls (via linphonecsh)."""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional


def available() -> bool:
    return shutil.which("linphonecsh") is not None


def _run(args: List[str], timeout: float = 3.0) -> str:
    try:
        r = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
    except Exception as e:
        return f"ERR {e}"


def dial(number: str) -> bool:
    num = (number or "").strip()
    if not num:
        return False
    # Prefer sip: URI if it already looks like one
    target = num if num.lower().startswith("sip:") else num
    out = _run(["linphonecsh", "dial", target])
    if "ERR" in out and "not found" in out.lower():
        return False
    return True


def hangup() -> None:
    # Newer / older CLI names
    _run(["linphonecsh", "generic", "terminate"])
    _run(["linphonecsh", "hangup"])


def answer() -> None:
    _run(["linphonecsh", "generic", "answer"])
    # Fallback: answer first incoming call id if listed
    info = poll()
    if info.call_id is not None and info.phase == "incoming":
        _run(["linphonecsh", "generic", f"answer {info.call_id}"])


@dataclass
class CallInfo:
    """Best-effort snapshot of linphonec call list."""

    raw: str = ""
    phase: str = "idle"  # idle | dialing | ringing | early | active | incoming | ending | error
    call_id: Optional[int] = None
    remote: str = ""
    state: str = ""


_STATE_MAP = (
    ("IncomingReceived", "incoming"),
    ("IncomingEarlyMedia", "incoming"),
    ("OutgoingInit", "dialing"),
    ("OutgoingProgress", "dialing"),
    ("OutgoingRinging", "ringing"),
    ("OutgoingEarlyMedia", "early"),
    ("Connected", "active"),
    ("StreamsRunning", "active"),
    ("Paused", "active"),
    ("Pausing", "active"),
    ("Resuming", "active"),
    ("PausedByRemote", "active"),
    ("Error", "error"),
    ("End", "ending"),
    ("Released", "ending"),
)


def poll() -> CallInfo:
    """Parse `linphonecsh generic calls` (and status call as fallback)."""
    raw = _run(["linphonecsh", "generic", "calls"])
    if not raw or raw.startswith("ERR"):
        raw2 = _run(["linphonecsh", "status", "call"])
        if raw2 and not raw2.startswith("ERR"):
            raw = raw2

    info = CallInfo(raw=raw or "")
    if not raw or "No active call" in raw or "no call" in raw.lower():
        # Empty status call often means idle
        if not raw or len(raw) < 3:
            return info
        if re.search(r"(?i)no\s+(active\s+)?call", raw):
            return info

    phase = "idle"
    state = ""
    for token, mapped in _STATE_MAP:
        if token in raw:
            phase = mapped
            state = token
            # Prefer active over ringing if both somehow present
            if mapped == "active":
                break

    # If we only got a sip URI from `status call`, treat as active/unknown
    if phase == "idle" and ("sip:" in raw.lower() or "@" in raw):
        phase = "active"
        state = "status_call"

    m = re.search(r"(?m)^\s*(\d+)\s+", raw)
    if m:
        try:
            info.call_id = int(m.group(1))
        except ValueError:
            pass

    sip = re.search(r"(sip:[^\s|;]+)", raw, re.I)
    if sip:
        info.remote = sip.group(1)
    else:
        # bare number in calls dump
        num = re.search(r"(?i)(?:to|with|from)\s+(\+?\d[\d\s\-]+)", raw)
        if num:
            info.remote = num.group(1).strip()

    info.phase = phase
    info.state = state
    return info


def remote_number(remote: str) -> str:
    """Strip sip:user@host → user / digits."""
    s = (remote or "").strip()
    if not s:
        return ""
    if s.lower().startswith("sip:"):
        s = s[4:]
    if "@" in s:
        s = s.split("@", 1)[0]
    return s.strip()
