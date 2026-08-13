"""Game Boy / GBC ROM picker + Wi‑Fi receive (upload from phone/PC browser)."""

from __future__ import annotations

import html
import os
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable, List, Optional
from urllib.parse import unquote

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from esp_handset.pages import page_chrome

DATA = Path.home() / ".esp-handset"
ROM_DIR = DATA / "roms" / "gb"
ROM_DIRS = [
    ROM_DIR,
    Path.home() / "roms" / "gb",
    Path.home() / "ROMs" / "gb",
    Path("/opt/esp-handset/roms/gb"),
]
UPLOAD_PORT = 8765


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


def _ensure_rom_dir() -> Path:
    ROM_DIR.mkdir(parents=True, exist_ok=True)
    return ROM_DIR


def _list_roms() -> List[Path]:
    found: List[Path] = []
    seen = set()
    _ensure_rom_dir()
    for d in ROM_DIRS:
        if not d.is_dir():
            continue
        try:
            for p in sorted(d.iterdir(), key=lambda x: x.name.casefold()):
                if p.suffix.lower() in (".gb", ".gbc", ".sgb"):
                    key = str(p.resolve()) if p.exists() else str(p)
                    if key in seen:
                        continue
                    seen.add(key)
                    found.append(p)
        except OSError:
            continue
    return found


def _find_launcher() -> str:
    for p in (
        "/usr/local/bin/digivice-gb",
        "/opt/esp-handset/session/digivice-gb.sh",
        str(Path(__file__).resolve().parents[1] / "session" / "digivice-gb.sh"),
        str(Path.home() / "esp-phone" / "pi_handset" / "session" / "digivice-gb.sh"),
    ):
        if os.path.isfile(p):
            return p
    return "/usr/local/bin/digivice-gb"


def _emu_hint() -> str:
    for cmd in ("retroarch", "mgba-sdl", "mgba-qt", "mgba"):
        if any(
            os.path.isfile(os.path.join(d, cmd))
            for d in os.environ.get("PATH", "/usr/bin:/bin").split(":")
        ):
            return f"Emulator: {cmd}"
    return "Need: sudo apt install retroarch libretro-gambatte"


def _safe_rom_name(name: str) -> Optional[str]:
    base = Path(unquote(name or "")).name
    if not base or base in (".", ".."):
        return None
    if Path(base).suffix.lower() not in (".gb", ".gbc", ".sgb"):
        return None
    # strip path tricks
    safe = "".join(c for c in base if c.isalnum() or c in "._- ()[]")
    if not safe or Path(safe).suffix.lower() not in (".gb", ".gbc", ".sgb"):
        return None
    return safe


class _UploadSignals(QObject):
    got_file = pyqtSignal(str)
    failed = pyqtSignal(str)


