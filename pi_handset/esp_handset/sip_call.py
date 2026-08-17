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

_ensure_lock = threading.RLock()  # also serializes linphonecsh pipe I/O
_ensured_once = False
_bin_cache: Optional[str] = None
_last_error = ""
_last_register_raw = ""
_WRAPPER = "/usr/local/bin/digivice-linphonecsh"
_BIN_HINTS = (
    Path("/etc/esp-handset/linphone.bin"),
    Path.home() / ".esp-handset" / "linphone.bin",
)
_LOG = Path.home() / ".esp-handset" / "sip-last.log"


def last_error() -> str:
    return _last_error


def last_register_raw() -> str:
    return _last_register_raw


def _set_error(msg: str) -> str:
    global _last_error
    _last_error = (msg or "").strip()
    return _last_error


def _log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(f"[sip_call] {msg}", flush=True)
    try:
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        prev = ""
        if _LOG.is_file():
            prev = _LOG.read_text(encoding="utf-8", errors="replace")
        lines = (prev + line + "\n").splitlines()[-120:]
        _LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass


def recent_log(n: int = 12) -> str:
    try:
        if not _LOG.is_file():
            return "(no sip-last.log yet)"
        lines = _LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:]) or "(empty log)"
    except OSError as e:
        return f"(log read error: {e})"


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
    """Run linphonecsh. Always serialized — concurrent pipe clients scramble replies."""
    env = os.environ.copy()
    try:
        env.setdefault("HOME", str(Path.home()))
    except Exception:
        pass
    with _ensure_lock:
        try:
            r = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=env,
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
    """True when linphonecsh status register looks successfully registered.

    Success often looks like: 'registered identity=sip:user@host'
    Failure is usually: 'registered=-1'
    Do NOT treat SIP digest '401 Unauthorized' chatter as failure when identity is present.
    """
    st = (status or "").strip()
    if not st:
        return False
    low = st.lower()
    # Hard fail only
    if re.search(r"(?i)registered\s*=\s*-1", st):
        return False
    if "identity" in low and re.search(r"(?i)registered\s*=\s*-1", st):
        return False
    # Hard success markers used by linphone 3/4/5 + openHAB checks
    if re.search(
        r"(?i)identity\s*=|registered to|RegistrationOk|LinphoneRegistrationOk|"
        r"registered\s*=\s*[1-9]\d*|registration successful",
        st,
    ):
        return True
    if re.search(r"(?i)\bregistered\b", st) and "unregistered" not in low:
        # 'registered' without =-1
        if not re.search(r"(?i)registered\s*=\s*-", st):
            return True
    if user and user in st and ("sip:" in low or (server and server in st)):
        if re.search(r"(?i)\bok\b|success|registered", st):
            return True
    return False


def _register_definitely_down(status: str) -> bool:
    st = (status or "").strip()
    if not st:
        return False
    if re.search(r"(?i)registered\s*=\s*-1", st):
        return True
    if re.search(r"(?i)\bunregistered\b|\bnot registered\b", st) and "identity" not in st.lower():
        return True
    return False


def _linphonerc_path() -> Path:
    return Path.home() / ".esp-handset" / "linphonerc"


