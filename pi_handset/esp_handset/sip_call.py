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

try:
    import fcntl
    import pty
except ImportError:
    fcntl = None  # type: ignore
    pty = None  # type: ignore

_log_lock = threading.Lock()
_eng_lock = threading.Lock()
_csh_lock = threading.Lock()
_ENGINE: Optional["LinphoneEngine"] = None
_DISC: Dict[str, Tuple[Optional[str], float]] = {
    "csh": (None, 0.0),
    "linphonec": (None, 0.0),
}
_DISC_TTL = 90.0
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


def _own_target_reason(digits: str) -> str:
    """Calling our SIP user or DID hairpins and 'connects' with no cell ring."""
    env = _sip_env()
    user = re.sub(r"\D", "", env.get("SIP_USER") or "")
    did = re.sub(r"\D", "", env.get("SIP_DID") or "")
    if user and digits == user:
        return "That's your SIP login — dial a 10-digit cell"
    if did:
        d10 = did[-10:] if len(did) >= 10 else did
        n10 = digits[-10:] if len(digits) >= 10 else digits
        if digits == did or (len(n10) == 10 and n10 == d10):
            return "That's this Digivice number — dial the other phone"
    return ""


def _call_uri(digits: str, server: str) -> str:
    return f"sip:{digits}@{server}"


def _is_linphonec_cli(path: str) -> bool:
    if not path or not _exists(path):
        return False
    try:
        real = os.path.realpath(path)
        base = os.path.basename(real).lower()
    except OSError:
        real = path
        base = os.path.basename(path).lower()
    if "daemon" in base or "linphonecsh" in base or "digivice-linphonec" in base:
        return False
    if "digivice-linphonec" in path.lower() or "digivice-linphonec" in real.lower():
        return False
    if _looks_like_script_wrapper(path) or _looks_like_script_wrapper(real):
        return False
    return "linphonec" in base


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
        if not any(line.endswith(s) for s in want) or not _exists(line):
            continue
        if _is_csh_wrapper(line):
            continue
        if line.endswith("linphonec") and not _is_linphonec_cli(line):
            continue
        return line
    return None