def _make_handler(dest: Path, signals: _UploadSignals):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            return

        def do_GET(self) -> None:  # noqa: N802
            body = f"""<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Digivice ROMs</title>
<style>
body{{font-family:sans-serif;background:#0b1a2a;color:#e8eef5;padding:16px;}}
h1{{font-size:1.2rem;}}
.box{{background:#152030;padding:16px;border-radius:8px;}}
input,button{{font-size:1rem;padding:10px;margin-top:8px;width:100%;box-sizing:border-box;}}
button{{background:#1f6feb;color:#fff;border:0;font-weight:700;}}
.ok{{color:#7dffa0;}}
</style></head><body>
<h1>Digivice · Game Boy ROMs</h1>
<p>Same Wi‑Fi as Digivice. Upload <b>.gb</b> / <b>.gbc</b> only.</p>
<div class="box">
<form method="POST" enctype="multipart/form-data" action="/upload">
<input type="file" name="rom" accept=".gb,.gbc,.sgb" required>
<button type="submit">Send to Digivice</button>
</form>
</div>
<p style="color:#9ab;font-size:0.85rem;">Files go to ~/.esp-handset/roms/gb/</p>
</body></html>"""
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
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
            if length <= 0 or length > 16 * 1024 * 1024:
                signals.failed.emit("File too large / empty")
                self._reply(400, "Bad upload size (max 16MB)")
                return
            raw = self.rfile.read(length)
            ctype = self.headers.get("Content-Type", "")
            filename, filedata = _parse_multipart(ctype, raw)
            safe = _safe_rom_name(filename or "")
            if not safe or not filedata:
                signals.failed.emit("Need a .gb / .gbc file")
                self._reply(400, "Please choose a .gb or .gbc file")
                return
            try:
                dest.mkdir(parents=True, exist_ok=True)
                out = dest / safe
                out.write_bytes(filedata)
                signals.got_file.emit(safe)
                self._reply(
                    200,
                    f"OK — saved <b>{html.escape(safe)}</b>. "
                    "On Digivice: Reload ROMs, then Play.",
                )
            except Exception as e:
                signals.failed.emit(str(e)[:60])
                self._reply(500, f"Save failed: {html.escape(str(e)[:80])}")

        def _reply(self, code: int, msg: str) -> None:
            body = f"""<!DOCTYPE html><html><body style="font-family:sans-serif;
background:#0b1a2a;color:#e8eef5;padding:16px;">
<h2>{msg}</h2>
<p><a style="color:#9cf;" href="/">Send another</a></p>
</body></html>""".encode(
                "utf-8"
            )
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _parse_multipart(content_type: str, body: bytes):
    """Minimal multipart file extract (name=rom)."""
    if "multipart/form-data" not in content_type or "boundary=" not in content_type:
        return None, None
    boundary = content_type.split("boundary=", 1)[-1].strip().encode("ascii", "ignore")
    if not boundary:
        return None, None
    parts = body.split(b"--" + boundary)
    for part in parts:
        if b"Content-Disposition" not in part or b'name="rom"' not in part:
            continue
        header, _, data = part.partition(b"\r\n\r\n")
        if not data:
            continue
        if data.endswith(b"\r\n"):
            data = data[:-2]
        fname = None
        for line in header.split(b"\r\n"):
            if b"filename=" in line:
                try:
                    raw = line.decode("utf-8", "replace")
                    fname = raw.split("filename=", 1)[-1].strip().strip('"')
                except Exception:
                    fname = "game.gb"
        return fname, data
    return None, None