def _write_linphonerc(env: Dict[str, str]) -> Optional[Path]:
    """Persist Zadarma/SIP proxy so `init -c` auto-registers."""
    user = (env.get("SIP_USER") or "").strip()
    server = (env.get("SIP_SERVER") or "").strip()
    password = (env.get("SIP_PASS") or "").strip()
    display = (env.get("SIP_DISPLAY") or user or "Digivice").strip()
    if not user or not server or not password:
        return None
    path = _linphonerc_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Minimal linphonerc — enough for linphonec daemon + register
        body = (
            "[sip]\n"
            "sip_port=5060\n"
            "use_info=0\n"
            "guess_hostname=1\n"
            "inc_timeout=15\n"
            "use_ipv6=0\n"
            f"display_name={display}\n"
            "\n"
            "[rtp]\n"
            "audio_rtp_port=7078\n"
            "\n"
            "[net]\n"
            "stun_server=stun.zadarma.com\n"
            "firewall_policy=1\n"
            "\n"
            "[auth_info_0]\n"
            f"username={user}\n"
            f"userid={user}\n"
            f"passwd={password}\n"
            f"realm={server}\n"
            "\n"
            "[proxy_0]\n"
            f"reg_proxy=sip:{server}\n"
            f"reg_identity=sip:{user}@{server}\n"
            "reg_expires=3600\n"
            "reg_sendregister=1\n"
            "publish=0\n"
            "dial_escape_plus=0\n"
        )
        path.write_text(body, encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return path
    except OSError as e:
        _log(f"linphonerc write failed: {e}")
        return None


def _daemon_alive(exe: str) -> bool:
    st = _run([exe, "status", "register"], timeout=2.0)
    if re.search(r"(?i)no running|not running|failed to connect|could not", st):
        return False
    if st.startswith("ERR") and "timeout" not in st.lower():
        st2 = _run([exe, "status"], timeout=2.0)
        if re.search(r"(?i)no running|not running|failed to connect", st2):
            return False
    return True


def _ensure_daemon(exe: str) -> str:
    """Bring up linphonec daemon. Fresh restart if pipe looks dead."""
    if _daemon_alive(exe):
        return ""
    env = _sip_env()
    rc = _write_linphonerc(env)
    _log(f"init linphonec daemon rc={rc}")
    # Clean any half-dead daemon first
    _run([exe, "exit"], timeout=2.0)
    time.sleep(0.35)
    # Prefer plain init (man page: default daemon). -c is best-effort.
    started = False
    if rc is not None:
        out = _run([exe, "init", "-c", str(rc)], timeout=6.0)
        _log(f"init -c → {out[:120]!r}")
        time.sleep(0.6)
        if _daemon_alive(exe):
            started = True
    if not started:
        out = _run([exe, "init"], timeout=5.0)
        _log(f"init → {out[:120]!r}")
        time.sleep(0.6)
    if not _daemon_alive(exe):
        return _set_error("Linphone daemon failed to start")
    _run([exe, "generic", "stun stun.zadarma.com"], timeout=3.0)
    return ""


def ensure() -> str:
    """Start linphonec daemon + register SIP. '' if OK, else short UI hint."""
    # Pipe I/O is serialized inside _run — do not hold a lock across sleeps
    return _ensure_unlocked()


def _status_register(exe: str) -> str:
    global _last_register_raw
    st = _run([exe, "status", "register"], timeout=2.5)
    _last_register_raw = st or ""
    return st


def _ensure_unlocked() -> str:
    exe = _bin()
    if not exe:
        return _set_error(missing_hint())
    try:
        dead = _ensure_daemon(exe)
        if dead:
            return dead
        env = _sip_env()
        user = (env.get("SIP_USER") or "").strip()
        server = (env.get("SIP_SERVER") or "").strip()
        password = (env.get("SIP_PASS") or "").strip()
        if not user or not password or not server:
            return _set_error("Set SIP in Settings → Accounts")
        _write_linphonerc(env)

        st = _status_register(exe)
        if _register_ok(st, user, server):
            _log(f"already registered: {st[:120]!r}")
            _set_error("")
            return ""

        # Official linphonecsh API first (Bookworm man page)
        attempts = [
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
            [exe, "register", f"sip:{user}@{server}", server, password],
            [exe, "generic", f"register sip:{user}@{server} {server} {password}"],
            [exe, "generic", f"register sip:{user}@{server} sip:{server} {password}"],
        ]
        for args in attempts:
            safe = " ".join(a if a != password else "***" for a in args[1:6])
            _log(f"register try: {safe}")
            out = _run(args, timeout=12.0)
            _log(f"register out: {out[:180]!r}")
            if re.search(r"(?i)unknown option|invalid option|usage:", out):
                continue
            # Digest auth needs time — keep this short so Digivice isn't stuck
            for i in range(6):
                time.sleep(0.4)
                st = _status_register(exe)
                if _register_ok(st, user, server):
                    _log(f"registered OK after {i+1} polls: {st[:120]!r}")
                    _set_error("")
                    return ""
            # Next method

        st = _status_register(exe)
        _log(f"register final: {st[:200]!r}")
        if _register_ok(st, user, server):
            _set_error("")
            return ""
        if _register_definitely_down(st):
            return _set_error(f"SIP not registered ({(st or 'empty')[:40]})")
        # Ambiguous — allow dial; Zadarma may still accept INVITE
        _log("register ambiguous — allowing dial")
        _set_error("")
        return ""
    except Exception as e:
        return _set_error(f"SIP error: {e}")


def ensure_async() -> None:
    """Background init/register — safe from Qt main thread."""
    global _ensured_once

    def work() -> None:
        global _ensured_once
        try:
            hint = ensure()
            _ensured_once = True
            if hint:
                _log(f"ensure: {hint}")
            else:
                _log("linphone ready")
        except Exception as e:
            _log(f"ensure failed ({e})")

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
    if server and e164.startswith("+"):
        out.append(f"sip:{e164}@{server}")
    if server and digits:
        out.append(f"sip:{digits}@{server}")
    if e164.startswith("+"):
        out.append(e164)
    if digits:
        out.append(digits)
    seen = set()
    uniq: List[str] = []
    for t in out:
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def _hard_dial_error(text: str) -> bool:
    """True only for clear reject — ignore SIP digest 401 noise."""
    t = text or ""
    if re.search(r"(?i)identity\s*=|registered to|RegistrationOk", t):
        return False
    return bool(
        re.search(
            r"(?i)not registered|forbidden|registration required|"
            r"could not resolve|no route|temporarily unavailable|486|603|"
            r"403 Forbidden|401 Unauthorized.*fail",
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
        return False, _set_error("No number")
    exe = _bin()
    if not exe:
        return False, _set_error(missing_hint() or "VoIP tool missing")

    hint = _ensure_unlocked()
    if hint and re.search(r"(?i)missing|daemon failed|Set SIP", hint):
        _log(f"dial blocked: {hint}")
        return False, hint

    st = _status_register(exe)
    if _register_definitely_down(st):
        # One more forced register pass
        hint2 = _ensure_unlocked()
        st = _status_register(exe)
        if _register_definitely_down(st):
            _log(f"dial abort — unregistered: {st[:160]!r}")
            detail = (st or hint2 or hint or "not registered")[:48]
            return False, _set_error(f"SIP not registered ({detail})")

    targets = _dial_targets(num)
    if not targets:
        return False, _set_error("Bad number")

    last_out = ""
    for target in targets:
        _log(f"dial → {target}")
        fired_ok = False
        for args in (
            [exe, "dial", target],
            [exe, "generic", f"call {target}"],
        ):
            out = _run(args, timeout=8.0)
            last_out = out or last_out
            _log(f"dial cmd {' '.join(args[1:3])} → {out[:140]!r}")
            if re.search(r"(?i)no running|failed to connect", out):
                _ensure_daemon(exe)
                _ensure_unlocked()
                out = _run(args, timeout=8.0)
                last_out = out or last_out
            if _hard_dial_error(out):
                continue
            if re.search(r"(?i)unknown|invalid|usage", out):
                continue
            fired_ok = True
            for _ in range(16):
                time.sleep(0.25)
                info = poll()
                if info.phase in ("dialing", "ringing", "early", "active"):
                    _log(f"call up phase={info.phase}")
                    _set_error("")
                    return True, ""
                if info.phase == "error":
                    _log(f"call error: {info.raw[:120]!r}")
                    fired_ok = False
                    break
            # Do NOT claim success without a visible call — that left Digivice
            # stuck on "Ringing" with nothing on the wire.
            if fired_ok:
                _log(f"dial cmd ok but no call state yet → try next ({target})")
                continue

    _log(f"dial failed; last={last_out[:180]!r}")
    raw = (_last_register_raw or last_out or "")[:48]
    if _hard_dial_error(last_out):
        return False, _set_error(f"SIP rejected ({raw})")
    if re.search(r"(?i)not registered", last_out):
        return False, _set_error(f"SIP not registered ({raw})")
    return False, _set_error(f"Dial failed ({raw or 'see Test SIP'})")


def doctor() -> str:
    """Short multi-line SIP/linphone status for the Accounts UI."""
    lines: List[str] = []
    exe = _bin()
    lines.append(f"bin: {exe or 'MISSING'}")
    env = _sip_env()
    lines.append(
        f"sip: {env.get('SIP_USER') or '?'}@{env.get('SIP_SERVER') or '?'}"
    )
    if not exe:
        lines.append(recent_log(8))
        return "\n".join(lines)
    hint = _ensure_unlocked()
    st = _status_register(exe)
    lines.append(f"register: {(st or 'empty')[:90]}")
    lines.append(f"ensure: {hint or 'OK'}")
    if _last_error:
        lines.append(f"last: {_last_error}")
    lines.append("--- log ---")
    lines.append(recent_log(10))
    return "\n".join(lines)


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
    if not raw or len(raw) < 3:
        return info
    if re.search(r"(?i)no\s+(active\s+)?call|No active call", raw):
        return info

    phase = "idle"
    state = ""
    for token, mapped in _STATE_MAP:
        if token in raw:
            phase = mapped
            state = token
            if mapped == "active":
                break

    # Only trust explicit call-state wording (avoid matching random '@' / help text)
    if phase == "idle":
        if re.search(
            r"(?i)Outgoing(Init|Progress|Ringing|Early)|CallState|StreamsRunning",
            raw,
        ):
            if re.search(r"(?i)OutgoingRinging", raw):
                phase, state = "ringing", "OutgoingRinging"
            elif re.search(r"(?i)OutgoingEarly|EarlyMedia", raw):
                phase, state = "early", "Early"
            elif re.search(r"(?i)StreamsRunning|Connected", raw):
                phase, state = "active", "Connected"
            else:
                phase, state = "dialing", "Outgoing"

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
