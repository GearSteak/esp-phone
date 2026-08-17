"""Linphone helpers for Digivice voice calls (via linphonecsh)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

_ensure_lock = threading.Lock()
_ensured_once = False
_bin_cache: Optional[str] = None
_WRAPPER = "/usr/local/bin/digivice-linphonecsh"
_BIN_HINTS = (
    Path("/etc/esp-handset/linphone.bin"),
    Path.home() / ".esp-handset" / "linphone.bin",
)


def _is_exe(path: str) -> bool:
    try:
        return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)
    except OSError:
        return False


def _exists(path: str) -> bool:
    try:
        return bool(path) and os.path.isfile(path)
    except OSError:
        return False


def _remember_bin(path: str) -> None:
    """Persist absolute path for next Digivice boot (user + system hint)."""
    for hint in _BIN_HINTS:
        try:
            hint.parent.mkdir(parents=True, exist_ok=True)
            hint.write_text(path + "\n", encoding="utf-8")
        except OSError:
            continue


def _locate_via_sudo() -> None:
    """Ask passwordless ensure to pin the binary (no apt if already installed)."""
    for cmd in (
        ["sudo", "-n", "/usr/local/bin/digivice-ensure-linphone", "--locate-only"],
        ["sudo", "-n", "digivice-ensure-linphone", "--locate-only"],
    ):
        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            return
        except Exception:
            continue


def _discover_bin() -> Optional[str]:
    """Find linphonecsh even when Digivice PATH is minimal."""
    # Prefer Digivice wrapper (always on handset PATH)
    if _is_exe(_WRAPPER) or _exists(_WRAPPER):
        return _WRAPPER

    for hint_path in _BIN_HINTS:
        try:
            if hint_path.is_file():
                hint = hint_path.read_text(encoding="utf-8", errors="replace").strip()
                if _exists(hint):
                    return hint
        except OSError:
            pass

    candidates: List[str] = []

    which = shutil.which("linphonecsh")
    if which:
        candidates.append(which)

    try:
        r = subprocess.run(
            ["bash", "-lc", "command -v linphonecsh"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        hit = (r.stdout or "").strip().splitlines()
        if hit and hit[0]:
            candidates.append(hit[0].strip())
    except Exception:
        pass

    for pkg in ("linphone-cli", "linphone-nogtk", "linphone"):
        try:
            r = subprocess.run(
                ["dpkg", "-L", pkg],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            if r.returncode != 0:
                continue
            for line in (r.stdout or "").splitlines():
                line = line.strip()
                if line.endswith("/linphonecsh"):
                    candidates.append(line)
        except Exception:
            continue

    home_bin = ""
    try:
        home_bin = str(Path.home() / ".local" / "bin" / "linphonecsh")
    except Exception:
        home_bin = ""

    candidates.extend(
        [
            "/usr/bin/linphonecsh",
            "/usr/local/bin/linphonecsh",
            "/bin/linphonecsh",
            home_bin,
            "/home/pi/.local/bin/linphonecsh",
        ]
    )

    seen = set()
    for p in candidates:
        if not p or p in seen:
            continue
        seen.add(p)
        if "digivice-linphonecsh" in p:
            continue
        if _is_exe(p) or _exists(p):
            return p
    return None


def _bin() -> Optional[str]:
    global _bin_cache
    if _bin_cache and _exists(_bin_cache):
        return _bin_cache
    found = _discover_bin()
    if not found:
        _locate_via_sudo()
        found = _discover_bin()
    if found:
        _bin_cache = found
        if found != _WRAPPER:
            _remember_bin(found)
    return found


def available() -> bool:
    return _bin() is not None


def missing_hint() -> str:
    global _bin_cache
    _bin_cache = None
    if _bin():
        return ""
    return "VoIP tool missing — Update Digivice"


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
            registered = bool(
                re.search(r"(?i)registered|Ok|successful", st or "")
            ) and (user in (st or "") or server in (st or ""))
            if not registered:
                # Prefer modern flag form, then legacy positional
                out = _run(
                    [
                        exe,
                        "register",
                        "--username",
                        user,
                        "--host",
                        server,
                        "--password",
                        password,
                    ],
                    timeout=10.0,
                )
                if re.search(r"(?i)fail|error|invalid|denied", out):
                    out = _run(
                        [exe, "register", f"sip:{user}@{server}", server, password],
                        timeout=10.0,
                    )
                # Give registrar a moment
                time.sleep(0.6)
                st = _run([exe, "status", "register"], timeout=2.5)
                if re.search(r"(?i)fail|error|denied|forbidden|unauthorized", st):
                    return "SIP register failed — check Accounts"
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


def _dial_target(number: str) -> str:
    """Build a SIP URI linphonecsh can dial through the configured proxy."""
    raw = (number or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("sip:"):
        return raw
    # Keep leading + and digits
    num = re.sub(r"[^\d+*#]", "", raw)
    if not num:
        return raw
    env = _sip_env()
    server = (env.get("SIP_SERVER") or "").strip()
    if server:
        return f"sip:{num}@{server}"
    return num


def dial(number: str) -> bool:
    num = (number or "").strip()
    if not num:
        return False
    exe = _bin()
    if not exe:
        return False
    hint = ensure()
    if hint and ("fail" in hint.lower() or "missing" in hint.lower() or "daemon" in hint.lower()):
        print(f"[sip_call] dial blocked: {hint}", flush=True)
        return False
    target = _dial_target(num)
    print(f"[sip_call] dial → {target}", flush=True)
    out = _run([exe, "dial", target], timeout=6.0)
    if re.search(r"(?i)no running|failed to connect", out):
        _run([exe, "init"], timeout=4.0)
        ensure()
        out = _run([exe, "dial", target], timeout=6.0)
    # Alternate command some builds prefer
    if re.search(r"(?i)unknown|invalid|usage|fail|error|cannot|denied", out):
        out2 = _run([exe, "generic", f"call {target}"], timeout=6.0)
        if out2:
            out = out2
    if re.search(r"(?i)fail|error|denied|forbidden|not registered|cannot", out):
        print(f"[sip_call] dial reject: {out[:200]}", flush=True)
        return False
    # Confirm an outbound call actually appeared (don't lie to the UI)
    for _ in range(8):
        time.sleep(0.25)
        info = poll()
        if info.phase in ("dialing", "ringing", "early", "active"):
            return True
        if info.phase == "error":
            return False
    # Still no visible call — treat as failed so UI doesn't say "no answer"
    print(f"[sip_call] dial produced no call state; last={out[:160]!r}", flush=True)
    return False


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
    ("Early", "early"),
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
