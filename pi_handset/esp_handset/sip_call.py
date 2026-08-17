"""Linphone helpers for Digivice voice calls (via linphonecsh)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

_ensure_lock = threading.Lock()
_ensured_once = False


def _bin() -> Optional[str]:
    found = shutil.which("linphonecsh")
    if found:
        return found
    for p in ("/usr/bin/linphonecsh", "/usr/local/bin/linphonecsh"):
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def available() -> bool:
    return _bin() is not None


def missing_hint() -> str:
    # Prefer last ensure status if present
    try:
        p = Path("/etc/esp-handset/linphone.status")
        if p.is_file():
            st = p.read_text(encoding="utf-8", errors="replace").strip()
            if st.startswith("missing") or not st.startswith("ok"):
                return "Linphone apt failed — see ensure log"
    except Exception:
        pass
    return "Linphone missing — SSH: sudo digivice-ensure-linphone"


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
    except subprocess.TimeoutExpired:
        return "ERR timeout"
    except Exception as e:
        return f"ERR {e}"


def _sip_env() -> Dict[str, str]:
    vals: Dict[str, str] = {}
    candidates = [
        Path.home() / ".esp-handset" / "sip.env",
        Path("/etc/esp-handset/sip.env"),
    ]
    try:
        from esp_handset import store

        candidates.insert(0, store.DATA / "sip.env")
    except Exception:
        pass
    for path in candidates:
        try:
            if not path.is_file() or not os.access(path, os.R_OK):
                continue
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip()
            if vals.get("SIP_USER") and vals.get("SIP_SERVER"):
                break
        except OSError:
            continue
    return vals


def ensure() -> str:
    """Start linphonec daemon + register SIP. '' if OK, else short UI hint.

    Never runs apt — that freezes Digivice. Package install is apply-update only.
    """
    exe = _bin()
    if not exe:
        return missing_hint()
    try:
        st = _run([exe, "status", "register"], timeout=2.5)
        dead = (
            not st
            or st.startswith("ERR")
            or re.search(
                r"(?i)no running|not running|could not|unable|failed to connect", st
            )
        )
        if dead:
            _run([exe, "init"], timeout=4.0)
            st = _run([exe, "status", "register"], timeout=2.5)
            if st.startswith("ERR") and re.search(r"(?i)no running|not running", st):
                return "Linphone daemon failed to start"
        env = _sip_env()
        user = (env.get("SIP_USER") or "").strip()
        server = (env.get("SIP_SERVER") or "").strip()
        password = (env.get("SIP_PASS") or "").strip()
        if user and server and password:
            if f"{user}@{server}" not in st and "registered" not in st.lower():
                _run(
                    [exe, "register", f"sip:{user}@{server}", server, password],
                    timeout=8.0,
                )
        elif not user or not password:
            return "Set SIP in Settings → Accounts"
        return ""
    except Exception as e:
        return f"SIP error: {e}"


def ensure_async() -> None:
    """Background init/register — safe from Qt main thread."""
    global _ensured_once

    def work() -> None:
        global _ensured_once
        with _ensure_lock:
            if _ensured_once and available():
                # Still poke register lightly
                try:
                    ensure()
                except Exception:
                    pass
                return
            try:
                hint = ensure()
                _ensured_once = True
                if hint:
                    print(f"[sip_call] ensure: {hint}", flush=True)
                else:
                    print("[sip_call] linphone ready", flush=True)
            except Exception as e:
                print(f"[sip_call] ensure failed ({e})", flush=True)

    threading.Thread(target=work, name="sip-ensure", daemon=True).start()


def dial(number: str) -> bool:
    num = (number or "").strip()
    if not num:
        return False
    exe = _bin()
    if not exe:
        return False
    # Quick daemon wake (no apt)
    ensure()
    target = num if num.lower().startswith("sip:") else num
    out = _run([exe, "dial", target], timeout=5.0)
    if re.search(r"(?i)no running|failed to connect", out):
        _run([exe, "init"], timeout=4.0)
        out = _run([exe, "dial", target], timeout=5.0)
    if "ERR" in out and "not found" in out.lower():
        return False
    return True


def hangup() -> None:
    exe = _bin()
    if not exe:
        return
    _run([exe, "generic", "terminate"], timeout=2.0)
    _run([exe, "hangup"], timeout=2.0)


def answer() -> None:
    exe = _bin()
    if not exe:
        return
    _run([exe, "generic", "answer"], timeout=2.0)
    info = poll()
    if info.call_id is not None and info.phase == "incoming":
        _run([exe, "generic", f"answer {info.call_id}"], timeout=2.0)


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
    exe = _bin()
    if not exe:
        return CallInfo()
    raw = _run([exe, "generic", "calls"], timeout=2.0)
    if not raw or raw.startswith("ERR"):
        raw2 = _run([exe, "status", "call"], timeout=2.0)
        if raw2 and not raw2.startswith("ERR"):
            raw = raw2

    info = CallInfo(raw=raw or "")
    if not raw or "No active call" in raw or "no call" in raw.lower():
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
            if mapped == "active":
                break

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
