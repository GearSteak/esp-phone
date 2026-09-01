"""Digivice Wi‑Fi file transfer — send to Digivice or download from Digivice."""

from __future__ import annotations

import html
import mimetypes
import os
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urlparse

from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from esp_handset.pages import page_chrome

DATA = Path.home() / ".esp-handset"
PHOTOS = Path.home() / "Pictures" / "phone"
UPLOAD_PORT = 8765

# dest_key → (label, folder, allowed suffixes or None = common docs/media)
# Digivice row stays Photos / ROMs / Files; the web form lists every console.
_ROM_SYSTEMS: Tuple[Tuple[str, str, str, Tuple[str, ...]], ...] = (
    ("rom_gb", "Game Boy", "gb", (".gb", ".gbc", ".sgb")),
    ("rom_nes", "NES", "nes", (".nes", ".fds", ".unf", ".unif")),
    ("rom_sms", "SMS / GG", "sms", (".sms", ".gg", ".sg")),
)

_ROM_EXTS = tuple(
    dict.fromkeys(ext for _k, _l, _f, exts in _ROM_SYSTEMS for ext in exts)
)
_ROM_FOLDER = {
    ext: folder for _k, _l, folder, exts in _ROM_SYSTEMS for ext in exts
}
_ROM_ZIP = (".zip",)

DESTINATIONS: Dict[str, Tuple[str, Path, Optional[Tuple[str, ...]]]] = {
    "photos": (
        "Photos",
        PHOTOS,
        (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"),
    ),
    "roms": (
        "ROMs · auto",
        DATA / "roms",
        _ROM_EXTS,
    ),
}
for _rk, _rl, _rf, _re in _ROM_SYSTEMS:
    DESTINATIONS[_rk] = (_rl, DATA / "roms" / _rf, _re + _ROM_ZIP)
DESTINATIONS["files"] = (
    "Files",
    DATA / "inbox",
    None,
)

DIGI_DEST_KEYS = ("photos", "roms", "files")

_FILES_OK = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".gif",
    ".txt",
    ".md",
    ".pdf",
    ".zip",
    ".gb",
    ".gbc",
    ".sgb",
    ".nes",
    ".fds",
    ".unf",
    ".sms",
    ".gg",
    ".sg",
    ".mp3",
    ".wav",
    ".ogg",
    ".json",
    ".csv",
)

_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

_ROM_ACCEPT = ",".join(_ROM_EXTS + _ROM_ZIP)

_MAX_UPLOAD = 512 * 1024 * 1024  # 512 MiB — Shadowdark PDF / large ROMs


def _rom_folder_for(name: str) -> Path:
    sub = _ROM_FOLDER.get(Path(name).suffix.lower(), "gb")
    return DATA / "roms" / sub


def _dest_folder(dest_key: str, filename: str) -> Path:
    """Folder to write into — auto ROMs split by extension."""
    _label, folder, _allowed = DESTINATIONS[dest_key]
    if dest_key == "roms":
        return _rom_folder_for(filename)
    return folder


def _ext_hint(allowed: Optional[Tuple[str, ...]]) -> str:
    if not allowed:
        return "docs / media"
    return " ".join(allowed[:6])

MODEM_REPORT = DATA / "modem-doctor.txt"
MODEM_REPORT_TMP = Path("/tmp/digivice-modem-doctor.txt")
AUDIO_REPORT = DATA / "audio-doctor.txt"
AUDIO_REPORT_TMP = Path("/tmp/digivice-audio-doctor.txt")
MEDIA_REPORT = DATA / "media-doctor.txt"
MEDIA_REPORT_TMP = Path("/tmp/digivice-media-doctor.txt")
I2C_REPORT = DATA / "i2c-doctor.txt"
I2C_REPORT_TMP = Path("/tmp/digivice-i2c-doctor.txt")
MOUSE_REPORT = DATA / "mouse-doctor.txt"
MOUSE_REPORT_TMP = Path("/tmp/digivice-mouse-doctor.txt")
HELTEC_REPORT = DATA / "heltec-doctor.txt"
HELTEC_REPORT_TMP = Path("/tmp/digivice-heltec-doctor.txt")
SIP_REPORT = DATA / "sip-doctor.txt"
SIP_REPORT_TMP = Path("/tmp/digivice-sip-doctor.txt")


def _modem_report_path() -> Optional[Path]:
    for p in (MODEM_REPORT, MODEM_REPORT_TMP, Path.home() / "esp-phone" / "modem-doctor-LATEST.txt"):
        try:
            if p.is_file() and p.stat().st_size > 0:
                return p
        except OSError:
            continue
    return None


def _audio_report_path() -> Optional[Path]:
    for p in (AUDIO_REPORT, AUDIO_REPORT_TMP, Path.home() / "esp-phone" / "audio-doctor-LATEST.txt"):
        try:
            if p.is_file() and p.stat().st_size > 0:
                return p
        except OSError:
            continue
    return None


def _media_report_path() -> Optional[Path]:
    for p in (MEDIA_REPORT, MEDIA_REPORT_TMP, Path.home() / "esp-phone" / "media-doctor-LATEST.txt"):
        try:
            if p.is_file() and p.stat().st_size > 0:
                return p
        except OSError:
            continue
    return None


def _i2c_report_path() -> Optional[Path]:
    for p in (I2C_REPORT, I2C_REPORT_TMP, Path.home() / "esp-phone" / "i2c-doctor-LATEST.txt"):
        try:
            if p.is_file() and p.stat().st_size > 0:
                return p
        except OSError:
            continue
    return None


def _mouse_report_path() -> Optional[Path]:
    for p in (MOUSE_REPORT, MOUSE_REPORT_TMP, Path.home() / "esp-phone" / "mouse-doctor-LATEST.txt"):
        try:
            if p.is_file() and p.stat().st_size > 0:
                return p
        except OSError:
            continue
    return None


def _heltec_report_path() -> Optional[Path]:
    for p in (HELTEC_REPORT, HELTEC_REPORT_TMP, Path.home() / "esp-phone" / "heltec-doctor-LATEST.txt"):
        try:
            if p.is_file() and p.stat().st_size > 0:
                return p
        except OSError:
            continue
    return None


