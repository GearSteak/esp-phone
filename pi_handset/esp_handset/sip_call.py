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
from typing import Dict, List, Optional, Tuple

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


def _register_ok(status: str, user: str = "", server: str = "") -> bool:
    st = status or ""
    if re.search(r"(?i)unregistered|not registered|registration failed|forbidden|unauthorized|403|401", st):
        return False
    if re.search(r"(?i)\bregistered\b|Registration successful|Ok\b", st):
        if user and user in st:
            return True
        if server and server in st:
            return True
        # Some builds only print "registered" / "Ok"
        if re.search(r"(?i)\bregistered\b", st):
            return True
    return False


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
            time.sleep(0.4)
            st = _run([exe, "status", "register"], timeout=2.5)
            if st.startswith("ERR") and re.search(r"(?i)no running|not running", st):
                return "Linphone daemon failed to start"
        env = _sip_env()
        user = (env.get("SIP_USER") or "").strip()
        server = (env.get("SIP_SERVER") or "").strip()
        password = (env.get("SIP_PASS") or "").strip()
        if not user or not password or not server:
            return "Set SIP in Settings → Accounts"
        if _register_ok(st, user, server):
            return ""
        # Prefer legacy positional (Debian linphone-cli); then flag form
        attempts = [
            [exe, "register", f"sip:{user}@{server}", server, password],
            [exe, "register", f"sip:{user}@{server}", f"sip:{server}", password],
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
        ]
        last = ""
        for args in attempts:
            last = _run(args, timeout=12.0)
            print(f"[sip_call] register → {last[:160]!r}", flush=True)
            if re.search(r"(?i)unknown option|invalid option|usage:", last):
                continue
            # Wait for REGISTER round-trip
            for _ in range(8):
                time.sleep(0.4)
                st = _run([exe, "status", "register"], timeout=2.5)
                if _register_ok(st, user, server):
                    return ""
            if re.search(r"(?i)forbidden|unauthorized|403|401|denied|password", last):
                return "SIP auth failed — check password"
        st = _run([exe, "status", "register"], timeout=2.5)
        if _register_ok(st, user, server):
            return ""
        print(f"[sip_call] register status still bad: {st[:200]!r}", flush=True)
        # Don't hard-block dial — some builds report oddly while calls still work
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


def _default_cc() -> str:
    env = _sip_env()
    cc = (env.get("SIP_CC") or "").strip().lstrip("+")
    if cc.isdigit():
        return cc
    did = re.sub(r"[^\d]", "", env.get("SIP_DID") or "")
    if len(did) >= 11 and did.startswith("1"):
        return "1"
    if len(did) >= 10:
        return "1"
    return "1"


def _e164(number: str) -> str:
    """Normalize to +E.164 when possible (Zadarma wants +)."""
    raw = (number or "").strip()
    if raw.lower().startswith("sip:"):
        return raw
    kept = re.sub(r"[^\d+*#]", "", raw)
    if not kept:
        return raw
    if "*" in kept or "#" in kept:
        return kept
    if kept.startswith("+"):
        return "+" + re.sub(r"\D", "", kept[1:])
    digits = re.sub(r"\D", "", kept)
    cc = _default_cc()
    if len(digits) == 10:
        return f"+{cc}{digits}"
    if len(digits) == 11 and digits.startswith(cc):
        return f"+{digits}"
    if len(digits) >= 8:
        return f"+{digits}"
    return digits or kept