def _looks_like_script_wrapper(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            head = f.read(400)
    except OSError:
        return False
    if head.startswith(b"\x7fELF"):
        return False
    low = head.lower()
    return (
        b"linphonecsh not found" in low
        or b"linphonec not found" in low
        or b"digivice-linphonecsh" in low
        or b"digivice-linphonec:" in low
        or b"install linphone-cli" in low
    )


def _is_csh_wrapper(path: str) -> bool:
    if not path:
        return True
    try:
        real = os.path.realpath(path)
    except OSError:
        real = path
    blob = f"{path}\n{real}".lower()
    if "digivice-linphonecsh" in blob:
        return True
    return _looks_like_script_wrapper(path) or _looks_like_script_wrapper(real)


def _cached(kind: str, fn) -> Optional[str]:
    now = time.time()
    prev, ts = _DISC.get(kind, (None, 0.0))
    ttl = _DISC_TTL if prev else 8.0
    if ts and (now - ts) < ttl:
        return prev
    hit = fn()
    _DISC[kind] = (hit, now)
    return hit


def _bust_voip_cache() -> None:
    _DISC["csh"] = (None, 0.0)
    _DISC["linphonec"] = (None, 0.0)


def _find_via_find(name: str) -> Optional[str]:
    """Slow — only for Test SIP / install, never the 500ms poll path."""
    try:
        r = subprocess.run(
            [
                "find",
                "/usr/bin",
                "/usr/local/bin",
                "-name",
                name,
            ],
            capture_output=True,
            text=True,
            timeout=4.0,
            check=False,
        )
    except Exception:
        return None
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if line and _exists(line) and not _is_csh_wrapper(line):
            return line
    return None


def _discover_linphonec_uncached() -> Optional[str]:
    pinned = _read_pin("linphonec.bin")
    if pinned and _is_linphonec_cli(pinned):
        return pinned
    for p in (
        "/usr/bin/linphonec",
        "/usr/local/bin/linphonec",
        shutil.which("linphonec"),
    ):
        if p and _is_linphonec_cli(p):
            return p
    hit = _dpkg_bin("/linphonec")
    if hit and _is_linphonec_cli(hit):
        return hit
    return _find_via_find("linphonec")


def _discover_linphonec() -> Optional[str]:
    return _cached("linphonec", _discover_linphonec_uncached)


def _discover_csh_uncached() -> Optional[str]:
    pinned = _read_pin("linphone.bin")
    if pinned and _exists(pinned) and not _is_csh_wrapper(pinned):
        return pinned
    for p in (
        "/usr/bin/linphonecsh",
        "/usr/local/bin/linphonecsh",
        shutil.which("linphonecsh"),
    ):
        if p and _exists(p) and not _is_csh_wrapper(p):
            return p
    hit = _dpkg_bin("/linphonecsh")
    if hit and not _is_csh_wrapper(hit):
        return hit
    return _find_via_find("linphonecsh")


def _discover_csh() -> Optional[str]:
    return _cached("csh", _discover_csh_uncached)


_INSTALL_STARTED = 0.0
_INSTALL_LOCK = threading.Lock()
_INSTALL_STATE = "idle"  # idle | running | failed | ok
_INSTALL_MSG = ""


def _read_voip_status() -> str:
    try:
        p = Path("/etc/esp-handset/linphone.status")
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        pass
    return ""


def _kick_voip_install(*, force: bool = False) -> None:
    """Start linphone-cli install in the background; do not block the UI."""
    global _INSTALL_STARTED
    now = time.time()
    with _INSTALL_LOCK:
        if _INSTALL_STATE == "running" and now - _INSTALL_STARTED < 300.0:
            return
        if (
            not force
            and _INSTALL_STATE != "failed"
            and now - _INSTALL_STARTED < 120.0
        ):
            return
        _INSTALL_STATE = "running"
        _INSTALL_MSG = ""
    _INSTALL_STARTED = now
    threading.Thread(
        target=_install_voip_bg, name="voip-apt", daemon=True
    ).start()


def available() -> bool:
    if _discover_linphonec() is not None or _discover_csh() is not None:
        return True
    _kick_voip_install()
    return False


def missing_hint() -> str:
    if _discover_linphonec() is not None or _discover_csh() is not None:
        return ""
    st = _read_voip_status()
    with _INSTALL_LOCK:
        state = _INSTALL_STATE
        msg = _INSTALL_MSG
    if state == "running":
        return "Installing VoIP… try again in about a minute"
    if st.startswith("missing"):
        tail = ""
        try:
            logp = Path.home() / ".esp-handset" / "linphone-ensure.log"
            if logp.is_file():
                lines = logp.read_text(encoding="utf-8", errors="replace").splitlines()
                tail = next(
                    (
                        ln.strip()
                        for ln in reversed(lines[-30:])
                        if ln.strip() and not ln.startswith("[ensure-linphone]")
                    ),
                    "",
                )
        except OSError:
            pass
        if tail:
            return f"VoIP missing — {tail[:52]}"
        return "VoIP missing — Settings → Update, then Test SIP"
    if state == "failed" and msg:
        short = msg.replace("\n", " ").strip()
        if "password" in short.lower() or "sudo" in short.lower():
            return "VoIP needs Update once (sudo) — Settings → Update"
        return f"VoIP install failed — {short[:52]}"
    _kick_voip_install()
    return "Installing VoIP… try the call again in about a minute"


def prepare_voip(timeout: float = 180.0) -> bool:
    """Install or locate linphone. Safe from a worker thread (dial / Test SIP)."""
    global _INSTALL_STATE
    if _discover_linphonec() or _discover_csh():
        return True
    _bust_voip_cache()
    if _discover_linphonec_uncached() or _discover_csh_uncached():
        return True
    _kick_voip_install(force=True)
    deadline = time.time() + max(30.0, timeout)
    while time.time() < deadline:
        _bust_voip_cache()
        if _discover_linphonec_uncached() or _discover_csh_uncached():
            with _INSTALL_LOCK:
                _INSTALL_STATE = "ok"
            return True
        with _INSTALL_LOCK:
            state = _INSTALL_STATE
        if state != "running":
            break
        time.sleep(1.0)
    left = max(20.0, deadline - time.time())
    if left >= 20.0:
        _sudo_ensure_linphone(left)
        _bust_voip_cache()
        if _discover_linphonec_uncached() or _discover_csh_uncached():
            with _INSTALL_LOCK:
                _INSTALL_STATE = "ok"
            return True
    return bool(_discover_linphonec() or _discover_csh())


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
    """Map linphonec output to UI phase. Never treat ICE/TCP 'Connected' as answered."""
    s = line or ""
    if re.search(
        r"(?i)IncomingReceived|Incoming call|Receiving new call", s
    ):
        return "incoming"
    if re.search(
        r"(?i)Call (failed|error)|could not call|Unable to call|Not registered",
        s,
    ):
        return "error"
    if re.search(
        r"(?i)LinphoneCallEnd|Call (terminated|ended)|CallEnd",
        s,
    ):
        return "ending"
    # Talk timer only after a real call answers — not STUN/ICE/TCP "connected"
    if re.search(
        r"(?i)LinphoneCallStreamsRunning|StreamsRunning|"
        r"LinphoneCallConnected|Call answered|"
        r"Call state[: ].*Connected",
        s,
    ) and not re.search(r"(?i)disconnect", s):
        return "active"
    if re.search(
        r"(?i)LinphoneCallOutgoingRinging|OutgoingRinging|Remote ringing",
        s,
    ):
        return "ringing"
    if re.search(
        r"(?i)LinphoneCallOutgoing(Early|Progress|Init)|Early media|"
        r"OutgoingProgress|OutgoingInit|Contacting|Calling ",
        s,
    ):
        return "dialing"
    return current


class LinphoneEngine:
    """One long-lived `linphonec -c rc` with commands on stdin (PTY so output isn't stuck)."""

    def __init__(self) -> None:
        self.proc: Optional[subprocess.Popen] = None
        self.phase = "idle"
        self.registered = False
        self.lines: deque = deque(maxlen=80)
        self._lock = threading.Lock()
        self._reader: Optional[threading.Thread] = None
        self.bin = ""
        self._pty: Optional[int] = None

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _handle_line(self, line: str) -> None:
        if not line:
            return
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

    def _read_loop(self) -> None:
        try:
            if self._pty is not None:
                buf = ""
                while self.alive():
                    try:
                        chunk = os.read(self._pty, 1024)
                    except BlockingIOError:
                        time.sleep(0.05)
                        continue
                    except OSError:
                        break
                    if not chunk:
                        time.sleep(0.05)
                        continue
                    buf += chunk.decode("utf-8", "replace")
                    buf = buf.replace("\r\n", "\n").replace("\r", "\n")
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        self._handle_line(line.strip())
                return
            proc = self.proc
            if proc is None or proc.stdout is None:
                return
            for raw in proc.stdout:
                self._handle_line((raw or "").rstrip())
        except Exception as e:
            _log(f"linphonec reader: {e}")

    def _spawn(self, args: List[str]) -> None:
        env = {**os.environ, "HOME": str(Path.home()), "TERM": "dumb"}
        self._pty = None
        if pty is not None:
            try:
                master, slave = pty.openpty()
                self.proc = subprocess.Popen(
                    args,
                    stdin=slave,
                    stdout=slave,
                    stderr=slave,
                    close_fds=True,
                    env=env,
                )
                os.close(slave)
                if fcntl is not None:
                    fl = fcntl.fcntl(master, fcntl.F_GETFL)
                    fcntl.fcntl(master, fcntl.F_SETFL, fl | os.O_NONBLOCK)
                self._pty = master
                return
            except Exception as e:
                _log(f"pty spawn failed: {e}")
                self.proc = None
                self._pty = None
        cmd = args
        stdbuf = shutil.which("stdbuf")
        if stdbuf:
            cmd = [stdbuf, "-oL", "-eL", *args]
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )

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
        args = [self.bin, "-c", str(rc)]
        last_err = ""
        _log(f"start {' '.join(args)}")
        try:
            self._spawn(args)
        except Exception as e:
            last_err = str(e)
            self.proc = None
        time.sleep(0.4)
        if self.proc is None or self.proc.poll() is not None:
            leftover = last_err
            _log(f"linphonec died immediately: {leftover!r}")
            self.proc = None
            self._pty = None
            return _set_error(f"linphonec failed to start ({(leftover or 'exit')[:80]})")
        self.phase = "idle"
        self.registered = False
        self._reader = threading.Thread(
            target=self._read_loop, name="linphonec-out", daemon=True
        )
        self._reader.start()
        time.sleep(0.8)
        self.cmd(f"register sip:{user}@{server} {server} {password}")
        self.cmd("stun stun.zadarma.com")
        deadline = time.time() + 8.0
        while time.time() < deadline:
            if self.registered:
                _log("linphonec registered")
                break
            if not self.alive():
                return _set_error("linphonec exited during register")
            time.sleep(0.3)
        if not self.registered:
            _log("no register banner yet — will still try call")
        with self._lock:
            self.phase = "idle"
        _set_error("")
        return ""

    def cmd(self, line: str) -> None:
        if not self.alive():
            return
        try:
            _log(f"linphonec < {line.split(maxsplit=1)[0]}")
            payload = (line + "\n").encode("utf-8")
            if self._pty is not None:
                os.write(self._pty, payload)
                return
            proc = self.proc
            if proc is None or proc.stdin is None:
                return
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
        fd = self._pty
        if proc is not None and proc.poll() is None:
            try:
                payload = b"quit\n"
                if fd is not None:
                    os.write(fd, payload)
                elif proc.stdin is not None:
                    proc.stdin.write("quit\n")
                    proc.stdin.flush()
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass
        self.proc = None
        self._pty = None
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def _engine() -> LinphoneEngine:
    global _ENGINE
    with _eng_lock:
        if _ENGINE is None:
            _ENGINE = LinphoneEngine()
        return _ENGINE