def _cart_video_path() -> Optional[Path]:
    """Pick a mounted cart video so Prep can include ffprobe details."""
    try:
        from esp_handset.cartridge import refresh

        state = refresh(force=True)
        cart = state.cart
        if cart is None:
            return None
        for movie in cart.movies:
            if movie.path.is_file():
                return movie.path
        for show in cart.tv:
            for season in show.seasons:
                for episode in season.episodes:
                    if episode.path.is_file():
                        return episode.path
    except Exception:
        pass
    return None


def _refresh_media_report() -> Tuple[bool, str]:
    video = _cart_video_path()
    commands = [["digivice-media-doctor"]]
    if video is not None:
        commands[0].append(str(video))
    commands += [
        ["sudo", "-n", *commands[0]],
        ["bash", "/opt/esp-handset/session/digivice-media-doctor.sh"]
        + ([str(video)] if video is not None else []),
    ]
    last = "doctor not installed"
    for cmd in commands:
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if r.returncode == 0 or _media_report_path() is not None:
                p = _media_report_path()
                return True, f"Report ready ({p.name if p else 'ok'})"
            last = (r.stderr or r.stdout or last).strip()[:100] or last
        except FileNotFoundError:
            continue
        except Exception as e:
            last = str(e)[:100]
    p = _media_report_path()
    if p is not None:
        return True, f"Using existing {p.name}"
    return False, last


def _refresh_i2c_report() -> Tuple[bool, str]:
    cmds = (
        ["digivice-i2c-doctor"],
        ["sudo", "-n", "digivice-i2c-doctor"],
        ["bash", "/opt/esp-handset/session/digivice-i2c-doctor.sh"],
    )
    last = "doctor not installed"
    for cmd in cmds:
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            if r.returncode == 0 or _i2c_report_path() is not None:
                p = _i2c_report_path()
                return True, f"Report ready ({p.name if p else 'ok'})"
            last = (r.stderr or r.stdout or last).strip()[:80] or last
        except FileNotFoundError:
            continue
        except Exception as e:
            last = str(e)[:80]
    p = _i2c_report_path()
    if p is not None:
        return True, f"Using existing {p.name}"
    return False, last


def _refresh_mouse_report() -> Tuple[bool, str]:
    cmds = (
        ["digivice-mouse-doctor"],
        ["sudo", "-n", "digivice-mouse-doctor"],
        ["bash", "/opt/esp-handset/session/digivice-mouse-doctor.sh"],
    )
    last = "doctor not installed"
    for cmd in cmds:
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            if r.returncode == 0 or _mouse_report_path() is not None:
                p = _mouse_report_path()
                return True, f"Report ready ({p.name if p else 'ok'})"
            last = (r.stderr or r.stdout or last).strip()[:80] or last
        except FileNotFoundError:
            continue
        except Exception as e:
            last = str(e)[:80]
    p = _mouse_report_path()
    if p is not None:
        return True, f"Using existing {p.name}"
    return False, last


def _refresh_heltec_report() -> Tuple[bool, str]:
    # Never --restart / --fix here — that kills Digivice while Transfer is open.
    env = os.environ.copy()
    env["DIGIVICE_HELTEC_APT_ONLY"] = "1"
    env["DIGIVICE_ENSURE_HELTEC_NO_RESTART"] = "1"
    cmds = (
        ["sudo", "-n", "digivice-heltec-doctor"],
        ["sudo", "-n", "digivice-ensure-heltec", "--doctor"],
        ["bash", "/opt/esp-handset/session/digivice-heltec-doctor.sh"],
    )
    last = "doctor not installed"
    for cmd in cmds:
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
                env=env,
            )
            if r.returncode == 0 or _heltec_report_path() is not None:
                p = _heltec_report_path()
                return True, f"Report ready ({p.name if p else 'ok'})"
            last = (r.stderr or r.stdout or last).strip()[:80] or last
        except FileNotFoundError:
            continue
        except Exception as e:
            last = str(e)[:80]
    p = _heltec_report_path()
    if p is not None:
        return True, f"Using existing {p.name}"
    return False, last


def _refresh_modem_report() -> Tuple[bool, str]:
    """Run digivice-modem-doctor if available; return (ok, message)."""
    cmds = (
        ["digivice-modem-doctor"],
        ["sudo", "-n", "digivice-modem-doctor"],
        ["bash", "/opt/esp-handset/session/digivice-modem-doctor.sh"],
    )
    last = "doctor not installed"
    for cmd in cmds:
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            if r.returncode == 0 or _modem_report_path() is not None:
                p = _modem_report_path()
                return True, f"Report ready ({p.name if p else 'ok'})"
            last = (r.stderr or r.stdout or last).strip()[:80] or last
        except FileNotFoundError:
            continue
        except Exception as e:
            last = str(e)[:80]
    p = _modem_report_path()
    if p is not None:
        return True, f"Using existing {p.name}"
    return False, last


def _refresh_audio_report() -> Tuple[bool, str]:
    cmds = (
        ["digivice-audio-doctor"],
        ["sudo", "-n", "digivice-audio-doctor"],
        ["bash", "/opt/esp-handset/session/digivice-audio-doctor.sh"],
    )
    last = "doctor not installed"
    for cmd in cmds:
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if r.returncode == 0 or _audio_report_path() is not None:
                p = _audio_report_path()
                return True, f"Report ready ({p.name if p else 'ok'})"
            last = (r.stderr or r.stdout or last).strip()[:80] or last
        except FileNotFoundError:
            continue
        except Exception as e:
            last = str(e)[:80]
    p = _audio_report_path()
    if p is not None:
        return True, f"Using existing {p.name}"
    return False, last


def _sip_report_path() -> Optional[Path]:
    for p in (
        SIP_REPORT,
        SIP_REPORT_TMP,
        DATA / "inbox" / "sip-doctor.txt",
        Path.home() / "esp-phone" / "sip-doctor-LATEST.txt",
    ):
        try:
            if p.is_file() and p.stat().st_size > 0:
                return p
        except OSError:
            continue
    return None