def make_gb_page(on_back: Callable[[], None]) -> QWidget:
    """Games → Game Boy: pick ROM, or Receive from phone/PC browser."""
    from esp_handset import digi_nav

    root = QWidget()
    stack = QStackedWidget(root)
    outer = QVBoxLayout(root)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(stack)

    # ----- list -----
    list_page = QWidget()
    lay = QVBoxLayout(list_page)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(2)
    tip = QLabel(
        "A=Confirm B=Back Start=Home\n"
        "Select=Home+A · Exit=A+B+Home"
    )
    tip.setWordWrap(True)
    tip.setStyleSheet("color:#9ab;font-size:9px;")
    status = QLabel("")
    status.setWordWrap(True)
    status.setStyleSheet("color:#cde;font-size:10px;")
    lst = QListWidget()
    lst.setStyleSheet(
        "QListWidget { background: transparent; border: none; }"
        "QListWidget::item { padding: 4px; min-height: 22px; }"
        "QListWidget::item:selected { background:#FFE600; color:#000; }"
    )
    play = QPushButton("Play")
    play.setFixedHeight(28)
    play.setStyleSheet("font-weight:800;")
    recv = QPushButton("Receive ROMs (Wi‑Fi)")
    recv.setFixedHeight(26)
    refresh = QPushButton("Reload")
    refresh.setFixedHeight(24)
    lay.addWidget(tip)
    lay.addWidget(status)
    lay.addWidget(lst, 1)
    lay.addWidget(play)
    lay.addWidget(recv)
    lay.addWidget(refresh)
    stack.addWidget(list_page)

    # ----- receive -----
    recv_page = QWidget()
    rl = QVBoxLayout(recv_page)
    rl.setContentsMargins(4, 4, 4, 4)
    rl.setSpacing(4)
    recv_title = QLabel("On your phone or PC\n(same Wi‑Fi):")
    recv_title.setAlignment(Qt.AlignCenter)
    recv_title.setStyleSheet("font-size:11px; font-weight:700;")
    recv_title.setWordWrap(True)
    url_lab = QLabel("…")
    url_lab.setAlignment(Qt.AlignCenter)
    url_lab.setWordWrap(True)
    url_lab.setStyleSheet(
        "font-size:13px; font-weight:800; color:#FFE600;"
        "background:#1a2230; padding:8px;"
    )
    recv_status = QLabel("Waiting for upload…")
    recv_status.setAlignment(Qt.AlignCenter)
    recv_status.setWordWrap(True)
    recv_status.setStyleSheet("font-size:10px; color:#9ab;")
    stop_btn = QPushButton("Done")
    stop_btn.setFixedHeight(28)
    stop_btn.setStyleSheet("font-weight:700;")
    rl.addStretch(1)
    rl.addWidget(recv_title)
    rl.addWidget(url_lab)
    rl.addWidget(recv_status)
    rl.addStretch(1)
    rl.addWidget(stop_btn)
    stack.addWidget(recv_page)

    signals = _UploadSignals(root)
    server_holder: dict = {"httpd": None, "thread": None}

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
        server_holder["thread"] = None

    def start_server() -> None:
        stop_server()
        dest = _ensure_rom_dir()
        ip = _lan_ip()
        url_lab.setText(f"http://{ip}:{UPLOAD_PORT}")
        recv_status.setText("Open that link → choose .gb file → Send")

        handler = _make_handler(dest, signals)
        try:
            httpd = HTTPServer(("0.0.0.0", UPLOAD_PORT), handler)
        except OSError as e:
            recv_status.setText(f"Port busy: {e}")
            return
        server_holder["httpd"] = httpd

        def run() -> None:
            try:
                httpd.serve_forever(poll_interval=0.3)
            except Exception:
                pass

        t = threading.Thread(target=run, daemon=True)
        server_holder["thread"] = t
        t.start()

    def show_list() -> None:
        stop_server()
        stack.setCurrentWidget(list_page)
        refresh_list()
        digi_nav.ensure_page_focus(chrome)

    def show_receive() -> None:
        stack.setCurrentWidget(recv_page)
        start_server()
        digi_nav.ensure_page_focus(chrome)

    def on_got(name: str) -> None:
        recv_status.setText(f"Saved: {name}\nSend more or press Done")

    def on_fail(msg: str) -> None:
        recv_status.setText(msg)

    signals.got_file.connect(on_got)
    signals.failed.connect(on_fail)

    def refresh_list() -> None:
        lst.clear()
        roms = _list_roms()
        status.setText(f"{_emu_hint()}\n{len(roms)} ROM(s) · Receive = Wi‑Fi upload")
        if not roms:
            empty = QListWidgetItem("No ROMs yet\n→ Receive ROMs (Wi‑Fi)")
            empty.setFlags(Qt.NoItemFlags)
            lst.addItem(empty)
            return
        for p in roms:
            item = QListWidgetItem(p.name)
            item.setData(Qt.UserRole, str(p))
            lst.addItem(item)
        lst.setCurrentRow(0)

    def launch() -> None:
        item = lst.currentItem()
        if item is None:
            status.setText("Pick a ROM first")
            return
        path = item.data(Qt.UserRole)
        if not path or not Path(str(path)).is_file():
            status.setText("Invalid ROM")
            return
        rom = str(path)
        DATA.mkdir(parents=True, exist_ok=True)
        try:
            (DATA / "gb-rom").write_text(rom + "\n", encoding="utf-8")
        except OSError:
            pass
        try:
            Path("/run/digivice-gb-rom").write_text(rom + "\n", encoding="utf-8")
        except OSError:
            pass

        launcher = _find_launcher()
        status.setText("Starting Game Boy…")
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":0")
        try:
            subprocess.Popen(
                ["bash", launcher, rom],
                start_new_session=True,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except Exception as e:
            status.setText(f"Launch failed: {e}")
            return

        def _quit() -> None:
            try:
                from PyQt5.QtWidgets import QApplication

                app = QApplication.instance()
                if app is not None:
                    app.quit()
            except Exception:
                pass

        QTimer.singleShot(600, _quit)

    def chrome_back() -> None:
        if stack.currentWidget() is recv_page:
            show_list()
        else:
            stop_server()
            on_back()

    def on_hardware_back() -> bool:
        if stack.currentWidget() is recv_page:
            show_list()
            return True
        stop_server()
        return False

    lst.itemActivated.connect(lambda _i: launch())
    play.clicked.connect(launch)
    refresh.clicked.connect(refresh_list)
    recv.clicked.connect(show_receive)
    stop_btn.clicked.connect(show_list)

    chrome = page_chrome("Game Boy", root, chrome_back, scroll=False)
    chrome.on_hardware_back = on_hardware_back  # type: ignore[attr-defined]
    refresh_list()
    return chrome