def ensure() -> str:
    """Start linphonec when present. linphonecsh-only devices return OK (empty)."""
    if not _discover_linphonec() and not _discover_csh():
        if not prepare_voip(120.0):
            return _set_error(missing_hint())
    if _discover_linphonec():
        return _engine().start()
    if _discover_csh():
        return _csh_warmup()
    return _set_error(missing_hint())


def ensure_async() -> None:
    def work() -> None:
        try:
            if not _discover_linphonec() and not _discover_csh():
                _log("no voip binary yet — starting background install")
                _kick_voip_install(force=True)
                return
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
    if not csh or _is_csh_wrapper(csh):
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
    shown = args[0] if args else ""
    if shown == "register" or (len(args) > 1 and args[0] == "generic" and args[1].startswith("register")):
        _log("csh register → (hidden)")
    else:
        _log(f"csh {shown} → {out[:160]}")
    return out


def _csh_no_call(text: str) -> bool:
    s = (text or "").lower()
    return (
        (not s)
        or ("no active call" in s)
        or ("no call" in s)
        or ("hook=onhook" in s)
        or s.strip() == "idle"
    )


def _csh_calls() -> str:
    out = _csh_cmd("generic", "states calls", timeout=1.5)
    if out.strip() and "unknown" not in out.lower():
        return out
    return _csh_cmd("generic", "calls", timeout=1.5)