def _refresh_sip_report() -> Tuple[bool, str]:
    try:
        from esp_handset import sip_call

        # run_doctor=False — full doctor() restarts VoIP and can OOM/crash Digivice
        path = sip_call.write_sip_report(run_doctor=False)
        if path.is_file() and path.stat().st_size > 0:
            return True, f"Report ready ({path.name})"
        return False, "sip report empty"
    except Exception as e:
        p = _sip_report_path()
        if p is not None:
            return True, f"Using existing {p.name}"
        return False, str(e)[:80]


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        for tok in (r.stdout or "").split():
            if tok.count(".") == 3 and not tok.startswith("127."):
                return tok
    except Exception:
        pass
    return "0.0.0.0"


def _safe_name(name: str, allowed: Optional[Tuple[str, ...]]) -> Optional[str]:
    base = Path(unquote(name or "")).name
    if not base or base in (".", ".."):
        return None
    ext = Path(base).suffix.lower()
    if allowed is not None:
        if ext not in allowed:
            return None
    else:
        if ext not in _FILES_OK:
            return None
    safe = "".join(c for c in base if c.isalnum() or c in "._- ()[]")
    if not safe or Path(safe).suffix.lower() != ext:
        return None
    return safe


def _list_folder(dest_key: str) -> List[Path]:
    if dest_key not in DESTINATIONS:
        return []
    _label, folder, allowed = DESTINATIONS[dest_key]
    roots = [folder]
    if dest_key == "roms":
        roots = [folder / sub for sub in ("gb", "nes", "sms")]
        roots.append(folder)
    out: List[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for p in root.iterdir():
                if not p.is_file():
                    continue
                if p.name.upper() == "README.TXT":
                    continue
                if _safe_name(p.name, allowed) is None:
                    continue
                out.append(p)
        except OSError:
            continue
    out.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return out


def _resolve_file(dest_key: str, name: str) -> Optional[Path]:
    if dest_key not in DESTINATIONS:
        return None
    _label, folder, allowed = DESTINATIONS[dest_key]
    safe = _safe_name(name, allowed)
    if not safe:
        return None
    candidates = [folder / safe]
    if dest_key == "roms":
        candidates.insert(0, _rom_folder_for(safe) / safe)
        for sub in ("gb", "nes", "sms"):
            candidates.append(folder / sub / safe)
    try:
        folder_r = folder.resolve()
    except OSError:
        return None
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if not str(resolved).startswith(str(folder_r)):
            continue
        if resolved.is_file():
            return resolved
    return None


class _UploadSignals(QObject):
    got_file = pyqtSignal(str)
    failed = pyqtSignal(str)
    activity = pyqtSignal(str)
    prep_done = pyqtSignal(bool, str)


def _parse_multipart(content_type: str, body: bytes):
    """Return (dest_key, [(filename, bytes), ...])."""
    if "multipart/form-data" not in content_type or "boundary=" not in content_type:
        return None, []
    boundary = content_type.split("boundary=", 1)[-1].strip().encode("ascii", "ignore")
    if not boundary:
        return None, []
    dest_key = None
    files: List[Tuple[str, bytes]] = []
    for part in body.split(b"--" + boundary):
        if b"Content-Disposition" not in part:
            continue
        header, _, data = part.partition(b"\r\n\r\n")
        if not data:
            continue
        if data.endswith(b"\r\n"):
            data = data[:-2]
        hdr = header.decode("utf-8", "replace")
        if 'name="dest"' in hdr and "filename=" not in hdr:
            dest_key = data.decode("utf-8", "replace").strip()
            continue
        if 'name="file"' in hdr or 'name="rom"' in hdr:
            filename = "upload.bin"
            for line in header.split(b"\r\n"):
                if b"filename=" in line:
                    try:
                        raw = line.decode("utf-8", "replace")
                        filename = raw.split("filename=", 1)[-1].strip().strip('"')
                    except Exception:
                        filename = "upload.bin"
            if filename and data:
                files.append((filename, data))
    return dest_key, files


_CSS = """
body{font-family:sans-serif;background:#0b1a2a;color:#e8eef5;padding:16px;max-width:520px;margin:0 auto;}
h1{font-size:1.25rem;margin:0 0 8px;}
h2{font-size:1.05rem;margin:18px 0 8px;}
.box{background:#152030;padding:16px;border-radius:8px;margin-bottom:12px;}
label{display:block;margin-top:10px;font-size:0.9rem;color:#9ab;}
input,select,button{font-size:1rem;padding:10px;margin-top:6px;width:100%;box-sizing:border-box;}
button,.btn{display:inline-block;background:#1f6feb;color:#fff;border:0;font-weight:700;margin-top:14px;
  text-decoration:none;text-align:center;padding:10px;border-radius:4px;}
a{color:#9cf;}
.muted{color:#9ab;font-size:0.85rem;}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
.card{background:#152030;padding:8px;border-radius:8px;text-align:center;}
.card img{max-width:100%;max-height:140px;border-radius:4px;background:#000;}
.card a{display:block;margin-top:6px;font-size:0.8rem;word-break:break-all;}
ul.files{list-style:none;padding:0;margin:0;}
ul.files li{padding:8px 0;border-bottom:1px solid #243040;}
nav a{margin-right:10px;}
"""


def _make_handler(get_dest: Callable[[], str], signals: _UploadSignals):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = unquote(parsed.path or "/")

            if path in ("/", "/index.html"):
                self._page_home()
                return
            if path.startswith("/browse/"):
                key = path[len("/browse/") :].strip("/").split("/")[0]
                self._page_browse(key)
                return
            if path.startswith("/file/"):
                parts = path[len("/file/") :].strip("/").split("/", 1)
                if len(parts) != 2:
                    self.send_error(404)
                    return
                self._serve_file(parts[0], parts[1], inline=False)
                return
            if path.startswith("/view/"):
                parts = path[len("/view/") :].strip("/").split("/", 1)
                if len(parts) != 2:
                    self.send_error(404)
                    return
                self._serve_file(parts[0], parts[1], inline=True)
                return
            if path in ("/diag/modem", "/diag/modem.txt", "/modem-doctor.txt"):
                self._serve_modem_report(download=path.endswith(".txt"))
                return
            if path in ("/diag/audio", "/diag/audio.txt", "/audio-doctor.txt"):
                self._serve_audio_report(download=path.endswith(".txt"))
                return
            if path in ("/diag/media", "/diag/media.txt", "/media-doctor.txt"):
                self._serve_media_report(download=path.endswith(".txt"))
                return
            if path in ("/diag/i2c", "/diag/i2c.txt", "/i2c-doctor.txt"):
                self._serve_i2c_report(download=path.endswith(".txt"))
                return
            if path in ("/diag/mouse", "/diag/mouse.txt", "/mouse-doctor.txt"):
                self._serve_mouse_report(download=path.endswith(".txt"))
                return
            if path in ("/diag/heltec", "/diag/heltec.txt", "/heltec-doctor.txt"):
                self._serve_heltec_report(download=path.endswith(".txt"))
                return
            if path in ("/diag/sip", "/diag/sip.txt", "/sip-doctor.txt"):
                self._serve_sip_report(download=path.endswith(".txt"))
                return
            if path in ("/diag/beep", "/diag/beep.txt", "/last-beep.txt"):
                beep = Path.home() / ".esp-handset" / "last-beep.txt"
                if not beep.is_file():
                    msg = (
                        b"No last-beep.txt yet.\n"
                        b"Run Settings -> Debug -> BEEP first.\n"
                    )
                    self.send_response(404)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(msg)))
                    self.end_headers()
                    self.wfile.write(msg)
                    return
                raw = beep.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                if path.endswith(".txt"):
                    self.send_header(
                        "Content-Disposition",
                        'attachment; filename="last-beep.txt"',
                    )
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            self.send_error(404)

        def _html(self, title: str, inner: str) -> None:
            body = f"""<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_CSS}</style></head><body>
{inner}
</body></html>"""
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _page_home(self) -> None:
            cur = get_dest()
            opts = []
            for key, (label, _folder, allowed) in DESTINATIONS.items():
                sel = " selected" if key == cur else ""
                hint = _ext_hint(allowed)
                opts.append(
                    f'<option value="{key}"{sel}>{html.escape(label)} — {html.escape(hint)}</option>'
                )
            browse_links = []
            for key, (label, folder, _) in DESTINATIONS.items():
                n = len(_list_folder(key))
                browse_links.append(
                    f'<a class="btn" style="margin-top:8px;display:block;" href="/browse/{key}">'
                    f"Get {html.escape(label)} ({n})</a>"
                )
            rom_help = " · ".join(
                f"{lab} ({' '.join(exts[:4])})" for _k, lab, _f, exts in _ROM_SYSTEMS
            )
            report = _modem_report_path()
            if report is not None:
                try:
                    when = time.strftime(
                        "%Y-%m-%d %H:%M", time.localtime(report.stat().st_mtime)
                    )
                    diag_note = f"Ready · {html.escape(when)}"
                except OSError:
                    diag_note = "Ready"
            else:
                diag_note = "Run Prep on Digivice first (or open after full-update)"
            media_report = _media_report_path()
            if media_report is not None:
                try:
                    media_note = f"Ready · {html.escape(time.strftime('%Y-%m-%d %H:%M', time.localtime(media_report.stat().st_mtime)))}"
                except OSError:
                    media_note = "Ready"
            else:
                media_note = "Run Prep media report on Digivice first"
            i2c_report = _i2c_report_path()
            if i2c_report is not None:
                try:
                    i2c_note = f"Ready · {html.escape(time.strftime('%Y-%m-%d %H:%M', time.localtime(i2c_report.stat().st_mtime)))}"
                except OSError:
                    i2c_note = "Ready"
            else:
                i2c_note = "Run Prep I2C report on Digivice first"
            mouse_report = _mouse_report_path()
            if mouse_report is not None:
                try:
                    mouse_note = f"Ready · {html.escape(time.strftime('%Y-%m-%d %H:%M', time.localtime(mouse_report.stat().st_mtime)))}"
                except OSError:
                    mouse_note = "Ready"
            else:
                mouse_note = "Run Prep mouse report on Digivice first"
            heltec_report = _heltec_report_path()
            if heltec_report is not None:
                try:
                    heltec_note = f"Ready · {html.escape(time.strftime('%Y-%m-%d %H:%M', time.localtime(heltec_report.stat().st_mtime)))}"
                except OSError:
                    heltec_note = "Ready"
            else:
                heltec_note = "Run Prep Heltec report on Digivice first"
            inner = f"""
<nav><a href="/">Home</a></nav>
<h1>Digivice · Transfer</h1>
<p class="muted">Same Wi‑Fi. Send files to Digivice, or download photos/files to this computer.</p>

<div class="box">
<h2>SIP / call report</h2>
<p class="muted">Paste sip-doctor.txt into Cursor. Passwords are stripped.</p>
<a class="btn" style="display:block;" href="/diag/sip.txt">Download sip-doctor.txt</a>
<a style="display:block;margin-top:8px;" href="/diag/sip">View in browser</a>
</div>

<div class="box">
<h2>Modem doctor</h2>
<p class="muted">{diag_note} · no SIM is OK for AT/GPS tests</p>
<a class="btn" style="display:block;" href="/diag/modem.txt">Download modem-doctor.txt</a>
<a style="display:block;margin-top:8px;" href="/diag/modem">View in browser</a>
<a class="btn" style="margin-top:10px;display:block;" href="/diag/audio.txt">Download audio-doctor.txt</a>
<a class="btn" style="margin-top:10px;display:block;" href="/diag/media.txt">Download media-doctor.txt</a>
<p class="muted">{media_note}</p>
<a class="btn" style="margin-top:10px;display:block;" href="/diag/i2c.txt">Download i2c-doctor.txt</a>
<p class="muted">{i2c_note}</p>
<a class="btn" style="margin-top:10px;display:block;" href="/diag/mouse.txt">Download mouse-doctor.txt</a>
<p class="muted">{mouse_note}</p>
<a class="btn" style="margin-top:10px;display:block;" href="/diag/heltec.txt">Download heltec-doctor.txt</a>
<p class="muted">{heltec_note}</p>
<a class="btn" style="margin-top:10px;display:block;" href="/diag/beep.txt">Download last-beep.txt</a>
</div>

<div class="box">
<h2>↓ Get from Digivice</h2>
<p class="muted">Save camera shots and other files onto this PC/phone.</p>
{"".join(browse_links)}
</div>

<div class="box">
<h2>↑ Send to Digivice</h2>
<p class="muted">{html.escape(rom_help)}. Pick the console, or “ROMs · auto” to sort by extension.</p>
<form method="POST" enctype="multipart/form-data" action="/upload">
<label>Save to</label>
<select name="dest">{"".join(opts)}</select>
<label>ROM / file (you can pick several)</label>
<input type="file" name="file" accept="{html.escape(_ROM_ACCEPT)},image/*,.zip" multiple required>
<button type="submit">Send to Digivice</button>
</form>
</div>
<p class="muted">Photos → Pictures/phone · each console → roms/gb, nes, sms · Files → inbox</p>
"""
            self._html("Digivice Transfer", inner)

        def _page_browse(self, dest_key: str) -> None:
            if dest_key not in DESTINATIONS:
                self.send_error(404)
                return
            label, folder, _allowed = DESTINATIONS[dest_key]
            files = _list_folder(dest_key)
            signals.activity.emit(f"Browsing {label} ({len(files)})")

            if dest_key == "photos" or any(p.suffix.lower() in _IMG_EXT for p in files[:1]):
                cards = []
                for p in files:
                    qn = quote(p.name)
                    if p.suffix.lower() in _IMG_EXT:
                        cards.append(
                            f'<div class="card">'
                            f'<a href="/view/{dest_key}/{qn}" target="_blank">'
                            f'<img src="/view/{dest_key}/{qn}" alt="" loading="lazy"></a>'
                            f'<a href="/file/{dest_key}/{qn}" download="{html.escape(p.name)}">'
                            f"Download {html.escape(p.name)}</a></div>"
                        )
                    else:
                        cards.append(
                            f'<div class="card"><a href="/file/{dest_key}/{qn}" '
                            f'download="{html.escape(p.name)}">'
                            f"{html.escape(p.name)}</a></div>"
                        )
                listing = (
                    f'<div class="grid">{"".join(cards)}</div>'
                    if cards
                    else '<p class="muted">No files yet.</p>'
                )
            else:
                items = []
                for p in files:
                    qn = quote(p.name)
                    size = p.stat().st_size
                    items.append(
                        f'<li><a href="/file/{dest_key}/{qn}" download="{html.escape(p.name)}">'
                        f"{html.escape(p.name)}</a>"
                        f' <span class="muted">({size // 1024} KB)</span></li>'
                    )
                listing = (
                    f'<ul class="files">{"".join(items)}</ul>'
                    if items
                    else '<p class="muted">No files yet.</p>'
                )

            inner = f"""
<nav><a href="/">← Home</a></nav>
<h1>Get {html.escape(label)}</h1>
<p class="muted">{html.escape(str(folder))} · {len(files)} file(s)</p>
{listing}
"""
            self._html(f"Get {label}", inner)

        def _serve_file(self, dest_key: str, name: str, *, inline: bool) -> None:
            path = _resolve_file(dest_key, name)
            if path is None:
                self.send_error(404)
                return
            try:
                data = path.read_bytes()
            except OSError:
                self.send_error(500)
                return
            ctype, _ = mimetypes.guess_type(str(path))
            if not ctype:
                ctype = "application/octet-stream"
            disp = "inline" if inline else f'attachment; filename="{path.name}"'
            signals.activity.emit(f"Sent {path.name}")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", disp)
            self.end_headers()
            self.wfile.write(data)

        def _serve_modem_report(self, *, download: bool) -> None:
            path = _modem_report_path()
            if path is None:
                ok, msg = _refresh_modem_report()
                path = _modem_report_path() if ok else None
                if path is None:
                    body = (
                        "No modem-doctor.txt yet.\n\n"
                        "On Digivice: Tools → Transfer → Prep modem report,\n"
                        "or run: digivice-modem-doctor\n\n"
                        f"({msg})\n"
                    ).encode("utf-8")
                    self.send_response(404)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    signals.activity.emit("No modem report yet")
                    return
            try:
                data = path.read_bytes()
            except OSError:
                self.send_error(500)
                return
            signals.activity.emit("Sent modem-doctor.txt")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            if download:
                self.send_header(
                    "Content-Disposition",
                    'attachment; filename="modem-doctor.txt"',
                )
            self.end_headers()
            self.wfile.write(data)

        def _serve_audio_report(self, *, download: bool) -> None:
            path = _audio_report_path()
            if path is None:
                ok, msg = _refresh_audio_report()
                path = _audio_report_path() if ok else None
                if path is None:
                    body = (
                        "No audio-doctor.txt yet.\n\n"
                        "On Digivice: Tools → Transfer → Prep audio report,\n"
                        "or run: digivice-audio-doctor\n\n"
                        f"({msg})\n"
                    ).encode("utf-8")
                    self.send_response(404)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    signals.activity.emit("No audio report yet")
                    return
            try:
                data = path.read_bytes()
            except OSError:
                self.send_error(500)
                return
            signals.activity.emit("Sent audio-doctor.txt")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            if download:
                self.send_header(
                    "Content-Disposition",
                    'attachment; filename="audio-doctor.txt"',
                )
            self.end_headers()
            self.wfile.write(data)

        def _serve_media_report(self, *, download: bool) -> None:
            path = _media_report_path()
            if path is None:
                ok, msg = _refresh_media_report()
                path = _media_report_path() if ok else None
                if path is None:
                    body = (
                        "No media-doctor.txt yet.\n\n"
                        "On Digivice: Tools → Transfer → Prep media report,\n"
                        "or run: digivice-media-doctor\n\n"
                        f"({msg})\n"
                    ).encode("utf-8")
                    self.send_response(404)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    signals.activity.emit("No media report yet")
                    return
            try:
                data = path.read_bytes()
            except OSError:
                self.send_error(500)
                return
            signals.activity.emit("Sent media-doctor.txt")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            if download:
                self.send_header(
                    "Content-Disposition",
                    'attachment; filename="media-doctor.txt"',
                )
            self.end_headers()
            self.wfile.write(data)

        def _serve_i2c_report(self, *, download: bool) -> None:
            path = _i2c_report_path()
            if path is None:
                ok, msg = _refresh_i2c_report()
                path = _i2c_report_path() if ok else None
                if path is None:
                    body = (
                        "No i2c-doctor.txt yet.\n\n"
                        "On Digivice: Tools → Transfer → Prep I2C report,\n"
                        "or run: digivice-i2c-doctor\n\n"
                        f"({msg})\n"
                    ).encode("utf-8")
                    self.send_response(404)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    signals.activity.emit("No I2C report yet")
                    return
            try:
                data = path.read_bytes()
            except OSError:
                self.send_error(500)
                return
            signals.activity.emit("Sent i2c-doctor.txt")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            if download:
                self.send_header(
                    "Content-Disposition",
                    'attachment; filename="i2c-doctor.txt"',
                )
            self.end_headers()
            self.wfile.write(data)

        def _serve_mouse_report(self, *, download: bool) -> None:
            path = _mouse_report_path()
            if path is None:
                ok, msg = _refresh_mouse_report()
                path = _mouse_report_path() if ok else None
                if path is None:
                    body = (
                        "No mouse-doctor.txt yet.\n\n"
                        "On Digivice: Tools → Transfer → Prep mouse report,\n"
                        "or run: digivice-mouse-doctor\n\n"
                        f"({msg})\n"
                    ).encode("utf-8")
                    self.send_response(404)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    signals.activity.emit("No mouse report yet")
                    return
            try:
                data = path.read_bytes()
            except OSError:
                self.send_error(500)
                return
            signals.activity.emit("Sent mouse-doctor.txt")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            if download:
                self.send_header(
                    "Content-Disposition",
                    'attachment; filename="mouse-doctor.txt"',
                )
            self.end_headers()
            self.wfile.write(data)

        def _serve_heltec_report(self, *, download: bool) -> None:
            path = _heltec_report_path()
            if path is None:
                ok, msg = _refresh_heltec_report()
                path = _heltec_report_path() if ok else None
                if path is None:
                    body = (
                        "No heltec-doctor.txt yet.\n\n"
                        "On Digivice: Tools → Transfer → Prep Heltec report,\n"
                        "or run: sudo digivice-heltec-doctor\n\n"
                        f"({msg})\n"
                    ).encode("utf-8")
                    self.send_response(404)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    signals.activity.emit("No Heltec report yet")
                    return
            try:
                data = path.read_bytes()
            except OSError:
                self.send_error(500)
                return
            signals.activity.emit("Sent heltec-doctor.txt")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            if download:
                self.send_header(
                    "Content-Disposition",
                    'attachment; filename="heltec-doctor.txt"',
                )
            self.end_headers()
            self.wfile.write(data)

        def _serve_sip_report(self, *, download: bool) -> None:
            # Never regenerate here — Prep SIP already wrote the file.
            # Regenerating on download was crashing Digivice (OOM / VoIP fight).
            path = _sip_report_path()
            if path is None:
                body = (
                    "No sip-doctor.txt yet.\n\n"
                    "On Digivice: Tools → Transfer → Prep SIP report\n"
                    "then open this link again.\n"
                ).encode("utf-8")
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                signals.activity.emit("No SIP report yet")
                return
            try:
                # Stream in chunks — don't hold two full copies in RAM.
                size = path.stat().st_size
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(size))
                if download:
                    self.send_header(
                        "Content-Disposition",
                        'attachment; filename="sip-doctor.txt"',
                    )
                self.end_headers()
                with path.open("rb") as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            except OSError:
                try:
                    self.send_error(500)
                except Exception:
                    pass
                return
            signals.activity.emit("Sent sip-doctor.txt")

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in ("/upload", "/upload/"):
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > _MAX_UPLOAD:
                signals.failed.emit("File too large / empty")
                self._reply(400, "Bad size (max 48MB)")
                return
            raw = self.rfile.read(length)
            ctype = self.headers.get("Content-Type", "")
            dest_key, files = _parse_multipart(ctype, raw)
            if not dest_key or dest_key not in DESTINATIONS:
                dest_key = get_dest()
            if dest_key not in DESTINATIONS:
                dest_key = "files"
            if not files:
                signals.failed.emit("No file in upload")
                self._reply(400, "No file attached")
                return
            label, _folder, allowed = DESTINATIONS[dest_key]
            saved: List[str] = []
            errors: List[str] = []
            for filename, filedata in files:
                if not filedata:
                    continue
                safe = _safe_name(filename or "", allowed)
                if not safe:
                    allow = ", ".join(allowed) if allowed else ", ".join(_FILES_OK[:8]) + "…"
                    errors.append(f"{filename or '?'}: need {allow}")
                    continue
                try:
                    folder = _dest_folder(dest_key, safe)
                    folder.mkdir(parents=True, exist_ok=True)
                    out = folder / safe
                    if out.exists():
                        stem, ext = out.stem, out.suffix
                        n = 2
                        while out.exists():
                            out = folder / f"{stem}_{n}{ext}"
                            n += 1
                    out.write_bytes(filedata)
                    saved.append(f"{out.name} → {folder.name}")
                except Exception as e:
                    errors.append(f"{safe}: {str(e)[:40]}")
            if saved:
                signals.got_file.emit(f"{label}: " + ", ".join(saved))
            if errors and not saved:
                signals.failed.emit(errors[0][:80])
                self._reply(400, html.escape("; ".join(errors)[:400]))
                return
            extra = (
                f"<p class='muted'>{html.escape('; '.join(errors))}</p>" if errors else ""
            )
            names = "<br>".join(html.escape(s) for s in saved)
            self._reply(
                200,
                f"OK — saved to {html.escape(label)}:<br>{names}{extra}<br>"
                f'<a style="color:#9cf;" href="/">Home</a> · '
                f'<a style="color:#9cf;" href="/browse/{dest_key}">Browse {html.escape(label)}</a>',
            )

        def _reply(self, code: int, msg: str) -> None:
            body = f"""<!DOCTYPE html><html><body style="font-family:sans-serif;
background:#0b1a2a;color:#e8eef5;padding:16px;">
<h2>{msg}</h2>
<p><a style="color:#9cf;" href="/">Home</a></p>
</body></html>""".encode(
                "utf-8"
            )
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def make_wifi_transfer_page(
    on_back: Callable[[], None],
    *,
    initial_dest: str = "photos",
) -> QWidget:
    """Tools → Transfer: send/get photos · ROMs · files over Wi‑Fi."""
    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(3)

    dest_row = QHBoxLayout()
    dest_row.setSpacing(2)
    dest_btns: Dict[str, QPushButton] = {}
    _digi_labs = {"photos": "Photos", "roms": "ROMs", "files": "Files"}
    for key in DIGI_DEST_KEYS:
        b = QPushButton(_digi_labs.get(key, DESTINATIONS[key][0]))
        b.setFixedHeight(26)
        b.setStyleSheet("font-size:11px; font-weight:700;")
        b.setCheckable(True)
        dest_btns[key] = b
        dest_row.addWidget(b, 1)

    url_lab = QLabel("")
    url_lab.setAlignment(Qt.AlignCenter)
    url_lab.setWordWrap(True)
    url_lab.setStyleSheet(
        "font-size:12px; font-weight:800; color:#FFE600;"
        "background:#1a2230; padding:6px;"
    )
    status = QLabel("")
    status.setAlignment(Qt.AlignCenter)
    status.setWordWrap(True)
    status.setStyleSheet("font-size:10px; color:#cde;")

    start_btn = QPushButton("Start")
    start_btn.setFixedHeight(28)
    start_btn.setStyleSheet("font-weight:800;")
    prep_sip_btn = QPushButton("Prep SIP report")
    prep_sip_btn.setFixedHeight(26)
    prep_sip_btn.setStyleSheet("font-size:11px; font-weight:800;")
    prep_btn = QPushButton("Prep modem report")
    prep_btn.setFixedHeight(26)
    prep_btn.setStyleSheet("font-size:11px;")
    prep_audio_btn = QPushButton("Prep audio report")
    prep_audio_btn.setFixedHeight(26)
    prep_audio_btn.setStyleSheet("font-size:11px;")
    prep_media_btn = QPushButton("Prep media report")
    prep_media_btn.setFixedHeight(26)
    prep_media_btn.setStyleSheet("font-size:11px;")
    prep_i2c_btn = QPushButton("Prep I2C report")
    prep_i2c_btn.setFixedHeight(26)
    prep_i2c_btn.setStyleSheet("font-size:11px;")
    prep_mouse_btn = QPushButton("Prep mouse report")
    prep_mouse_btn.setFixedHeight(26)
    prep_mouse_btn.setStyleSheet("font-size:11px;")
    prep_heltec_btn = QPushButton("Prep Heltec report")
    prep_heltec_btn.setFixedHeight(26)
    prep_heltec_btn.setStyleSheet("font-size:11px;")
    stop_btn = QPushButton("Stop")
    stop_btn.setFixedHeight(26)
    stop_btn.setEnabled(False)

    lay.addLayout(dest_row)
    lay.addWidget(url_lab)
    lay.addWidget(status, 1)
    lay.addWidget(start_btn)
    lay.addWidget(prep_sip_btn)
    lay.addWidget(prep_btn)
    lay.addWidget(prep_audio_btn)
    lay.addWidget(prep_media_btn)
    lay.addWidget(prep_i2c_btn)
    lay.addWidget(prep_mouse_btn)
    lay.addWidget(prep_heltec_btn)
    lay.addWidget(stop_btn)

    state = {"dest": initial_dest if initial_dest in DESTINATIONS else "photos"}
    signals = _UploadSignals(body)
    server_holder: dict = {"httpd": None}

    def _paint_dest() -> None:
        shown = state["dest"]
        if shown.startswith("rom_"):
            shown = "roms"
        for key, b in dest_btns.items():
            on = key == shown
            b.setChecked(on)
            b.setStyleSheet(
                "font-size:11px; font-weight:800; background:#FFE600; color:#000;"
                if on
                else "font-size:11px; font-weight:700;"
            )

    def set_dest(key: str) -> None:
        if key in DESTINATIONS:
            state["dest"] = key
            _paint_dest()
            label, folder, allowed = DESTINATIONS[key]
            n = len(_list_folder(key))
            hint = _ext_hint(allowed)
            status.setText(f"{label} · {n} on device\n{hint}\n{folder}")

    def stop_server() -> None:
        httpd = server_holder.get("httpd")
        if httpd is not None:
            try:
                httpd.shutdown()
            except Exception:
                pass
            try:
                httpd.server_close()
            except Exception:
                pass
        server_holder["httpd"] = None
        start_btn.setEnabled(True)
        stop_btn.setEnabled(False)
        for b in dest_btns.values():
            b.setEnabled(True)

    def start_server() -> None:
        stop_server()
        for key, (_lab, folder, _) in DESTINATIONS.items():
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                if key == state["dest"]:
                    status.setText(f"Folder error: {e}")
                    return
        ip = _lan_ip()
        url_lab.setText(f"http://{ip}:{UPLOAD_PORT}")
        status.setText(
            f"SIP report on PC:\n"
            f"http://{ip}:{UPLOAD_PORT}/diag/sip.txt\n"
            f"(tap Prep SIP report first)"
        )
        # Do not generate the report on Start — that crashed Digivice.
        # User taps Prep SIP report once, then downloads.
        handler = _make_handler(lambda: state["dest"], signals)
        try:
            httpd = HTTPServer(("0.0.0.0", UPLOAD_PORT), handler)
        except OSError as e:
            status.setText(f"Port busy: {e}")
            return
        server_holder["httpd"] = httpd

        def run() -> None:
            try:
                httpd.serve_forever(poll_interval=0.3)
            except Exception:
                pass

        threading.Thread(target=run, daemon=True).start()
        start_btn.setEnabled(False)
        stop_btn.setEnabled(True)
        for b in dest_btns.values():
            b.setEnabled(False)

    def _prep_busy(on: bool) -> None:
        prep_sip_btn.setEnabled(not on)
        prep_btn.setEnabled(not on)
        prep_audio_btn.setEnabled(not on)
        prep_media_btn.setEnabled(not on)
        prep_i2c_btn.setEnabled(not on)
        prep_mouse_btn.setEnabled(not on)
        prep_heltec_btn.setEnabled(not on)

    def prep_sip() -> None:
        status.setText("Building SIP report…")
        _prep_busy(True)

        def work() -> None:
            ok, msg = _refresh_sip_report()
            signals.prep_done.emit(ok, f"sip:{msg}")

        threading.Thread(target=work, daemon=True).start()

    def prep_modem() -> None:
        status.setText("Running modem doctor…")
        _prep_busy(True)

        def work() -> None:
            ok, msg = _refresh_modem_report()
            signals.prep_done.emit(ok, msg)

        threading.Thread(target=work, daemon=True).start()

    def prep_audio() -> None:
        status.setText("Running audio doctor…")
        _prep_busy(True)

        def work() -> None:
            ok, msg = _refresh_audio_report()
            signals.prep_done.emit(ok, f"audio:{msg}")

        threading.Thread(target=work, daemon=True).start()

    def prep_media() -> None:
        status.setText("Running media doctor…")
        _prep_busy(True)

        def work() -> None:
            ok, msg = _refresh_media_report()
            signals.prep_done.emit(ok, f"media:{msg}")

        threading.Thread(target=work, daemon=True).start()

    def prep_i2c() -> None:
        status.setText("Running I2C doctor…")
        _prep_busy(True)

        def work() -> None:
            ok, msg = _refresh_i2c_report()
            signals.prep_done.emit(ok, f"i2c:{msg}")

        threading.Thread(target=work, daemon=True).start()

    def prep_mouse() -> None:
        status.setText("Running mouse doctor…")
        _prep_busy(True)

        def work() -> None:
            ok, msg = _refresh_mouse_report()
            signals.prep_done.emit(ok, f"mouse:{msg}")

        threading.Thread(target=work, daemon=True).start()

    def prep_heltec() -> None:
        status.setText("Running Heltec doctor…")
        _prep_busy(True)

        def work() -> None:
            ok, msg = _refresh_heltec_report()
            signals.prep_done.emit(ok, f"heltec:{msg}")

        threading.Thread(target=work, daemon=True).start()

    def on_prep_done(ok: bool, msg: str) -> None:
        _prep_busy(False)
        if server_holder.get("httpd") is None:
            start_server()
        ip = _lan_ip()
        url_lab.setText(f"http://{ip}:{UPLOAD_PORT}")
        kind = "modem"
        show = msg
        if msg.startswith("audio:"):
            kind = "audio"
            show = msg[6:]
        elif msg.startswith("media:"):
            kind = "media"
            show = msg[6:]
        elif msg.startswith("i2c:"):
            kind = "i2c"
            show = msg[4:]
        elif msg.startswith("mouse:"):
            kind = "mouse"
            show = msg[6:]
        elif msg.startswith("heltec:"):
            kind = "heltec"
            show = msg[7:]
        elif msg.startswith("sip:"):
            kind = "sip"
            show = msg[4:]
        path_ok = {
            "audio": _audio_report_path,
            "media": _media_report_path,
            "i2c": _i2c_report_path,
            "mouse": _mouse_report_path,
            "heltec": _heltec_report_path,
            "sip": _sip_report_path,
            "modem": _modem_report_path,
        }[kind]()
        if ok and path_ok is not None:
            status.setText(
                f"{kind} report ready · on PC open:\n"
                f"http://{ip}:{UPLOAD_PORT}/diag/{kind}.txt"
            )
        else:
            status.setText(f"Doctor failed: {show}")

    def on_got(msg: str) -> None:
        status.setText(f"Saved {msg}\nSend more or Stop")

    def on_fail(msg: str) -> None:
        status.setText(msg)

    def on_activity(msg: str) -> None:
        status.setText(msg)

    signals.got_file.connect(on_got)
    signals.failed.connect(on_fail)
    signals.activity.connect(on_activity)
    signals.prep_done.connect(on_prep_done)

    for key, b in dest_btns.items():
        b.clicked.connect(lambda _=False, k=key: set_dest(k))
    start_btn.clicked.connect(start_server)
    prep_sip_btn.clicked.connect(prep_sip)
    prep_btn.clicked.connect(prep_modem)
    prep_audio_btn.clicked.connect(prep_audio)
    prep_media_btn.clicked.connect(prep_media)
    prep_i2c_btn.clicked.connect(prep_i2c)
    prep_mouse_btn.clicked.connect(prep_mouse)
    prep_heltec_btn.clicked.connect(prep_heltec)
    stop_btn.clicked.connect(
        lambda: (stop_server(), status.setText("Stopped. Start again when ready."))
    )

    def chrome_back() -> None:
        stop_server()
        on_back()

    def on_hardware_back() -> bool:
        if server_holder.get("httpd") is not None:
            stop_server()
            status.setText("Stopped.")
            return True
        return False

    chrome = page_chrome("Transfer", body, chrome_back, scroll=False)
    chrome.on_hardware_back = on_hardware_back  # type: ignore[attr-defined]
    chrome.set_transfer_dest = set_dest  # type: ignore[attr-defined]
    chrome.stop_transfer = stop_server  # type: ignore[attr-defined]

    set_dest(state["dest"])
    return chrome
