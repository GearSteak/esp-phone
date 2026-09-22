"""Digivice ↔ Snail OS (XTEINK) companion bridge — LAN HTTP API for card Lua apps.

Snail's snail.fetch() is documented as HTTPS. Try HTTP on LAN first; if the
device rejects it, enable TLS with a cert under ~/.esp-handset/snail-bridge/.
"""

from __future__ import annotations

import json
import socket
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from esp_handset import store

DATA = Path.home() / ".esp-handset"
CERT_DIR = DATA / "snail-bridge"
DEFAULT_PORT = 8787

_httpd: Optional[ThreadingHTTPServer] = None
_thread: Optional[threading.Thread] = None
_port = DEFAULT_PORT
_use_tls = False
_started_at = 0.0


def lan_ip() -> str:
    """Best-effort primary LAN IPv4 (not 127.0.0.1)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.4)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass
    return "127.0.0.1"


def base_url() -> str:
    scheme = "https" if _use_tls else "http"
    return f"{scheme}://{lan_ip()}:{_port}"


def is_running() -> bool:
    return _httpd is not None and _thread is not None and _thread.is_alive()


def status_dict() -> Dict[str, Any]:
    return {
        "ok": True,
        "name": "Digivice",
        "version": 1,
        "ip": lan_ip(),
        "port": _port,
        "tls": _use_tls,
        "running": is_running(),
        "uptime_s": int(time.time() - _started_at) if is_running() else 0,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def inbox_payload(limit: int = 24) -> Dict[str, Any]:
    """Flat JSON shaped for snail.fetch field sinks."""
    raw = store.load("notifs.json", [])
    if not isinstance(raw, list):
        raw = []
    items: List[Dict[str, str]] = []
    for n in raw[: max(1, min(40, int(limit)))]:
        if not isinstance(n, dict):
            continue
        title = str(n.get("title") or n.get("kind") or "Note")[:48]
        body = str(n.get("body") or n.get("text") or "")[:96]
        kind = str(n.get("kind") or "info")[:16]
        when = str(n.get("at") or n.get("ts") or n.get("time") or "")[:32]
        items.append(
            {
                "title": title,
                "body": body,
                "kind": kind,
                "when": when,
                "line": f"{title}: {body}"[:80],
            }
        )
    return {
        "ok": True,
        "total": len(items),
        "name": "Digivice",
        "items": items,
    }


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":")).encode("utf-8")


def _make_handler() -> type:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            print(f"[snail-bridge] {self.address_string()} {fmt % args}", flush=True)

        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")

        def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._cors()
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            path = (self.path or "/").split("?", 1)[0]
            if path in ("/", "/snail", "/snail/v1", "/snail/v1/ping"):
                self._send(200, _json_bytes({"ok": True, "pong": True, "name": "Digivice"}))
                return
            if path == "/snail/v1/status":
                self._send(200, _json_bytes(status_dict()))
                return
            if path.startswith("/snail/v1/inbox"):
                limit = 24
                if "?" in (self.path or ""):
                    q = (self.path or "").split("?", 1)[1]
                    for part in q.split("&"):
                        if part.startswith("limit="):
                            try:
                                limit = int(part.split("=", 1)[1])
                            except ValueError:
                                pass
                self._send(200, _json_bytes(inbox_payload(limit)))
                return
            if path == "/snail/v1/host.txt":
                text = (
                    f"HOST={base_url()}\n"
                    f"# Paste into digivice.lua: local HOST = \"{base_url()}\"\n"
                ).encode("utf-8")
                self._send(200, text, "text/plain; charset=utf-8")
                return
            self._send(404, _json_bytes({"ok": False, "error": "not found"}))

    return Handler


def cert_paths() -> Tuple[Path, Path]:
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    return CERT_DIR / "cert.pem", CERT_DIR / "key.pem"


def tls_ready() -> bool:
    cert, key = cert_paths()
    return cert.is_file() and key.is_file()


def start(port: int = DEFAULT_PORT, *, tls: bool = False) -> str:
    """Start the bridge. Returns base URL. Raises on bind failure."""
    global _httpd, _thread, _port, _use_tls, _started_at
    stop()
    _port = int(port)
    _use_tls = bool(tls)
    handler = _make_handler()
    httpd = ThreadingHTTPServer(("0.0.0.0", _port), handler)
    if _use_tls:
        cert, key = cert_paths()
        if not cert.is_file() or not key.is_file():
            httpd.server_close()
            raise RuntimeError(
                f"TLS requested but missing {cert.name}/{key.name} in {CERT_DIR}"
            )
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(cert), str(key))
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    _httpd = httpd
    _started_at = time.time()

    def run() -> None:
        try:
            httpd.serve_forever(poll_interval=0.5)
        except Exception as e:
            print(f"[snail-bridge] server exit: {e}", flush=True)

    _thread = threading.Thread(target=run, name="snail-bridge", daemon=True)
    _thread.start()
    url = base_url()
    print(f"[snail-bridge] listening {url}", flush=True)
    return url


def stop() -> None:
    global _httpd, _thread, _started_at
    httpd = _httpd
    _httpd = None
    if httpd is not None:
        try:
            httpd.shutdown()
        except Exception:
            pass
        try:
            httpd.server_close()
        except Exception:
            pass
    if _thread is not None and _thread.is_alive():
        _thread.join(timeout=2.0)
    _thread = None
    _started_at = 0.0