def _csh_phase(hook: str, calls: str) -> str:
    raw = f"{hook}\n{calls}"
    phase = _phase_from_line(calls, "idle")
    phase = _phase_from_line(hook, phase)
    if phase != "idle":
        return phase
    if re.search(r"(?i)OutgoingRinging|Remote ringing", raw):
        return "ringing"
    if re.search(r"(?i)OutgoingProgress|OutgoingInit|Calling ", raw):
        return "dialing"
    if re.search(r"(?i)StreamsRunning|LinphoneCallConnected", raw):
        return "active"
    # offhook alone is ringing or talk — keep as dialing, never jump to timer
    if re.search(r"(?i)hook=offhook", hook):
        return "dialing"
    return "idle"


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
            _csh_cmd("init", "-c", str(rc))
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
    time.sleep(0.5)
    _csh_cmd("generic", f"register sip:{user}@{server} {server} {password}")
    deadline = time.time() + 8.0
    while time.time() < deadline:
        st = _csh_cmd("status", "register", timeout=3.0)
        if re.search(r"(?i)identity=|registered to|RegistrationOk|successful", st):
            if "registered=-1" in st and "identity" not in st.lower():
                time.sleep(0.5)
                continue
            _set_error("")
            return ""
        time.sleep(0.5)
    _log("csh: no register identity yet")
    _set_error("")
    return ""


