"""Digivice voice calls via a live linphonec process (same engine as desktop).

linphonecsh's unix-pipe daemon is unreliable on the Pi. We start linphonec with
a Zadarma UDP config, wait for REGISTER, then send: call sip:1XXXXXXXXXX@host
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_log_lock = threading.Lock()
_eng_lock = threading.Lock()
_csh_lock = threading.Lock()
_engine: Optional["LinphoneEngine"] = None
_last_error = ""
_last_register_raw = ""
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
        with _log_lock:
            prev = ""
            if _LOG.is_file():
                prev = _LOG.read_text(encoding="utf-8", errors="replace")
            lines = (prev + line + "\n").splitlines()[-160:]
            _LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass


def recent_log(n: int = 14) -> str:
    try:
        if not _LOG.is_file():
            return "(no sip-last.log yet)"
        lines = _LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:]) or "(empty log)"
    except OSError as e:
        return f"(log read error: {e})"


def _exists(path: str) -> bool:
    """True if path is a real file (execute bit optional — kiosk PATH is tiny)."""
    try:
        return bool(path) and os.path.isfile(path)
    except OSError:
        return False


def _read_pin(name: str) -> Optional[str]:
    for folder in (Path("/etc/esp-handset"), Path.home() / ".esp-handset"):
        try:
            p = folder / name
            if not p.is_file():
                continue
            cand = p.read_text(encoding="utf-8", errors="replace").strip().splitlines()
            hit = (cand[0] if cand else "").strip()
            if hit and _exists(hit):
                return hit
        except OSError:
            continue
    return None


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


def _linphonerc_path() -> Path:
    return Path.home() / ".esp-handset" / "linphonerc"


def _write_linphonerc(env: Dict[str, str]) -> Optional[Path]:
    user = (env.get("SIP_USER") or "").strip()
    server = (env.get("SIP_SERVER") or "").strip()
    password = (env.get("SIP_PASS") or "").strip()
    display = (env.get("SIP_DISPLAY") or user or "Digivice").strip()
    if not user or not server or not password:
        return None
    path = _linphonerc_path()
    body = (
        "[sip]\n"
        "sip_port=5060\n"
        "sip_tcp_port=-1\n"
        "sip_tls_port=-1\n"
        "use_info=0\n"
        "guess_hostname=1\n"
        "inc_timeout=30\n"
        "use_ipv6=0\n"
        "default_proxy=0\n"
        f"display_name={display}\n"
        "\n"
        "[rtp]\n"
        "audio_rtp_port=7078\n"
        "\n"
        "[net]\n"
        "stun_server=stun.zadarma.com\n"
        "firewall_policy=1\n"
        "\n"
        "[sound]\n"
        "echocancellation=0\n"
        "\n"
        "[auth_info_0]\n"
        f"username={user}\n"
        f"userid={user}\n"
        f"passwd={password}\n"
        f"realm={server}\n"
        f"domain={server}\n"
        "\n"
        "[proxy_0]\n"
        f"reg_proxy=<sip:{server};transport=udp>\n"
        f"reg_identity=sip:{user}@{server}\n"
        "reg_expires=3600\n"
        "reg_sendregister=1\n"
        "publish=0\n"
        "dial_escape_plus=0\n"
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        os.chmod(path, 0o600)
        # Some linphonec builds ignore -c and only read ~/.linphonerc
        home_rc = Path.home() / ".linphonerc"
        try:
            home_rc.write_text(body, encoding="utf-8")
            os.chmod(home_rc, 0o600)
        except OSError:
            pass
        return path
    except OSError as e:
        _log(f"linphonerc write failed: {e}")
        return None


def _default_cc() -> str:
    env = _sip_env()
    cc = (env.get("SIP_CC") or "").strip().lstrip("+")
    if cc.isdigit():
        return cc
    did = re.sub(r"[^\d]", "", env.get("SIP_DID") or "")
    if did.startswith("1"):
        return "1"
    return "1"


def pstn_digits(number: str) -> str:
    """NANP digits with country code 1, no plus — what worked on Windows."""
    raw = (number or "").strip()
    if raw.lower().startswith("sip:"):
        rest = raw[4:]
        rest = rest.split("@", 1)[0]
        raw = rest
    digits = re.sub(r"\D", "", raw)
    cc = _default_cc()
    if len(digits) == 10:
        return f"{cc}{digits}"
    if len(digits) == 11 and digits.startswith(cc):
        return digits
    if len(digits) >= 8:
        return digits
    return digits


def _dpkg_bin(*suffixes: str) -> Optional[str]:
    try:
        r = subprocess.run(
            ["dpkg", "-L", "linphone-cli", "linphone-nogtk", "linphone"],
            capture_output=True,
            text=True,
            timeout=4.0,
            check=False,
        )
    except Exception:
        return None
    want = tuple(suffixes)
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if any(line.endswith(s) for s in want) and _exists(line):
            return line
    return None


def _discover_linphonec() -> Optional[str]:
    pinned = _read_pin("linphonec.bin")
    if pinned:
        return pinned
    for p in (
        "/usr/local/bin/digivice-linphonec",
        shutil.which("linphonec"),
        "/usr/bin/linphonec",
        "/usr/local/bin/linphonec",
        shutil.which("linphone-daemon"),
        "/usr/bin/linphone-daemon",
        "/usr/local/bin/linphone-daemon",
    ):
        if not p:
            continue
        if "digivice-linphonecsh" in p:
            continue
        if _exists(p):
            return p
    try:
        r = subprocess.run(
            ["bash", "-lc", "command -v linphonec || command -v linphone-daemon"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        hit = (r.stdout or "").strip().splitlines()
        if hit and _exists(hit[0].strip()):
            return hit[0].strip()
    except Exception:
        pass
    return _dpkg_bin("/linphonec", "/linphone-daemon")


def _discover_csh() -> Optional[str]:
    pinned = _read_pin("linphone.bin")
    if pinned:
        return pinned
    for p in (
        "/usr/local/bin/digivice-linphonecsh",
        shutil.which("linphonecsh"),
        "/usr/bin/linphonecsh",
        "/usr/local/bin/linphonecsh",
    ):
        if p and _exists(p):
            return p
    return _dpkg_bin("/linphonecsh")


def available() -> bool:
    return _discover_linphonec() is not None or _discover_csh() is not None


def missing_hint() -> str:
    if available():
        return ""
    return "VoIP tool missing — Update Digivice"


def _kill_stray_linphone() -> None:
    """Drop leftover daemons so port 5060 is free for our linphonec."""
    csh = _discover_csh()
    if csh:
        try:
            subprocess.run(
                [csh, "exit"],
                capture_output=True,
                timeout=2.0,
                check=False,
            )
        except Exception:
            pass
    for name in ("linphonec", "linphonecsh"):
        try:
            subprocess.run(
                ["pkill", "-u", str(os.getuid()), "-x", name],
                capture_output=True,
                timeout=2.0,
                check=False,
            )
        except Exception:
            pass
    time.sleep(0.35)


@dataclass
class CallInfo:
    raw: str = ""
    phase: str = "idle"
    call_id: Optional[int] = None
    remote: str = ""
    state: str = ""


def _phase_from_line(line: str, current: str) -> str:
    s = line or ""
    if re.search(
        r"(?i)IncomingReceived|Incoming call|Receiving new call", s
    ):
        return "incoming"
    if re.search(r"(?i)Registration (failed|refused)|Forbidden|403|401 Unauthorized", s):
        if "identity" in s.lower() and "successful" in s.lower():
            return current
        return current
    if re.search(
        r"(?i)Call (failed|error)|could not call|Unable to call|Not registered",
        s,
    ):
        return "error"
    if re.search(
        r"(?i)Call (terminated|ended)|CallEnd|Released|terminated",
        s,
    ):
        return "ending"
    if re.search(
        r"(?i)Connected|StreamsRunning|Call connected|Call answered", s
    ):
        return "active"
    if re.search(
        r"(?i)Remote ringing|OutgoingRinging|Ringing", s
    ):
        return "ringing"
    if re.search(
        r"(?i)OutgoingEarly|Early media|OutgoingProgress|OutgoingInit|"
        r"Contacting|Connecting to|Calling ",
        s,
    ):
        return "dialing"
    return current


class LinphoneEngine:
    """One long-lived `linphonec -c rc` with commands on stdin."""

    def __init__(self) -> None:
        self.proc: Optional[subprocess.Popen] = None
        self.phase = "idle"
        self.registered = False
        self.lines: deque = deque(maxlen=80)
        self._lock = threading.Lock()
        self._reader: Optional[threading.Thread] = None
        self.bin = ""

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _read_loop(self) -> None:
        proc = self.proc
        if proc is None or proc.stdout is None:
            return
        try:
            for raw in proc.stdout:
                line = (raw or "").rstrip()
                if not line:
                    continue
                _log(f"linphonec | {line[:200]}")
                with self._lock:
                    self.lines.append(line)
                    low = line.lower()
                    if re.search(
                        r"(?i)registration (successful|ok)|registered to|"
                        r"identity=|LinphoneRegistrationOk",
                        line,
                    ):
                        self.registered = True
                    if re.search(
                        r"(?i)registration failed|unregistered|registered=-1",
                        line,
                    ):
                        if "successful" not in low:
                            self.registered = False
                    self.phase = _phase_from_line(line, self.phase)
        except Exception as e:
            _log(f"linphonec reader: {e}")

    def start(self) -> str:
        if self.alive():
            return ""
        env = _sip_env()
        user = (env.get("SIP_USER") or "").strip()
        server = (env.get("SIP_SERVER") or "").strip()
        password = (env.get("SIP_PASS") or "").strip()
        if not user or not server or not password:
            return _set_error("Set SIP in Settings → Accounts")
        rc = _write_linphonerc(env)
        if rc is None:
            return _set_error("Could not write linphonerc")
        self.bin = _discover_linphonec() or ""
        if not self.bin:
            return _set_error("linphonec not found")
        _kill_stray_linphone()
        log_path = str(Path.home() / ".esp-handset" / "linphonec.debug")
        attempts = [
            [self.bin, "--pipe", "-c", str(rc), "-d", "1", "-l", log_path],
            [self.bin, "-c", str(rc), "-d", "1", "-l", log_path],
            [self.bin, "-c", str(rc)],
        ]
        last_err = ""
        for args in attempts:
            _log(f"start {' '.join(args)}")
            try:
                self.proc = subprocess.Popen(
                    args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env={**os.environ, "HOME": str(Path.home())},
                )
            except Exception as e:
                last_err = str(e)
                self.proc = None
                continue
            time.sleep(0.4)
            if self.proc.poll() is not None:
                leftover = ""
                try:
                    leftover = (self.proc.stdout.read() or "")[:200]
                except Exception:
                    pass
                last_err = leftover or f"exit {self.proc.returncode}"
                _log(f"linphonec died immediately: {last_err!r}")
                self.proc = None
                continue
            break
        if not self.alive():
            return _set_error(f"linphonec failed to start ({last_err[:80]})")
        self.phase = "idle"
        self.registered = False
        self._reader = threading.Thread(
            target=self._read_loop, name="linphonec-out", daemon=True
        )
        self._reader.start()
        time.sleep(0.8)
        # Interactive register (config auto-register is flaky on linphonec 5)
        self.cmd(f"register sip:{user}@{server} {server} {password}")
        self.cmd("stun stun.zadarma.com")
        deadline = time.time() + 12.0
        while time.time() < deadline:
            if self.registered:
                _log("linphonec registered")
                _set_error("")
                return ""
            if not self.alive():
                return _set_error("linphonec exited during register")
            time.sleep(0.35)
        # Don't hard-fail: some builds never print 'registered' but still dial
        _log("no register banner yet — will still try call")
        _set_error("")
        return ""

    def cmd(self, line: str) -> None:
        proc = self.proc
        if proc is None or proc.stdin is None or proc.poll() is not None:
            return
        try:
            _log(f"linphonec < {line.split(maxsplit=1)[0]}")
            proc.stdin.write(line + "\n")
            proc.stdin.flush()
        except Exception as e:
            _log(f"linphonec cmd failed: {e}")

    def snapshot(self) -> CallInfo:
        with self._lock:
            raw = "\n".join(list(self.lines)[-8:])
            phase = self.phase
        return CallInfo(raw=raw, phase=phase, state=phase)

    def stop(self) -> None:
        proc = self.proc
        self.proc = None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.write("quit\n")
                proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass


def _engine() -> LinphoneEngine:
    global _engine
    with _eng_lock:
        if _engine is None:
            _engine = LinphoneEngine()
        return _engine


def ensure() -> str:
    """Start linphonec when present. linphonecsh-only devices return OK (empty)."""
    if _discover_linphonec():
        return _engine().start()
    if _discover_csh():
        return _csh_warmup()
    return _set_error(missing_hint())


def ensure_async() -> None:
    def work() -> None:
        try:
            hint = ensure()
            if hint:
                _log(f"ensure: {hint}")
            elif _engine().alive():
                _log("linphonec ready")
            else:
                _log("linphonecsh ready")
        except Exception as e:
            _log(f"ensure failed: {e}")

    threading.Thread(target=work, name="sip-ensure", daemon=True).start()


def _csh_cmd(*args: str, timeout: float = 8.0) -> str:
    csh = _discover_csh()
    if not csh:
        return ""
    with _csh_lock:
        try:
            r = subprocess.run(
                [csh, *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except Exception as e:
            _log(f"csh {args[:2]!r} err: {e}")
            return str(e)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    shown = " ".join(args[:2])
    _log(f"csh {shown} → {out[:160]}")
    return out


def _csh_no_call(text: str) -> bool:
    s = (text or "").lower()
    return (not s) or ("no active call" in s) or ("no call" in s) or s.strip() == "idle"


def _csh_warmup() -> str:
    env = _sip_env()
    user = (env.get("SIP_USER") or "").strip()
    server = (env.get("SIP_SERVER") or "").strip()
    password = (env.get("SIP_PASS") or "").strip()
    if not user or not server or not password:
        return _set_error("Set SIP in Settings → Accounts")
    rc = _write_linphonerc(env)
    _csh_cmd("exit")
    time.sleep(0.35)
    if rc:
        init_out = _csh_cmd("init", "-c", str(rc))
        if re.search(r"(?i)no running|not running|failed to connect", init_out):
            _csh_cmd("init")
    else:
        _csh_cmd("init")
    time.sleep(0.6)
    _csh_cmd(
        "register",
        "--username",
        user,
        "--host",
        server,
        "--password",
        password,
    )
    time.sleep(0.4)
    _csh_cmd("generic", f"register sip:{user}@{server} {server} {password}")
    _set_error("")
    return ""


def _dial_via_csh(digits: str, server: str) -> Tuple[bool, str]:
    global _last_register_raw
    hint = _csh_warmup()
    if hint and "Set SIP" in hint:
        return False, hint
    st = _csh_cmd("status", "register")
    _last_register_raw = st[:200]
    target = f"sip:{digits}@{server}"
    _log(f"csh dial {digits} / {target}")
    _csh_cmd("dial", digits)
    time.sleep(0.45)
    call = _csh_cmd("status", "call")
    if _csh_no_call(call):
        _csh_cmd("dial", target)
        time.sleep(0.45)
        call = _csh_cmd("status", "call")
    if _csh_no_call(call):
        _csh_cmd("generic", f"call {target}")
        time.sleep(0.5)
        call = _csh_cmd("status", "call")
    if re.search(
        r"(?i)Outgoing|Ringing|Connected|StreamsRunning|Early|sip:", call
    ):
        _set_error("")
        return True, ""
    if not _csh_no_call(call):
        _set_error("")
        return True, ""
    _log("csh: no call banner yet — leaving INVITE up")
    _set_error("")
    return True, ""


def dial(number: str) -> bool:
    ok, _ = dial_ex(number)
    return ok


def dial_ex(number: str) -> Tuple[bool, str]:
    global _last_register_raw
    num = (number or "").strip()
    if not num:
        return False, _set_error("No number")
    env = _sip_env()
    server = (env.get("SIP_SERVER") or "").strip()
    digits = pstn_digits(num)
    if not digits:
        return False, _set_error("Bad number")
    if not server:
        return False, _set_error("Set SIP in Settings → Accounts")

    if _discover_linphonec():
        hint = _engine().start()
        eng = _engine()
        if eng.alive():
            target = f"sip:{digits}@{server}"
            _log(f"call {target} (digits={digits})")
            eng.phase = "dialing"
            eng.cmd(f"call {target}")
            time.sleep(0.4)
            eng.cmd(f"call {digits}")
            deadline = time.time() + 8.0
            while time.time() < deadline:
                info = eng.snapshot()
                _last_register_raw = (
                    "registered" if eng.registered else "unregistered"
                )
                if info.phase in ("dialing", "ringing", "early", "active"):
                    _set_error("")
                    return True, ""
                if info.phase == "error":
                    return False, _set_error("SIP rejected call")
                time.sleep(0.25)
            if eng.alive():
                _log("no stdout call banner yet — leaving call up")
                _set_error("")
                return True, ""
            _log(f"linphonec died after dial ({hint})")
        else:
            _log(f"linphonec did not start ({hint}); trying linphonecsh")

    if _discover_csh():
        return _dial_via_csh(digits, server)
    return False, _set_error(missing_hint())


def hangup() -> None:
    eng = _engine()
    if eng.alive():
        eng.cmd("terminate")
        eng.cmd("hangup")
        eng.phase = "idle"
        return
    if _discover_csh():
        _csh_cmd("generic", "terminate", timeout=3.0)
        _csh_cmd("hangup", timeout=3.0)


def answer() -> None:
    eng = _engine()
    if eng.alive():
        eng.cmd("answer")
        return
    if _discover_csh():
        _csh_cmd("answer", timeout=3.0)
        _csh_cmd("generic", "answer", timeout=3.0)


def poll() -> CallInfo:
    eng = _engine()
    if eng.alive():
        return eng.snapshot()
    if _discover_csh():
        raw = _csh_cmd("status", "call", timeout=1.5)
        phase = _phase_from_line(raw, "idle")
        if not _csh_no_call(raw) and phase == "idle":
            phase = "active"
        return CallInfo(raw=raw, phase=phase, state=phase)
    return CallInfo()


def doctor() -> str:
    env = _sip_env()
    lines = [
        f"linphonec: {_discover_linphonec() or 'MISSING'}",
        f"linphonecsh: {_discover_csh() or 'none'}",
        f"sip: {env.get('SIP_USER') or '?'}@{env.get('SIP_SERVER') or '?'}",
    ]
    hint = ensure()
    eng = _engine()
    lines.append(
        f"proc: {'up' if eng.alive() else 'down'} pid={getattr(eng.proc, 'pid', None)}"
    )
    lines.append(f"registered: {eng.registered}")
    lines.append(f"phase: {eng.phase}")
    lines.append(f"ensure: {hint or 'OK'}")
    if _last_error:
        lines.append(f"last: {_last_error}")
    lines.append("--- log ---")
    lines.append(recent_log(12))
    return "\n".join(lines)


def remote_number(remote: str) -> str:
    s = (remote or "").strip()
    if s.lower().startswith("sip:"):
        s = s[4:]
    if "@" in s:
        s = s.split("@", 1)[0]
    return s.strip()
