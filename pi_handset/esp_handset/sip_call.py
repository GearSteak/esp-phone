"""Digivice voice calls via a live linphonec process (same engine as desktop).

linphonecsh's unix-pipe daemon is unreliable on the Pi. We start linphonec with
a Zadarma UDP config, wait for REGISTER, then send: call sip:1XXXXXXXXXX@host
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import threading
import time
import traceback
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

try:
    import termios
except ImportError:
    termios = None  # type: ignore

_log_lock = threading.Lock()
_eng_lock = threading.Lock()
_run_lock = threading.Lock()
_csh_lock = threading.Lock()
_ENGINE: Optional["LinphoneEngine"] = None
_DISC: Dict[str, Tuple[Optional[str], float]] = {
    "csh": (None, 0.0),
    "linphonec": (None, 0.0),
}
_DISC_TTL = 90.0
_last_error = ""
_last_register_raw = ""
_active_backend: Optional[str] = None  # "csh" | "pty" | None — which stack owns the call
_csh_poll_lock = threading.Lock()
_csh_poll_info: Optional[CallInfo] = None  # filled after CallInfo exists; see _ensure_csh_poller
_csh_poll_thread: Optional[threading.Thread] = None
_csh_poll_stop = threading.Event()
_csh_idle_streak = 0
_LOG = Path.home() / ".esp-handset" / "sip-last.log"
_CORE_LOG = Path.home() / ".esp-handset" / "linphone-core.log"
_REPORT = Path.home() / ".esp-handset" / "sip-doctor.txt"


def last_error() -> str:
    return _last_error


def last_call_error() -> str:
    """SIP/PSTN reject reason from the core log, if any."""
    return _core_log_call_error()


def last_register_raw() -> str:
    return _last_register_raw


def _set_error(msg: str) -> str:
    global _last_error
    _last_error = (msg or "").strip()
    return _last_error


def _log(msg: str) -> None:
    msg = _redact(msg)
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


def _redact(text: str) -> str:
    s = text or ""
    s = re.sub(r"(?im)^(\s*(?:SIP_PASS|passwd|password|ha1)\s*=\s*).+$", r"\1***", s)
    s = re.sub(r"(?im)^(register sip:\S+ \S+ )\S+$", r"\1***", s)
    # Do not call _sip_env() here — Prep SIP redacts large tails and that
    # re-read + replace loop was a crash vector on low-RAM Pis.
    return s


def _cmd_out(cmd: List[str], timeout: float = 5.0, cap: int = 2500) -> str:
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        return out[:cap] if out else f"(exit {r.returncode}, empty)"
    except Exception as e:
        return f"(err {e})"


def _trim_core_log_if_huge(max_keep: int = 200_000) -> None:
    """Prevent linphone-core.log from growing until Prep SIP OOMs the Pi."""
    try:
        if not _CORE_LOG.is_file():
            return
        size = _CORE_LOG.stat().st_size
        if size <= max_keep * 2:
            return
        with _CORE_LOG.open("rb") as f:
            f.seek(-max_keep, os.SEEK_END)
            tail = f.read()
        _CORE_LOG.write_bytes(b"(...log trimmed...)\n" + tail)
    except OSError:
        pass


def _tail_file(path: Path, max_bytes: int = 2500) -> str:
    """Read only the end of a file — full core logs OOM the Pi on Prep SIP."""
    try:
        if not path.is_file():
            return "(missing)"
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > max_bytes:
                f.seek(-max_bytes, os.SEEK_END)
            data = f.read(max_bytes)
        text = data.decode("utf-8", "replace")
        if size > max_bytes:
            text = f"(…truncated, last {max_bytes} bytes…)\n" + text
        return _redact(text)
    except OSError as e:
        return f"(read error: {e})"


def write_sip_report(*, extra: str = "", run_doctor: bool = False) -> Path:
    """Tiny SIP dump for Transfer → sip-doctor.txt.

    File tails only — no subprocesses, no doctor(), no log rewrite.
    Prep SIP / download must stay safe on a 2GB Pi.
    """
    chunks: List[str] = [
        f"=== digivice-sip-doctor {time.strftime('%Y-%m-%d %H:%M:%S')} ===",
        f"host={_hostname()} user={os.environ.get('USER', '')}",
        f"backend={_active_backend or 'none'}",
        f"last_error={_last_error or ''}",
        "",
    ]
    if extra:
        chunks.append("--- extra ---")
        chunks.append(_redact(str(extra))[:800])
        chunks.append("")
    # Ignore run_doctor — never restart VoIP from Prep/download.
    _ = run_doctor
    try:
        env = _sip_env()
    except Exception:
        env = {}
    chunks.append("--- sip.env (redacted) ---")
    if not env:
        chunks.append("(no sip.env)")
    else:
        for k in ("SIP_SERVER", "SIP_USER", "SIP_DISPLAY", "SIP_DID", "SIP_PASS"):
            if k not in env:
                continue
            v = "***" if k == "SIP_PASS" else env.get(k, "")
            chunks.append(f"{k}={v}")
        chunks.append(f"env-from: {sip_env_source() or '?'}")
        chunks.append(f"pass-len: {len((env.get('SIP_PASS') or '').strip())}")
    chunks.append("")
    # Paths only — never run linphonec / find / ss / git here.
    chunks.append("--- binaries ---")
    for label, cand in (
        ("linphonec", _read_pin("linphonec.bin") or "/usr/bin/linphonec"),
        ("linphonecsh", _read_pin("linphone.bin") or "/usr/bin/linphonecsh"),
    ):
        try:
            ok = Path(cand).is_file()
        except OSError:
            ok = False
        chunks.append(f"{label}: {cand}{' OK' if ok else ' MISSING'}")
    chunks.append("")
    for p in (
        Path.home() / ".esp-handset" / "last_update",
        Path("/etc/esp-handset/last_update"),
        Path.home() / "esp-phone" / ".git" / "HEAD",
    ):
        try:
            if p.is_file():
                chunks.append(f"{p}: {p.read_text(encoding='utf-8', errors='replace').strip()[:100]}")
        except OSError:
            pass
    chunks.append("")
    chunks.append(f"ipv4={_local_ipv4() or 'NONE'}")
    chunks.append("")
    for label, path, cap in (
        ("linphonerc", _linphonerc_path(), 1600),
        ("sip-last.log", _LOG, 1800),
        ("linphone-core.log", _CORE_LOG, 2800),
        ("linphone.status", Path("/etc/esp-handset/linphone.status"), 120),
    ):
        chunks.append(f"--- {label} ---")
        chunks.append(_tail_file(path, cap))
        chunks.append("")
    body = "\n".join(chunks) + "\n"
    if len(body) > 24000:
        body = body[:24000] + "\n=== truncated ===\n"
    # One write path only — less I/O / less chance of OOM mid-copy.
    for dest in (_REPORT, Path("/tmp/digivice-sip-doctor.txt")):
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body, encoding="utf-8")
        except OSError as e:
            _log(f"sip report write {dest}: {e}")
    try:
        _log(f"sip report → {_REPORT} ({len(body)} bytes)")
    except Exception:
        pass
    return _REPORT


def _hostname() -> str:
    try:
        import socket as _socket

        return _socket.gethostname()
    except Exception:
        return "?"


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


_last_sip_env_source = ""


def _sip_env_paths() -> List[Path]:
    seen: set = set()
    paths: List[Path] = []
    for p in (
        Path.home() / ".esp-handset" / "sip.env",
        Path("/etc/esp-handset/sip.env"),
    ):
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key in seen:
            continue
        seen.add(key)
        paths.append(p)
    return paths


def _read_sip_file(path: Path) -> Dict[str, str]:
    vals: Dict[str, str] = {}
    try:
        if not path.is_file() or not os.access(path, os.R_OK):
            return vals
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip()
    except OSError:
        pass
    return vals


def _is_placeholder_sip_pass(password: str) -> bool:
    p = (password or "").strip()
    if not p:
        return True
    if p in ("YOUR_SIP_PASSWORD", "Ping927Ld"):
        return True
    if p.startswith("YOUR_") or p.startswith("CHANGE_ME"):
        return True
    return False


def _sip_env_score(vals: Dict[str, str]) -> int:
    if not (vals.get("SIP_USER") or "").strip():
        return 0
    if not (vals.get("SIP_SERVER") or "").strip():
        return 0
    if _is_placeholder_sip_pass(vals.get("SIP_PASS") or ""):
        return 1
    return 10


def sip_env_source() -> str:
    return _last_sip_env_source


def _sip_env() -> Dict[str, str]:
    global _last_sip_env_source
    best: Dict[str, str] = {}
    best_score = 0
    best_path = ""
    home = Path.home() / ".esp-handset" / "sip.env"
    for path in _sip_env_paths():
        vals = _read_sip_file(path)
        score = _sip_env_score(vals)
        if score > best_score:
            best_score = score
            best = vals
            best_path = str(path)
        elif (
            score == best_score
            and score >= 10
            and path.resolve() == home.resolve()
        ):
            best = vals
            best_path = str(path)
    _last_sip_env_source = best_path
    return dict(best)


def _linphonerc_path() -> Path:
    return Path.home() / ".esp-handset" / "linphonerc"


def _alsa_voip_devices() -> Tuple[str, str, str]:
    """ALSA labels for linphone: (playback, capture, ringer). Dual = jack + USB tee."""
    try:
        from esp_handset.alsa_dual import card_sets, voip_playback_label

        dual_pb = voip_playback_label()
        hp_short, hp_label, usb_short, usb_label = card_sets()
    except Exception:
        dual_pb = None
        hp_short = hp_label = usb_short = usb_label = None

    usb = f"ALSA: {usb_label}" if usb_label else ""
    headphones = f"ALSA: {hp_label}" if hp_label else ""

    if not usb and not headphones:
        try:
            r = subprocess.run(
                ["aplay", "-l"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
        except Exception:
            d = "ALSA: default"
            return d, d, d
        lines = (r.stdout or "").splitlines()
        other = ""
        for line in lines:
            m = re.match(r"^card \d+:\s*\S+\s*\[([^\]]+)\]", line)
            if not m:
                continue
            low = line.lower()
            if any(x in low for x in ("hdmi", "vc4")):
                continue
            name = m.group(1).strip()
            if not name:
                continue
            label = f"ALSA: {name}"
            if "usb" in low or "device" in low or "cm10" in low or "headset" in low:
                usb = usb or label
            elif "bcm2835" in low or "headphones" in low or "headphone" in low:
                headphones = headphones or label
            else:
                other = other or label

    # Both plugged in → ALSA default pcm.!default mirrors to jack + USB
    if dual_pb:
        playback = dual_pb
    else:
        playback = headphones or usb or "ALSA: default"
    capture = usb or headphones or "ALSA: default"
    ringer = playback
    return playback, capture, ringer


def _alsa_usb_label() -> str:
    """Legacy single device — playback path."""
    return _alsa_voip_devices()[0]


def _local_ipv4() -> str:
    out = _cmd_out(["hostname", "-I"], timeout=2.0, cap=200)
    for tok in (out or "").split():
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", tok) and not tok.startswith("127."):
            return tok
    return ""


def _prepare_linphone_home() -> None:
    for p in (
        Path.home() / ".local" / "share" / "linphone",
        Path.home() / ".config" / "linphone",
    ):
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


def _write_linphonerc(env: Dict[str, str]) -> Optional[Path]:
    user = (env.get("SIP_USER") or "").strip()
    server = (env.get("SIP_SERVER") or "").strip()
    password = (env.get("SIP_PASS") or "").strip()
    display = (env.get("SIP_DISPLAY") or user or "Digivice").strip()
    if not user or not server or not password:
        return None
    playback, capture, ringer = _alsa_voip_devices()
    ip = _local_ipv4() or "127.0.0.1"
    ha1 = hashlib.md5(f"{user}:{server}:{password}".encode("utf-8")).hexdigest()
    _prepare_linphone_home()
    # guess_hostname=0 made Contact sip:gear@unknown-host (Zadarma ignores that).
    # Skip STUN on REGISTER — linphone 5 rewrites nat_policy_ref to a random id
    # then fails next start with "There is no NatPolicy with ref […]".
    body = (
        "[sip]\n"
        "sip_port=5060\n"
        "sip_tcp_port=0\n"
        "sip_tls_port=0\n"
        "use_info=0\n"
        "guess_hostname=1\n"
        "register_only_when_network_is_up=0\n"
        "inc_timeout=45\n"
        "use_ipv6=0\n"
        "ipv6_enabled=0\n"
        "default_proxy=0\n"
        f"display_name={display}\n"
        f"contact=sip:{user}@{ip}\n"
        "\n"
        "[rtp]\n"
        "audio_rtp_port=7078\n"
        "audio_jitt_comp=60\n"
        "nortp_timeout=120\n"
        "\n"
        "[net]\n"
        "firewall_policy=0\n"
        "mtu=1300\n"
        "\n"
        "[sound]\n"
        "echocancellation=0\n"
        f"playback_dev_id={playback}\n"
        f"capture_dev_id={capture}\n"
        f"ringer_dev_id={ringer}\n"
        "\n"
        "[audio_codec_0]\n"
        "mime=PCMU\n"
        "rate=8000\n"
        "channels=1\n"
        "enabled=1\n"
        "\n"
        "[audio_codec_1]\n"
        "mime=PCMA\n"
        "rate=8000\n"
        "channels=1\n"
        "enabled=1\n"
        "\n"
        "[audio_codec_2]\n"
        "mime=opus\n"
        "rate=48000\n"
        "channels=2\n"
        "enabled=0\n"
        "\n"
        "[auth_info_0]\n"
        f"username={user}\n"
        f"userid={user}\n"
        f"passwd={password}\n"
        f"ha1={ha1}\n"
        f"realm={server}\n"
        f"domain={server}\n"
        "\n"
        "[proxy_0]\n"
        f"reg_proxy=<sip:{server};transport=udp>\n"
        f"reg_identity=sip:{user}@{server}\n"
        "reg_expires=120\n"
        "reg_sendregister=1\n"
        "publish=0\n"
        "dial_escape_plus=0\n"
    )
    path = _linphonerc_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        os.chmod(path, 0o600)
        home_rc = Path.home() / ".linphonerc"
        try:
            home_rc.write_text(body, encoding="utf-8")
            os.chmod(home_rc, 0o600)
        except OSError:
            pass
        cfg_dir = Path.home() / ".config" / "linphone"
        try:
            cfg_dir.mkdir(parents=True, exist_ok=True)
            (cfg_dir / "linphonerc").write_text(body, encoding="utf-8")
            os.chmod(cfg_dir / "linphonerc", 0o600)
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


def _voip_bin_runs(path: str) -> bool:
    """False when the ELF exists but cannot load (rc 127 / missing .so)."""
    if not path or not _exists(path):
        return False
    try:
        r = subprocess.run(
            [path, "-v"],
            capture_output=True,
            text=True,
            timeout=4.0,
            check=False,
        )
    except Exception:
        return False
    blob = ((r.stdout or "") + (r.stderr or "")).lower()
    if "error while loading shared libraries" in blob:
        return False
    if "cannot open shared object" in blob:
        return False
    if r.returncode == 127:
        return False
    return True


def _broken_linphonec_msg() -> str:
    for p in ("/usr/bin/linphonec", "/usr/local/bin/linphonec"):
        if not _exists(p):
            continue
        if _voip_bin_runs(p):
            continue
        return _cmd_out([p, "-v"], timeout=4.0, cap=400)
    return ""


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
        if not line or not _exists(line):
            continue
        if name == "linphonec":
            if _is_linphonec_cli(line):
                return line
            continue
        if not _is_csh_wrapper(line):
            return line
    return None


def _discover_linphonec_uncached() -> Optional[str]:
    pinned = _read_pin("linphonec.bin")
    if pinned and _is_linphonec_cli(pinned) and _voip_bin_runs(pinned):
        return pinned
    for p in (
        "/usr/bin/linphonec",
        "/usr/local/bin/linphonec",
        shutil.which("linphonec"),
    ):
        if p and _is_linphonec_cli(p) and _voip_bin_runs(p):
            return p
    hit = _dpkg_bin("/linphonec")
    if hit and _is_linphonec_cli(hit) and _voip_bin_runs(hit):
        return hit
    hit = _find_via_find("linphonec")
    if hit and _voip_bin_runs(hit):
        return hit
    return None


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
    global _INSTALL_STARTED, _INSTALL_STATE, _INSTALL_MSG
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
    # Call-level only. "Not registered" / ICE "failed" must not kill the overlay.
    if re.search(
        r"(?i)LinphoneCallError|"
        r"\bCall failed\b|Unable to call|could not call|"
        r"403 Forbidden|404 Not Found|402 Payment|486 Busy|603 Decline|"
        r"408 Request Timeout|487 Request Terminated|"
        r"480 Temporarily|Not Acceptable|Forbidden",
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
        r"OutgoingProgress|OutgoingInit|Contacting|Calling |"
        r"Establishing call",
        s,
    ):
        return "dialing"
    return current


def _core_log_tail(n_chars: int = 8000) -> str:
    try:
        if not _CORE_LOG.is_file():
            return ""
        return _CORE_LOG.read_text(encoding="utf-8", errors="replace")[-n_chars:]
    except OSError:
        return ""


def _core_log_call_phase() -> Optional[str]:
    """Best-effort call phase from linphone-core.log (PTY banners are often quiet)."""
    text = _core_log_tail(14000)
    if not text:
        return None
    last: Optional[str] = None
    for ln in text.splitlines():
        flag = _phase_from_line(ln, "")
        if flag in ("incoming", "error", "ending", "active", "ringing", "dialing"):
            last = flag
            continue
        # belle-sip wire log (common when linphonec CLI stays quiet)
        if re.search(r"(?i)^\s*INVITE\s+sip:", ln) or re.search(
            r"(?i)message sent.*\bINVITE\b", ln
        ):
            last = "dialing"
        elif re.search(r"(?i)SIP/2\.0\s+180\b|Ringing", ln) and "REGISTER" not in ln:
            last = "ringing"
        elif re.search(r"(?i)SIP/2\.0\s+183\b|Session Progress", ln):
            last = "dialing"
        elif re.search(r"(?i)SIP/2\.0\s+200\b", ln) and re.search(
            r"(?i)INVITE|cseq:.*invite", text[-2000:], re.I
        ):
            # Don't treat REGISTER 200 as answered
            if re.search(r"(?i)CSeq:.*INVITE", text[-2500:]):
                last = "active"
        elif re.search(
            r"(?i)SIP/2\.0\s+(402|403|404|408|480|486|487|603)\b", ln
        ):
            # Ignore REGISTER 403 lockout noise during an outbound dial if
            # we already saw an INVITE in this window — still surface as error.
            last = "error"
    return last


def _core_log_call_error() -> str:
    text = _core_log_tail(14000)
    if not text:
        return ""
    # Prefer the most recent SIP failure related to INVITE, not stale REGISTER blocks
    tail = text[-6000:]
    patterns = (
        (r"(?i)402 Payment Required", "Add Zadarma balance"),
        (r"(?i)403 Forbidden", "Call blocked (403)"),
        (r"(?i)404 Not Found", "Bad number (404)"),
        (r"(?i)480 Temporarily", "Unavailable (480)"),
        (r"(?i)486 Busy", "Busy"),
        (r"(?i)603 Decline", "Declined"),
        (r"(?i)408 Request Timeout", "Timed out (408)"),
        (r"(?i)Unable to call|could not call|Call failed", "Could not place call"),
        (r"(?i)Blocked for incorrect passwords", "SIP still locked"),
    )
    for pat, msg in patterns:
        if re.search(pat, tail):
            return msg
    return ""


_ANSI = re.compile(r"\x1b\[[0-9;?=]*[A-Za-z]|\x1b\].*?(?:\x07|\x1b\\)")


def _clean_cli(line: str) -> str:
    s = _ANSI.sub("", line or "")
    return s.replace("\x00", "").replace("linphonec>", "").strip()


def _line_registered(line: str) -> Optional[bool]:
    """True/False if this linphonec line reports REGISTER state, else None."""
    s = _clean_cli(line)
    if not s:
        return None
    low = s.lower()
    if re.search(
        r"(?i)registration failed|unregistered|"
        r"registered\s*=\s*-1|LinphoneRegistrationFailed|"
        r"\bnot registered\b|io error|unauthorized|403 forbidden",
        s,
    ):
        # 401 challenge chatter is normal — only fail if there is no success on this line
        if not re.search(
            r"(?i)registration (on\b.*)?(is )?successful|"
            r"registration ok|registered\s*=\s*1|now registered",
            s,
        ):
            # "401 Unauthorized" during digest is not a failed REGISTER
            if re.search(r"(?i)\b401\b", s) and not re.search(
                r"(?i)registration failed", s
            ):
                return None
            return False
    if re.search(
        r"(?i)registration (on\b.*)?(is )?(successful|sucessful|ok)|registered to|"
        r"LinphoneRegistrationOk|"
        r"now registered|is registered|"
        r"registered\s*=\s*[1-9]|registered identity|^registered,|"
        r"registered:\s*yes",
        s,
    ):
        if "not registered" not in low and "unregistered" not in low:
            return True
    return None


def _text_registered(text: str) -> Optional[bool]:
    last: Optional[bool] = None
    for ln in (text or "").splitlines():
        flag = _line_registered(ln)
        if flag is not None:
            last = flag
    return last


def _core_log_registered() -> Optional[bool]:
    try:
        if not _CORE_LOG.is_file():
            return None
        text = _CORE_LOG.read_text(encoding="utf-8", errors="replace")[-12000:]
    except OSError:
        return None
    return _text_registered(text)


def _zadarma_block_reason() -> str:
    """Zadarma 403 lockout / auth reject from linphone-core.log, else empty."""
    try:
        if not _CORE_LOG.is_file():
            return ""
        text = _CORE_LOG.read_text(encoding="utf-8", errors="replace")[-20000:]
    except OSError:
        return ""
    if re.search(r"(?i)Blocked for incorrect passwords", text):
        return (
            "Zadarma LOCKED this SIP extension (403 Blocked). "
            "This is a server lockout from earlier failed logins — your current "
            "password may already be correct but will not work until Zadarma clears "
            "the block. Contact Zadarma support to unlock, or wait several hours "
            "without tapping Test SIP."
        )
    if re.search(r"(?i)403 Forbidden", text) and re.search(
        r"(?i)LinphoneRegistrationFailed", text
    ):
        return "Zadarma rejected REGISTER (403). Check SIP user/password in Accounts."
    return ""


class LinphoneEngine:
    """One long-lived `linphonec -c rc`. PTY + CR so readline actually accepts commands."""

    def __init__(self) -> None:
        self.proc: Optional[subprocess.Popen] = None
        self.phase = "idle"
        self.registered = False
        self.lines: deque = deque(maxlen=80)
        self._lock = threading.Lock()
        self._reader: Optional[threading.Thread] = None
        self.bin = ""
        self._pty: Optional[int] = None
        self._user = ""
        self._server = ""
        self._password = ""
        self._rc_key = ""
        self._auth_prompt = False
        self._pass_sent_at = 0.0
        self._cli_ready = False

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _send_sip_password(self) -> None:
        if not self._password or not self.alive():
            return
        now = time.time()
        with self._lock:
            if now - self._pass_sent_at < 8.0:
                return
            self._pass_sent_at = now
            self._auth_prompt = True
            self._cli_ready = False
        _log("linphonec password prompt — sending SIP_PASS once")
        try:
            payload = (self._password + "\r\n").encode("utf-8")
            if self._pty is not None:
                os.write(self._pty, payload)
                return
            proc = self.proc
            if proc is not None and proc.stdin is not None:
                proc.stdin.write(self._password + "\n")
                proc.stdin.flush()
        except Exception as e:
            _log(f"password send failed: {e}")

    def _handle_line(self, line: str) -> None:
        line = _clean_cli(line)
        if not line:
            return
        if self._password and line.strip() == self._password:
            return
        low = line.lower()
        if "password for" in low:
            self._send_sip_password()
            return
        if "linphonec>" in low:
            with self._lock:
                if self._pass_sent_at and (time.time() - self._pass_sent_at) > 0.4:
                    self._auth_prompt = False
                if not self._auth_prompt:
                    self._cli_ready = True
        # PTY echo of our own commands — not linphonec status
        if low in ("status register", "status", "proxy list", "register") or low.startswith(
            "register sip:"
        ):
            return
        _log(f"linphonec | {line[:200]}")
        with self._lock:
            self.lines.append(line)
            flag = _line_registered(line)
            if flag is True:
                self.registered = True
                self._auth_prompt = False
                self._cli_ready = True
            elif flag is False:
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
                        self._handle_line(line)
                    m = re.search(r"(?i)password for [^\n]*", buf)
                    if m:
                        self._handle_line(buf[: m.end()])
                        buf = buf[m.end() :]
                    elif "linphonec>" in buf:
                        self._handle_line(buf)
                        buf = ""
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
                if termios is not None:
                    try:
                        attrs = termios.tcgetattr(slave)
                        attrs[3] &= ~(
                            termios.ECHO
                            | termios.ECHOE
                            | termios.ECHOK
                            | getattr(termios, "ECHONL", 0)
                        )
                        termios.tcsetattr(slave, termios.TCSANOW, attrs)
                    except Exception:
                        pass
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

    def _drain(self, limit: int = 2000) -> str:
        buf = b""
        fd = self._pty
        if fd is not None:
            end = time.time() + 0.4
            while time.time() < end:
                try:
                    chunk = os.read(fd, 1024)
                except BlockingIOError:
                    time.sleep(0.04)
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
            return buf.decode("utf-8", "replace")[-limit:]
        proc = self.proc
        if proc is not None and proc.stdout is not None:
            try:
                raw = proc.stdout.read()
            except Exception:
                raw = ""
            if isinstance(raw, bytes):
                return raw.decode("utf-8", "replace")[-limit:]
            return str(raw or "")[-limit:]
        return ""

    def start(self) -> str:
        with _run_lock:
            return self._start_inner()

    def _start_inner(self) -> str:
        env = _sip_env()
        user = (env.get("SIP_USER") or "").strip()
        server = (env.get("SIP_SERVER") or "").strip()
        password = (env.get("SIP_PASS") or "").strip()
        if not user or not server or not password:
            return _set_error("Set SIP in Settings → Accounts")
        rc_key = f"{user}|{server}|{password}"
        self._user, self._server, self._password = user, server, password
        if self.alive() and self.registered and self._rc_key == rc_key:
            return ""
        if self.alive() and self._rc_key != rc_key:
            _log("SIP account changed — restart linphonec")
            self.stop()
            time.sleep(0.4)
        elif self.alive() and not self.registered:
            blocked = _zadarma_block_reason()
            if blocked:
                return _set_error(blocked)
            _log("linphonec up but not registered — retry REGISTER")
            if self.ensure_registered(12.0, send_register=True):
                return ""
            blocked = _zadarma_block_reason()
            if blocked:
                return _set_error(blocked)
            _log("still unregistered — restart linphonec")
            self.stop()
            time.sleep(0.4)
        rc = _write_linphonerc(env)
        if rc is None:
            return _set_error("Could not write linphonerc")
        self.bin = _discover_linphonec() or ""
        if not self.bin:
            return _set_error("linphonec not found")
        _kill_stray_linphone()
        try:
            _CORE_LOG.parent.mkdir(parents=True, exist_ok=True)
            _CORE_LOG.write_text("", encoding="utf-8")
        except OSError:
            pass
        attempts = (
            [self.bin, "-S", "-d", "1", "-l", str(_CORE_LOG), "-c", str(rc)],
            [self.bin, "-S", "-c", str(rc)],
            [self.bin, "-c", str(rc)],
            [self.bin, f"--config={rc}"],
        )
        last_err = ""
        started = False
        for args in attempts:
            _log(f"start {' '.join(args)} sound={_alsa_voip_devices()}")
            try:
                self._spawn(args)
            except Exception as e:
                last_err = str(e)
                self.proc = None
                self._pty = None
                _log(f"spawn failed: {e}")
                continue
            time.sleep(0.55)
            if self.proc is not None and self.proc.poll() is None:
                started = True
                break
            leftover = self._drain(800) or last_err
            code = self.proc.poll() if self.proc is not None else "?"
            _log(f"linphonec died immediately rc={code} {leftover[:240]!r}")
            last_err = leftover or last_err or f"exit {code}"
            self.stop()
            time.sleep(0.2)
        if not started:
            try:
                write_sip_report(extra=f"linphonec failed to start: {last_err[:400]}")
            except Exception:
                pass
            return _set_error(
                f"linphonec failed to start ({(last_err or 'exit')[:80]})"
            )
        self.phase = "idle"
        self.registered = False
        self._auth_prompt = False
        self._pass_sent_at = 0.0
        self._cli_ready = False
        self._rc_key = rc_key
        self._reader = threading.Thread(
            target=self._read_loop, name="linphonec-out", daemon=True
        )
        self._reader.start()
        # rc has reg_sendregister=1 — do not type status/proxy into a password prompt
        if not self.ensure_registered(16.0, send_register=False):
            blocked = _zadarma_block_reason()
            if not blocked:
                self.ensure_registered(12.0, send_register=True)
            if not self.registered:
                if not self.alive():
                    err = _set_error("linphonec exited during register")
                    try:
                        write_sip_report(extra=err + "\n" + recent_log(20))
                    except Exception:
                        pass
                    return err
                blocked = _zadarma_block_reason()
                with self._lock:
                    tail = " | ".join(list(self.lines)[-5:])
                ip = _local_ipv4()
                if blocked:
                    err = _set_error(blocked)
                    self.stop()
                elif not ip:
                    err = _set_error("No IPv4 — Wi-Fi/cell is down")
                else:
                    err = _set_error("SIP not registered — check Wi‑Fi / Accounts")
                extra = _redact(tail)[:180]
                if extra and not blocked:
                    err = _set_error(f"{err}\n{extra}")
                try:
                    write_sip_report(extra=err + "\n" + recent_log(20))
                except Exception:
                    pass
                return err
        with self._lock:
            self.phase = "idle"
        _set_error("")
        _log("SIP registered — ready to dial")
        return ""

    def ensure_registered(self, timeout_s: float, *, send_register: bool) -> bool:
        started = time.time()
        sent = False
        deadline = started + max(1.0, timeout_s)
        while time.time() < deadline:
            with self._lock:
                if self.registered:
                    _log("linphonec registered")
                    return True
                recent = "\n".join(list(self.lines)[-8:])
                prompting = self._auth_prompt
                ready = self._cli_ready
                sent_pw = self._pass_sent_at
            flag = _text_registered(recent) or _core_log_registered()
            if flag is True:
                with self._lock:
                    self.registered = True
                    self._cli_ready = True
                _log("linphonec registered")
                return True
            blocked = _zadarma_block_reason()
            if blocked:
                _log("Zadarma lockout — stopping linphonec")
                self.stop()
                return False
            if not self.alive():
                return False
            elapsed = time.time() - started
            if sent_pw and (time.time() - sent_pw) > 1.0:
                with self._lock:
                    self._auth_prompt = False
                    self._cli_ready = True
                ready = True
            elif elapsed > 6.0 and not prompting:
                with self._lock:
                    self._cli_ready = True
                ready = True
            if send_register and not sent and ready and self._user and self._server:
                blocked = _zadarma_block_reason()
                if blocked:
                    _log("Zadarma lockout — stopping linphonec")
                    self.stop()
                    return False
                self.cmd(
                    f"register sip:{self._user}@{self._server} "
                    f"{self._server} {self._password}"
                )
                sent = True
            time.sleep(0.35)
        with self._lock:
            return bool(self.registered)

    def reset_call_state(self) -> None:
        with self._lock:
            self.phase = "idle"
            self.lines.clear()

    def cmd(self, line: str, *, force: bool = False) -> bool:
        """Send a linphonec command. Returns False if dropped (CLI not ready)."""
        if not self.alive():
            return False
        low = (line or "").strip().lower()
        # Dial/hangup must never be silently dropped — that left Digivice
        # showing "Ringing" with no INVITE on the wire.
        critical = low.startswith(
            ("call ", "terminate", "hangup", "answer", "decline")
        )
        with self._lock:
            if not force and not critical and (self._auth_prompt or not self._cli_ready):
                _log(f"linphonec drop (not ready): {low.split()[0] if low else '?'}")
                return False
            if critical and not self._cli_ready:
                self._cli_ready = True
                self._auth_prompt = False
        try:
            shown = line.split(maxsplit=1)[0]
            _log(f"linphonec < {shown}")
            payload = (line + "\r\n").encode("utf-8")
            if self._pty is not None:
                os.write(self._pty, payload)
                return True
            proc = self.proc
            if proc is None or proc.stdin is None:
                return False
            proc.stdin.write(line + "\n")
            proc.stdin.flush()
            return True
        except Exception as e:
            _log(f"linphonec cmd failed: {e}")
            return False

    def snapshot(self) -> CallInfo:
        with self._lock:
            raw = "\n".join(list(self.lines)[-8:])
            phase = self.phase
        core = _core_log_call_phase()
        # Prefer a more advanced core-log phase when PTY is quiet
        rank = {
            "idle": 0,
            "ending": 1,
            "error": 2,
            "incoming": 3,
            "dialing": 4,
            "ringing": 5,
            "active": 6,
        }
        if core and rank.get(core, 0) > rank.get(phase, 0):
            phase = core
            with self._lock:
                if rank.get(core, 0) >= rank.get(self.phase, 0):
                    self.phase = core
        return CallInfo(raw=raw, phase=phase, state=phase)

    def stop(self) -> None:
        proc = self.proc
        fd = self._pty
        self.registered = False
        self._rc_key = ""
        if proc is not None and proc.poll() is None:
            try:
                payload = b"quit\r\n"
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
            try:
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
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


def _csh_cmd(*args: str, timeout: float = 8.0, quiet: bool = False) -> str:
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
            if not quiet:
                _log(f"csh {args[:2]!r} err: {e}")
            return str(e)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if quiet:
        return out
    shown = args[0] if args else ""
    if shown == "register" or (len(args) > 1 and args[0] == "generic" and args[1].startswith("register")):
        _log("csh register → (hidden)")
    else:
        _log(f"csh {shown} → {out[:160]}")
    return out


def _csh_call_live(text: str) -> bool:
    """True while SIP still owns a session (ringing, answered, or renegotiating)."""
    s = (text or "").lower()
    if not s.strip():
        return False
    return bool(
        re.search(
            r"(?i)call out|hook=sip:|hook=offhook|hook=dialing|"
            r"duration=\d+|StreamsRunning|OutgoingRinging|"
            r"OutgoingProgress|Establishing call|Calling ",
            s,
        )
    )


def _csh_no_call(text: str) -> bool:
    s = (text or "").lower()
    if _csh_call_live(s):
        return False
    # Empty / unknown: do not treat as hung up (status blips on answer)
    if not s.strip():
        return False
    return (
        ("no active call" in s)
        or ("no active calls" in s)
        or s.strip() in ("no call", "idle")
        or ("hook=onhook" in s)
        or ("hook=on-hook" in s)
    )


def _csh_calls(*, quiet: bool = False) -> str:
    out = _csh_cmd("generic", "states calls", timeout=0.6, quiet=quiet)
    if out.strip() and "unknown" not in out.lower():
        return out
    return _csh_cmd("generic", "calls", timeout=0.6, quiet=quiet)


def _csh_phase(hook: str, calls: str) -> str:
    raw = f"{hook}\n{calls}"
    # linphonec status hook (authoritative):
    #   Call out, duration=N  → outbound StreamsRunning/Connected (ANSWERED)
    #   hook=answered         → inbound answered
    #   hook=ringing          → OutgoingRinging (far end ringing)
    #   hook=dialing          → OutgoingProgress
    # Digivice used to map "Call out" → Ringing, so Connected never appeared.
    if re.search(
        r"(?i)Call out|hook=answered|"
        r"StreamsRunning|LinphoneCallConnected|Call answered",
        raw,
    ):
        return "active"
    if re.search(
        r"(?i)hook=ringing|OutgoingRinging|Remote ringing|LinphoneCallOutgoingRinging",
        raw,
    ):
        return "ringing"
    if re.search(
        r"(?i)hook=dialing|hook=outgoing_init|OutgoingProgress|OutgoingInit|"
        r"Calling |Establishing call|hook=sip:|hook=offhook|in progress",
        raw,
    ):
        return "dialing"
    if re.search(r"(?i)LinphoneCallError|403 Forbidden|404 Not Found|486 Busy", raw):
        return "error"
    if re.search(r"(?i)Call (terminated|ended)|hook=on-?hook|No active calls", raw):
        return "idle"
    return _phase_from_line(hook, _phase_from_line(calls, "idle"))


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
    global _last_register_raw, _active_backend
    hint = _csh_warmup()
    if hint and "Set SIP" in hint:
        return False, hint
    st = _csh_cmd("status", "register")
    _last_register_raw = st[:200]
    if not re.search(r"(?i)registered|identity=", st):
        _csh_warmup()
        st = _csh_cmd("status", "register")
        _last_register_raw = st[:200]
    # Kill any leftover call so we never stack INVITEs (multi-ring on the cell).
    _csh_cmd("generic", "terminate", timeout=2.0, quiet=True)
    _csh_cmd("hangup", timeout=2.0, quiet=True)
    time.sleep(0.35)
    # ONE dial only. E.164 for Zadarma PSTN. Fallbacks used to place 2–3 calls.
    target = f"sip:+{digits}@{server}" if digits.isdigit() else _call_uri(digits, server)
    _log(f"csh dial once {target}")
    dial_out = _csh_cmd("dial", target)
    time.sleep(0.8)
    hook = _csh_cmd("status", "hook", timeout=2.0, quiet=True)
    # If first form didn't start, hangup then try plain sip:digits@host once
    if _csh_no_call(hook) and not re.search(
        r"(?i)Establishing call|in progress|assigned id|Call out", dial_out or ""
    ):
        target2 = _call_uri(digits, server)
        if target2 != target:
            _log(f"csh dial once fallback {target2}")
            _csh_cmd("generic", "terminate", timeout=2.0, quiet=True)
            dial_out = _csh_cmd("dial", target2)
            time.sleep(0.8)
            hook = _csh_cmd("status", "hook", timeout=2.0, quiet=True)
    phase = _csh_phase(hook, "")
    if phase == "idle":
        phase = _phase_from_line(dial_out or "", "idle")
    blob = f"{dial_out}\n{hook}"
    if phase in ("dialing", "ringing", "active") or re.search(
        r"(?i)Establishing call|in progress|assigned id|Call out|hook=sip:",
        blob,
    ):
        _active_backend = "csh"
        with _csh_poll_lock:
            _csh_poll_info = CallInfo(phase="dialing", state="dialing", raw=blob[:200])
        _ensure_csh_poller()
        _set_error("")
        _log("csh outbound call started (single INVITE)")
        return True, ""
    _log(f"csh: no outbound call (hook={hook[:80]!r})")
    return False, _set_error("Call did not start — try Test SIP")


def _core_log_size() -> int:
    try:
        return _CORE_LOG.stat().st_size if _CORE_LOG.is_file() else 0
    except OSError:
        return 0


def _core_log_since(mark: int) -> str:
    try:
        if not _CORE_LOG.is_file():
            return ""
        with _CORE_LOG.open("rb") as f:
            f.seek(max(0, mark))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _fresh_has_invite(mark: int) -> bool:
    return bool(re.search(r"(?i)\bINVITE\s+sip:", _core_log_since(mark)))


def _wake_linphonec_cli(eng: "LinphoneEngine") -> None:
    """Nudge readline so the next call command is accepted."""
    try:
        if eng._pty is not None:
            os.write(eng._pty, b"\r\n")
        elif eng.proc is not None and eng.proc.stdin is not None:
            eng.proc.stdin.write("\n")
            eng.proc.stdin.flush()
    except Exception:
        pass
    with eng._lock:
        eng._cli_ready = True
        eng._auth_prompt = False
    time.sleep(0.25)


def _wait_call_progress(
    eng: "LinphoneEngine", log_mark: int, timeout_s: float
) -> Tuple[str, str]:
    """Return (phase|'' , error_msg). phase set on success."""
    deadline = time.time() + max(1.0, timeout_s)
    while time.time() < deadline:
        if not eng.alive():
            return "", "linphonec died after dial"
        if _fresh_has_invite(log_mark):
            with eng._lock:
                eng.phase = "dialing"
            return "dialing", ""
        info = eng.snapshot()
        if info.phase in ("dialing", "ringing", "active"):
            return info.phase, ""
        if info.phase == "error":
            return "", _core_log_call_error() or "Call rejected"
        fresh = _core_log_since(log_mark)
        if fresh and re.search(
            r"(?i)SIP/2\.0\s+(402|403|404|408|480|486|603)\b", fresh
        ) and re.search(r"(?i)INVITE", fresh):
            return "", _core_log_call_error() or "Call rejected"
        time.sleep(0.2)
    return "", ""


def dial(number: str) -> bool:
    ok, _ = dial_ex(number)
    return ok


def dial_ex(number: str) -> Tuple[bool, str]:
    try:
        return _dial_ex_inner(number)
    except Exception as e:
        _log(f"dial_ex crashed: {e}")
        try:
            write_sip_report(extra=f"dial_ex crashed:\n{traceback.format_exc()}")
        except Exception:
            pass
        return False, _set_error(f"Dial failed: {e}")


def _dial_ex_inner(number: str) -> Tuple[bool, str]:
    global _last_register_raw, _active_backend
    _active_backend = None
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

    # Prefer linphonecsh for outbound. PTY linphonec registers but often
    # never emits INVITE; two linphonecs also fight for :5060.
    if _discover_csh():
        eng = _engine()
        if eng.alive():
            _log("stopping PTY linphonec before csh dial")
            eng.stop()
            time.sleep(0.35)
        _kill_stray_linphone()
        ok, reason = _dial_via_csh(digits, server)
        if ok:
            return True, ""
        return False, reason or _set_error("Call did not start")

    target = _call_uri(digits, server)
    if _discover_linphonec():
        hint = _engine().start()
        if hint:
            return False, hint
        eng = _engine()
        if not eng.alive() or not eng.registered:
            return False, _set_error(
                hint or "SIP not registered — check Wi‑Fi / Accounts"
            )
        eng.reset_call_state()
        _wake_linphonec_cli(eng)
        log_mark = _core_log_size()
        _log(f"call try {digits}")
        eng.cmd(f"call {digits}", force=True)
        phase, err = _wait_call_progress(eng, log_mark, 8.0)
        if not phase:
            log_mark = _core_log_size()
            eng.cmd(f"call {target}", force=True)
            phase, err = _wait_call_progress(eng, log_mark, 8.0)
        if phase:
            _active_backend = "pty"
            _last_register_raw = "registered"
            _set_error("")
            return True, ""
        if err:
            return False, _set_error(err)
        return False, _set_error(_core_log_call_error() or "No ringback")

    return False, _set_error(missing_hint())


def hangup() -> None:
    global _active_backend
    if _active_backend == "csh" or _discover_csh():
        _csh_cmd("generic", "terminate", timeout=3.0)
        _csh_cmd("hangup", timeout=3.0)
    eng = _engine()
    if eng.alive():
        eng.cmd("terminate", force=True)
        eng.cmd("hangup", force=True)
        eng.phase = "idle"
    _active_backend = None


def answer() -> None:
    if _active_backend == "csh" or (
        not _engine().alive() and _discover_csh()
    ):
        _csh_cmd("answer", timeout=3.0)
        _csh_cmd("generic", "answer", timeout=3.0)
        return
    eng = _engine()
    if eng.alive():
        eng.cmd("answer", force=True)
        return
    if _discover_csh():
        _csh_cmd("answer", timeout=3.0)


def _ensure_csh_poller() -> None:
    """Background poller so Qt never blocks on linphonecsh (kills CardKB/UI)."""
    global _csh_poll_thread

    def loop() -> None:
        global _active_backend, _csh_poll_info, _csh_idle_streak
        while not _csh_poll_stop.is_set():
            if _active_backend != "csh":
                _csh_idle_streak = 0
                _csh_poll_stop.wait(0.4)
                continue
            try:
                hook = _csh_cmd("status", "hook", timeout=0.5, quiet=True)
                # Empty/failed status: keep last poll (answer renegotiation)
                if not (hook or "").strip():
                    _csh_poll_stop.wait(0.8)
                    continue
                # Cheap backup: states calls often shows StreamsRunning when hook is quiet
                calls = ""
                if not re.search(r"(?i)Call out|hook=answered|hook=ringing", hook):
                    calls = _csh_cmd(
                        "generic", "states calls", timeout=0.5, quiet=True
                    )
                phase = _csh_phase(hook, calls)
                live = _csh_call_live(hook) or _csh_call_live(calls)
                # Answer / media can briefly look idle — need sustained no-call
                if live:
                    _csh_idle_streak = 0
                    if not phase or phase == "idle":
                        phase = "dialing"
                elif _csh_no_call(hook) or phase == "idle":
                    _csh_idle_streak += 1
                    if _csh_idle_streak < 4:
                        with _csh_poll_lock:
                            prev = _csh_poll_info
                        phase = (
                            prev.phase
                            if prev is not None and prev.phase not in ("idle", "ending")
                            else "dialing"
                        )
                    else:
                        phase = "idle"
                        _active_backend = None
                        _csh_idle_streak = 0
                else:
                    _csh_idle_streak = 0
                    if not phase or phase == "idle":
                        phase = "dialing"
                info = CallInfo(
                    raw=(hook + ("\n" + calls if calls else ""))[:400],
                    phase=phase,
                    state=phase,
                )
                with _csh_poll_lock:
                    _csh_poll_info = info
            except Exception:
                pass
            _csh_poll_stop.wait(0.8)

    if _csh_poll_thread is not None and _csh_poll_thread.is_alive():
        return
    _csh_poll_stop.clear()
    _csh_poll_thread = threading.Thread(target=loop, name="csh-poll", daemon=True)
    _csh_poll_thread.start()


def poll() -> CallInfo:
    """Non-blocking UI poll — never run linphonecsh on the Qt thread."""
    global _active_backend
    if _active_backend == "csh":
        _ensure_csh_poller()
        with _csh_poll_lock:
            info = _csh_poll_info
        if info is None:
            return CallInfo(phase="dialing", state="dialing")
        return info
    eng = _engine()
    if eng.alive():
        return eng.snapshot()
    return CallInfo()


def _sudo_ensure_linphone(timeout: float = 300.0) -> str:
    """Install/find real linphonecsh. Digivice has passwordless sudo for this."""
    cmds = (
        ["sudo", "-n", "digivice-ensure-linphone", "--debs"],
        ["sudo", "-n", "/usr/local/bin/digivice-ensure-linphone", "--debs"],
        ["sudo", "-n", "bash", "/usr/local/bin/digivice-ensure-linphone", "--debs"],
        ["sudo", "-n", "/opt/esp-handset/session/ensure-linphone.sh", "--debs"],
        ["sudo", "-n", "bash", "/opt/esp-handset/session/ensure-linphone.sh", "--debs"],
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


def doctor(*, save_report: bool = True) -> str:
    """Start linphonec if needed and report whether Zadarma REGISTER succeeded."""
    env = _sip_env()
    user = (env.get("SIP_USER") or "").strip() or "?"
    server = (env.get("SIP_SERVER") or "").strip() or "?"
    password = (env.get("SIP_PASS") or "").strip()
    _bust_voip_cache()
    if _is_placeholder_sip_pass(password):
        lines = [
            "RESULT: NEED PASSWORD",
            f"sip: {user}@{server}",
            "Enter your Zadarma SIP extension password above, then Save SIP.",
            "Use the password from Zadarma → SIP extension — not the website login.",
            f"env-from: {sip_env_source() or '?'}",
            f"pass-len: {len(password)}",
        ]
        text = "\n".join(lines)
        if save_report:
            try:
                write_sip_report(extra=text)
            except Exception:
                pass
        return text
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
    blocked = _zadarma_block_reason()
    lines = [
        f"linphonec: {lp or 'MISSING'}",
        f"linphonecsh: {csh or 'MISSING'}",
        f"sip: {user}@{server}",
        f"env-from: {sip_env_source() or '?'}",
        f"pass-len: {len(password)}",
    ]
    if blocked:
        lines.append(blocked)
    broken = _broken_linphonec_msg()
    if not lp:
        _kick_voip_install(force=True)
        if broken:
            lines.insert(0, "RESULT: VOIP BROKEN")
            lines.append(broken.replace("\n", " ")[:220])
            lines.append("Repairing: Debian Trixie linphone (not sid).")
        else:
            lines.insert(0, "RESULT: INSTALLING VOIP")
            lines.append("Installing linphone-cli in the background.")
        lines.append("Wait about a minute, then Test SIP again.")
        lines.append("--- log ---")
        lines.append(recent_log(8))
        return "\n".join(lines)
    if lp:
        _DISC["linphonec"] = (lp, time.time())
    if csh:
        _DISC["csh"] = (csh, time.time())

    hint = ensure()
    eng = _engine()
    lines.append(f"proc: {'up' if eng.alive() else 'down'}")
    lines.append(f"cli-registered: {eng.registered}")
    if hint:
        lines.append(hint)
    if _last_error and _last_error not in lines:
        lines.append(f"last: {_last_error}")

    # linphonec is the real engine. Do not ask linphonecsh — that daemon
    # fights for UDP/5060 and reports "not running" even when we are registered.
    if lp:
        result = "REGISTERED" if eng.alive() and eng.registered else "NOT REGISTERED"
    else:
        st = _csh_cmd("status", "register", timeout=3.0)
        compact = (st or "").replace("\n", " ").strip()
        if re.search(r"(?i)linphonecsh not found", compact):
            threading.Thread(
                target=_install_voip_bg, name="voip-apt", daemon=True
            ).start()
            result = "INSTALLING VOIP"
            lines.append("wrapper could not find real linphonecsh")
        elif compact:
            lines.append(f"register: {compact[:140]}")
            ok = _text_registered(compact)
            result = "REGISTERED" if ok is True else "NOT REGISTERED"
        else:
            result = "NOT REGISTERED"

    if result == "NOT REGISTERED" and blocked:
        result = "ZADARMA LOCKED"
    elif result == "NOT REGISTERED" and not blocked:
        try:
            core = _CORE_LOG.read_text(encoding="utf-8", errors="replace")[-4000:]
            if re.search(r"(?i)Blocked for incorrect passwords", core):
                result = "ZADARMA LOCKED"
                lines.append(
                    "Zadarma server lockout — not a wrong-password error on this attempt. "
                    "Contact Zadarma support to unlock extension, then Test SIP once."
                )
            elif re.search(r"(?i)403 Forbidden|Unauthorized", core):
                lines.append(
                    "Zadarma rejected the login. Check SIP extension password in Zadarma, "
                    "enter it in Settings, Save SIP, then Test SIP."
                )
        except OSError:
            pass
    if blocked and result != "REGISTERED":
        result = "ZADARMA LOCKED"
        eng.stop()
    lines.insert(0, f"RESULT: {result}")
    lines.append("--- log ---")
    lines.append(recent_log(10))
    try:
        if _CORE_LOG.is_file():
            core_tail = _CORE_LOG.read_text(encoding="utf-8", errors="replace")[-2500:]
            core_tail = _redact(core_tail)
            for ln in core_tail.splitlines()[-8:]:
                if re.search(
                    r"(?i)register|403|401|blocked|forbidden|unauthorized|registration",
                    ln,
                ):
                    lines.append(f"core: {ln[:160]}")
    except OSError:
        pass
    text = "\n".join(lines)
    if save_report:
        try:
            write_sip_report(extra=text)
        except Exception:
            pass
    return text


def remote_number(remote: str) -> str:
    s = (remote or "").strip()
    if s.lower().startswith("sip:"):
        s = s[4:]
    if "@" in s:
        s = s.split("@", 1)[0]
    return s.strip()
