"""Digivice Wi‑Fi file transfer — send to Digivice or download from Digivice."""

from __future__ import annotations

import html
import mimetypes
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urlparse

from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer
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
DESTINATIONS: Dict[str, Tuple[str, Path, Optional[Tuple[str, ...]]]] = {
    "photos": (
        "Photos",
        PHOTOS,
        (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"),
    ),
    "roms": (
        "GB ROMs",
        DATA / "roms" / "gb",
        (".gb", ".gbc", ".sgb"),
    ),
    "files": (
        "Files",
        DATA / "inbox",
        None,
    ),
}

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
    ".mp3",
    ".wav",
    ".ogg",
    ".json",
    ".csv",
)

_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

MODEM_REPORT = DATA / "modem-doctor.txt"
MODEM_REPORT_TMP = Path("/tmp/digivice-modem-doctor.txt")


def _modem_report_path() -> Optional[Path]:
    for p in (MODEM_REPORT, MODEM_REPORT_TMP, Path.home() / "esp-phone" / "modem-doctor-LATEST.txt"):
        try:
            if p.is_file() and p.stat().st_size > 0:
                return p
        except OSError:
            continue
    return None


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
    if not folder.is_dir():
        return []
    out: List[Path] = []
    try:
        for p in sorted(folder.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not p.is_file():
                continue
            if _safe_name(p.name, allowed) is None:
                continue
            out.append(p)
    except OSError:
        return []
    return out


def _resolve_file(dest_key: str, name: str) -> Optional[Path]:
    if dest_key not in DESTINATIONS:
        return None
    _label, folder, allowed = DESTINATIONS[dest_key]
    safe = _safe_name(name, allowed)
    if not safe:
        return None
    path = (folder / safe).resolve()
    try:
        folder_r = folder.resolve()
    except OSError:
        return None
    if not str(path).startswith(str(folder_r)):
        return None
    if not path.is_file():
        return None
    return path


class _UploadSignals(QObject):
    got_file = pyqtSignal(str)
    failed = pyqtSignal(str)
    activity = pyqtSignal(str)
    prep_done = pyqtSignal(bool, str)


def _parse_multipart(content_type: str, body: bytes):
    if "multipart/form-data" not in content_type or "boundary=" not in content_type:
        return None, None, None
    boundary = content_type.split("boundary=", 1)[-1].strip().encode("ascii", "ignore")
    if not boundary:
        return None, None, None
    dest_key = None
    filename = None
    filedata = None
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
            for line in header.split(b"\r\n"):
                if b"filename=" in line:
                    try:
                        raw = line.decode("utf-8", "replace")
                        filename = raw.split("filename=", 1)[-1].strip().strip('"')
                    except Exception:
                        filename = "upload.bin"
            filedata = data
    return dest_key, filename, filedata


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
            for key, (label, _folder, _) in DESTINATIONS.items():
                sel = " selected" if key == cur else ""
                opts.append(f'<option value="{key}"{sel}>{html.escape(label)}</option>')
            browse_links = []
            for key, (label, folder, _) in DESTINATIONS.items():
                n = len(_list_folder(key))
                browse_links.append(
                    f'<a class="btn" style="margin-top:8px;display:block;" href="/browse/{key}">'
                    f"Get {html.escape(label)} ({n})</a>"
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
            inner = f"""
<nav><a href="/">Home</a></nav>
<h1>Digivice · Transfer</h1>
<p class="muted">Same Wi‑Fi. Send files to Digivice, or download photos/files to this computer.</p>

<div class="box">
<h2>Modem doctor</h2>
<p class="muted">{diag_note} · no SIM is OK for AT/GPS tests</p>
<a class="btn" style="display:block;" href="/diag/modem.txt">Download modem-doctor.txt</a>
<a style="display:block;margin-top:8px;" href="/diag/modem">View in browser</a>
</div>

<div class="box">
<h2>↓ Get from Digivice</h2>
<p class="muted">Save camera shots and other files onto this PC/phone.</p>
{"".join(browse_links)}
</div>

<div class="box">
<h2>↑ Send to Digivice</h2>
<form method="POST" enctype="multipart/form-data" action="/upload">
<label>Save to</label>
<select name="dest">{"".join(opts)}</select>
<label>File</label>
<input type="file" name="file" required>
<button type="submit">Send to Digivice</button>
</form>
</div>
<p class="muted">Photos → Pictures/phone · ROMs → roms/gb · Files → inbox</p>
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

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in ("/upload", "/upload/"):
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > 32 * 1024 * 1024:
                signals.failed.emit("File too large / empty")
                self._reply(400, "Bad size (max 32MB)")
                return
            raw = self.rfile.read(length)
            ctype = self.headers.get("Content-Type", "")
            dest_key, filename, filedata = _parse_multipart(ctype, raw)
            if not dest_key or dest_key not in DESTINATIONS:
                dest_key = get_dest()
            if dest_key not in DESTINATIONS:
                dest_key = "files"
            label, folder, allowed = DESTINATIONS[dest_key]
            safe = _safe_name(filename or "", allowed)
            if not safe or not filedata:
                allow = ", ".join(allowed) if allowed else ", ".join(_FILES_OK[:8]) + "…"
                signals.failed.emit("Wrong file type")
                self._reply(
                    400,
                    f"That type isn’t allowed for {html.escape(label)}. Try: {html.escape(allow)}",
                )
                return
            try:
                folder.mkdir(parents=True, exist_ok=True)
                out = folder / safe
                if out.exists():
                    stem, ext = out.stem, out.suffix
                    n = 2
                    while out.exists():
                        out = folder / f"{stem}_{n}{ext}"
                        n += 1
                out.write_bytes(filedata)
                signals.got_file.emit(f"{label}: {out.name}")
                self._reply(
                    200,
                    f"OK — saved <b>{html.escape(out.name)}</b> to {html.escape(label)}.<br>"
                    f'<a style="color:#9cf;" href="/">Home</a> · '
                    f'<a style="color:#9cf;" href="/browse/{dest_key}">Browse {html.escape(label)}</a>',
                )
            except Exception as e:
                signals.failed.emit(str(e)[:50])
                self._reply(500, f"Save failed: {html.escape(str(e)[:80])}")

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

    tip = QLabel("Start · open link on PC · Get Photos / modem report")
    tip.setWordWrap(True)
    tip.setStyleSheet("color:#9ab;font-size:9px;")

    dest_row = QHBoxLayout()
    dest_row.setSpacing(2)
    dest_btns: Dict[str, QPushButton] = {}
    for key, (label, _folder, _a) in DESTINATIONS.items():
        b = QPushButton(label)
        b.setFixedHeight(26)
        b.setStyleSheet("font-size:11px; font-weight:700;")
        b.setCheckable(True)
        dest_btns[key] = b
        dest_row.addWidget(b, 1)

    url_lab = QLabel("Press Start")
    url_lab.setAlignment(Qt.AlignCenter)
    url_lab.setWordWrap(True)
    url_lab.setStyleSheet(
        "font-size:12px; font-weight:800; color:#FFE600;"
        "background:#1a2230; padding:6px;"
    )
    status = QLabel("Photos selected · Start to share both ways.")
    status.setAlignment(Qt.AlignCenter)
    status.setWordWrap(True)
    status.setStyleSheet("font-size:10px; color:#cde;")

    start_btn = QPushButton("Start")
    start_btn.setFixedHeight(28)
    start_btn.setStyleSheet("font-weight:800;")
    prep_btn = QPushButton("Prep modem report")
    prep_btn.setFixedHeight(26)
    prep_btn.setStyleSheet("font-size:11px;")
    stop_btn = QPushButton("Stop")
    stop_btn.setFixedHeight(26)
    stop_btn.setEnabled(False)

    lay.addWidget(tip)
    lay.addLayout(dest_row)
    lay.addWidget(url_lab)
    lay.addWidget(status, 1)
    lay.addWidget(start_btn)
    lay.addWidget(prep_btn)
    lay.addWidget(stop_btn)

    state = {"dest": initial_dest if initial_dest in DESTINATIONS else "photos"}
    signals = _UploadSignals(body)
    server_holder: dict = {"httpd": None}

    def _paint_dest() -> None:
        for key, b in dest_btns.items():
            on = key == state["dest"]
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
            label, folder, _ = DESTINATIONS[key]
            n = len(_list_folder(key))
            status.setText(f"{label} · {n} on device\n{folder}")

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
        label, _folder, _ = DESTINATIONS[state["dest"]]
        ip = _lan_ip()
        url_lab.setText(f"http://{ip}:{UPLOAD_PORT}")
        status.setText(
            f"Open link · Get {label} / modem report\n"
            f"Modem: http://{ip}:{UPLOAD_PORT}/diag/modem.txt"
        )

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

    def prep_modem() -> None:
        status.setText("Running modem doctor…")
        prep_btn.setEnabled(False)

        holder: dict = {"ok": False, "msg": ""}

        def work() -> None:
            holder["ok"], holder["msg"] = _refresh_modem_report()

        def after() -> None:
            prep_btn.setEnabled(True)
            if server_holder.get("httpd") is None:
                start_server()
            ip = _lan_ip()
            url_lab.setText(f"http://{ip}:{UPLOAD_PORT}")
            if holder["ok"] and _modem_report_path() is not None:
                status.setText(
                    f"Report ready · on PC open:\n"
                    f"http://{ip}:{UPLOAD_PORT}/diag/modem.txt"
                )
            else:
                status.setText(f"Doctor failed: {holder['msg']}")

        def run_then_ui() -> None:
            work()
            QTimer.singleShot(0, after)

        threading.Thread(target=run_then_ui, daemon=True).start()

    def on_got(msg: str) -> None:
        status.setText(f"Saved {msg}\nSend more or Stop")

    def on_fail(msg: str) -> None:
        status.setText(msg)

    def on_activity(msg: str) -> None:
        status.setText(msg)

    signals.got_file.connect(on_got)
    signals.failed.connect(on_fail)
    signals.activity.connect(on_activity)

    for key, b in dest_btns.items():
        b.clicked.connect(lambda _=False, k=key: set_dest(k))
    start_btn.clicked.connect(start_server)
    prep_btn.clicked.connect(prep_modem)
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