def _dial_via_csh(digits: str, server: str) -> Tuple[bool, str]:
    global _last_register_raw
    hint = _csh_warmup()
    if hint and "Set SIP" in hint:
        return False, hint
    st = _csh_cmd("status", "register")
    _last_register_raw = st[:200]
    target = _call_uri(digits, server)
    _log(f"csh dial {target}")
    _csh_cmd("dial", target)
    time.sleep(0.6)
    hook = _csh_cmd("status", "hook", timeout=3.0)
    calls = _csh_calls()
    phase = _csh_phase(hook, calls)
    if phase == "idle" and _csh_no_call(hook) and _csh_no_call(calls):
        _csh_cmd("generic", f"call {target}")
        time.sleep(0.7)
        hook = _csh_cmd("status", "hook", timeout=3.0)
        calls = _csh_calls()
        phase = _csh_phase(hook, calls)
    if phase in ("dialing", "ringing", "active"):
        _set_error("")
        return True, ""
    _log(f"csh: no outbound call (hook={hook[:80]!r})")
    return False, _set_error("Call did not start — try Test SIP")


def dial(number: str) -> bool:
    ok, _ = dial_ex(number)
    return ok


def dial_ex(number: str) -> Tuple[bool, str]:
    try:
        return _dial_ex_inner(number)
    except Exception as e:
        _log(f"dial_ex crashed: {e}")
        return False, _set_error(f"Dial failed: {e}")


def _dial_ex_inner(number: str) -> Tuple[bool, str]:
    global _last_register_raw
    if not _discover_linphonec() and not _discover_csh():
        _log("dial: voip missing — running prepare_voip")
        if not prepare_voip(180.0):
            return False, _set_error(missing_hint())
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
    own = _own_target_reason(digits)
    if own:
        return False, _set_error(own)

    target = _call_uri(digits, server)

    if _discover_linphonec():
        hint = _engine().start()
        eng = _engine()
        if eng.alive():
            _log(f"call {target}")
            with eng._lock:
                eng.phase = "idle"
            eng.cmd(f"call {target}")
            deadline = time.time() + 6.0
            while time.time() < deadline:
                info = eng.snapshot()
                _last_register_raw = (
                    "registered" if eng.registered else "unregistered"
                )
                if info.phase in ("dialing", "ringing", "active"):
                    _set_error("")
                    return True, ""
                if info.phase == "error":
                    return False, _set_error("SIP rejected call")
                time.sleep(0.25)
            if not eng.alive():
                _log(f"linphonec died after dial ({hint})")
            else:
                # INVITE may be in flight even if stdout is quiet — don't kill it
                with eng._lock:
                    if eng.phase == "idle":
                        eng.phase = "dialing"
                _log("left outbound call up (no state banner yet)")
                _set_error("")
                return True, ""

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
    """Cheap: never spawn linphonecsh from the UI timer."""
    eng = _engine()
    if eng.alive():
        return eng.snapshot()
    return CallInfo()


def _sudo_ensure_linphone(timeout: float = 300.0) -> str:
    """Install/find real linphonecsh. Digivice has passwordless sudo for this."""
    cmds = (
        ["sudo", "-n", "digivice-ensure-linphone"],
        ["sudo", "-n", "/usr/local/bin/digivice-ensure-linphone"],
        ["sudo", "-n", "bash", "/usr/local/bin/digivice-ensure-linphone"],
        ["sudo", "-n", "/opt/esp-handset/session/ensure-linphone.sh"],
        ["sudo", "-n", "bash", "/opt/esp-handset/session/ensure-linphone.sh"],
    )
    last = "ensure not available"
    for cmd in cmds:
        _log(f"ensure {' '.join(cmd)}")
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return "ensure timed out — Test SIP again"
        except FileNotFoundError:
            continue
        except Exception as e:
            last = str(e)
            continue
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        _log(f"ensure rc={r.returncode} {(out or '')[-120:]}")
        _bust_voip_cache()
        if r.returncode == 0:
            return out[-400:] or "ensure ok"
        last = out[-400:] or f"ensure rc={r.returncode}"
        low = out.lower()
        if (
            "password is required" in low
            or "not found" in low
            or "no such file" in low
        ):
            continue
        return last
    return last