def _dial_targets(number: str) -> List[str]:
    """Candidate URIs/numbers to try (Zadarma prefers sip:+E164@sip.zadarma.com)."""
    raw = (number or "").strip()
    if not raw:
        return []
    if raw.lower().startswith("sip:"):
        return [raw]
    env = _sip_env()
    server = (env.get("SIP_SERVER") or "").strip()
    e164 = _e164(raw)
    digits = re.sub(r"[^\d+*#]", "", raw)
    out: List[str] = []
    if server:
        if e164.startswith("+"):
            out.append(f"sip:{e164}@{server}")
        if digits and f"sip:{digits}@{server}" not in out:
            out.append(f"sip:{digits}@{server}")
        bare_plus = e164 if e164.startswith("+") else ""
        if bare_plus:
            out.append(bare_plus)
    if e164 and e164 not in out:
        out.append(e164)
    if digits and digits not in out:
        out.append(digits)
    # Preserve order, drop empties
    seen = set()
    uniq: List[str] = []
    for t in out:
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def _hard_dial_error(text: str) -> bool:
    """True only for clear reject — not soft chatter like 'failed to connect' after init."""
    t = text or ""
    return bool(
        re.search(
            r"(?i)not registered|forbidden|unauthorized|403|401|denied|declined|"
            r"could not resolve|no route|temporarily unavailable|486|603",
            t,
        )
    )


def dial(number: str) -> bool:
    """Place outbound call. True if linphone accepted / call appeared."""
    ok, _reason = dial_ex(number)
    return ok


def dial_ex(number: str) -> Tuple[bool, str]:
    """Return (ok, reason). reason is '' on success, else a short UI hint."""
    num = (number or "").strip()
    if not num:
        return False, "No number"
    exe = _bin()
    if not exe:
        return False, missing_hint() or "VoIP tool missing"
    hint = ensure()
    if hint and re.search(r"(?i)missing|daemon failed|auth failed|Set SIP", hint):
        print(f"[sip_call] dial blocked: {hint}", flush=True)
        return False, hint

    targets = _dial_targets(num)
    if not targets:
        return False, "Bad number"

    last_out = ""
    for target in targets:
        print(f"[sip_call] dial → {target}", flush=True)
        out = _run([exe, "dial", target], timeout=8.0)
        last_out = out or last_out
        if re.search(r"(?i)no running|failed to connect", out):
            _run([exe, "init"], timeout=4.0)
            ensure()
            out = _run([exe, "dial", target], timeout=8.0)
            last_out = out or last_out
        if re.search(r"(?i)unknown|invalid|usage", out) or _hard_dial_error(out):
            out2 = _run([exe, "generic", f"call {target}"], timeout=8.0)
            if out2:
                out = out2
                last_out = out2
        if _hard_dial_error(out):
            print(f"[sip_call] dial reject: {out[:200]}", flush=True)
            continue
        # Wait for an outbound call to show up (Zadarma can be slow)
        for _ in range(16):
            time.sleep(0.25)
            info = poll()
            if info.phase in ("dialing", "ringing", "early", "active"):
                return True, ""
            if info.phase == "error":
                break
        # Command didn't hard-fail — treat as started; UI tracks state
        if out and not _hard_dial_error(out) and not re.search(
            r"(?i)unknown|invalid|usage|no running", out
        ):
            print(f"[sip_call] dial accepted (no poll yet): {target}", flush=True)
            return True, ""
        # Empty success is common for linphonecsh dial
        if not (out or "").strip() or out.strip().lower() in ("ok", "done"):
            print(f"[sip_call] dial empty-ok → {target}", flush=True)
            return True, ""

    print(f"[sip_call] dial produced no call; last={last_out[:160]!r}", flush=True)
    if _hard_dial_error(last_out):
        return False, "SIP rejected call"
    if re.search(r"(?i)not registered", last_out):
        return False, "SIP not registered"
    return False, "Dial failed — check Wi‑Fi / number"


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

    # linphonec / linphone-cli wording variants
    if phase == "idle":
        if re.search(r"(?i)outgoing|progress|dialing|calling", raw):
            phase = "dialing"
            state = state or "Outgoing"
        elif re.search(r"(?i)ringing", raw):
            phase = "ringing"
            state = state or "Ringing"
        elif re.search(r"(?i)streams?\s*running|connected|active call", raw):
            phase = "active"
            state = state or "Connected"

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