def _install_voip_bg() -> None:
    global _INSTALL_STATE, _INSTALL_MSG
    try:
        out = _sudo_ensure_linphone(300.0)
        _bust_voip_cache()
        if _discover_linphonec_uncached() or _discover_csh_uncached():
            with _INSTALL_LOCK:
                _INSTALL_STATE = "ok"
                _INSTALL_MSG = ""
            _log("voip install OK")
            return
        with _INSTALL_LOCK:
            _INSTALL_STATE = "failed"
            _INSTALL_MSG = out or _read_voip_status() or "linphone not found"
        _log(f"voip install failed: {_INSTALL_MSG[:120]}")
    except Exception as e:
        with _INSTALL_LOCK:
            _INSTALL_STATE = "failed"
            _INSTALL_MSG = str(e)
        _log(f"voip install err: {e}")
    finally:
        _bust_voip_cache()


def doctor() -> str:
    """Fast SIP check. If linphonecsh is missing, start install in the background."""
    env = _sip_env()
    user = (env.get("SIP_USER") or "").strip() or "?"
    server = (env.get("SIP_SERVER") or "").strip() or "?"
    _bust_voip_cache()
    csh = _discover_csh_uncached()
    lp = _discover_linphonec_uncached()
    if not csh:
        csh = _dpkg_bin("/linphonecsh")
        if csh and _is_csh_wrapper(csh):
            csh = None
    if not lp:
        lp = _dpkg_bin("/linphonec")
        if lp and not _is_linphonec_cli(lp):
            lp = None
    lines = [
        f"linphonec: {lp or 'MISSING'}",
        f"linphonecsh: {csh or 'MISSING'}",
        f"sip: {user}@{server}",
    ]
    if not csh and not lp:
        threading.Thread(
            target=_install_voip_bg, name="voip-apt", daemon=True
        ).start()
        lines.insert(0, "RESULT: INSTALLING VOIP")
        lines.append("Installing linphone-cli in the background.")
        lines.append("Wait about a minute, then Test SIP again.")
        lines.append("This is not the wrapper — the real CLI is missing.")
        lines.append("--- log ---")
        lines.append(recent_log(8))
        return "\n".join(lines)
    if csh:
        _DISC["csh"] = (csh, time.time())
    if lp:
        _DISC["linphonec"] = (lp, time.time())
    eng = _engine()
    lines.append(f"proc: {'up' if eng.alive() else 'down'}")
    lines.append(f"cli-registered: {eng.registered}")
    result = "NOT REGISTERED"
    if csh:
        st = _csh_cmd("status", "register", timeout=2.0)
        compact = (st or "").replace("\n", " ").strip()
        if re.search(r"(?i)linphonecsh not found", compact):
            threading.Thread(
                target=_install_voip_bg, name="voip-apt", daemon=True
            ).start()
            result = "INSTALLING VOIP"
            lines.append("wrapper could not find real linphonecsh")
        elif re.search(r"(?i)no running|not running|failed to connect", compact):
            lines.append("daemon: not running (Save SIP to register)")
            result = "NOT REGISTERED"
        elif compact:
            lines.append(f"register: {compact[:140]}")
            ok = bool(
                re.search(
                    r"(?i)identity=|registered to|RegistrationOk|successful",
                    compact,
                )
            )
            if "registered=-1" in compact and "identity" not in compact.lower():
                ok = False
            if eng.registered:
                ok = True
            result = "REGISTERED" if ok else "NOT REGISTERED"
        else:
            result = "REGISTERED" if eng.registered else "NOT REGISTERED"
    elif eng.registered:
        result = "REGISTERED"
    if _last_error:
        lines.append(f"last: {_last_error}")
    lines.insert(0, f"RESULT: {result}")
    lines.append("--- log ---")
    lines.append(recent_log(8))
    return "\n".join(lines)


def remote_number(remote: str) -> str:
    s = (remote or "").strip()
    if s.lower().startswith("sip:"):
        s = s[4:]
    if "@" in s:
        s = s.split("@", 1)[0]
    return s.strip()
