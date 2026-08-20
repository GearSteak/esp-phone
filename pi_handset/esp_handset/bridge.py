"""ESP handset CDC bridge — keyboard / volume only."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Deque, Optional

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    serial = None
    list_ports = None


EventHandler = Callable[[str, str], None]


class EspBridge:
    def __init__(self, port: Optional[str] = None, baud: int = 115200):
        self.port = port
        self.baud = baud
        self._ser = None
        self._rx: Deque[str] = deque(maxlen=500)
        self._handlers: list[EventHandler] = []
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    @staticmethod
    def find_port(prefer: str = "/dev/esp-bridge") -> Optional[str]:
        import os

        env = os.environ.get("ESP_BRIDGE_PORT", "").strip()
        if env and os.path.exists(env):
            return env
        if os.path.exists(prefer):
            return prefer
        if os.environ.get("ESP_BRIDGE_UART", "").strip().lower() in (
            "1",
            "true",
            "yes",
        ):
            for p in (
                "/dev/esp-bridge-uart",
                "/dev/ttyAMA0",
                "/dev/serial0",
                "/dev/ttyS0",
            ):
                if os.path.exists(p):
                    return p
        if list_ports is None:
            return None
        for p in list_ports.comports():
            desc = (p.description or "").lower()
            vid = p.vid or 0
            if vid == 0x303A or "esp" in desc or "usb jtag" in desc:
                return p.device
        ports = list(list_ports.comports()) if list_ports else []
        return ports[0].device if ports else None

    def open(self) -> None:
        if serial is None:
            raise RuntimeError("pyserial not installed")
        port = self.port or self.find_port()
        if not port:
            raise RuntimeError("No ESP serial port found")
        self.port = port
        self._ser = serial.Serial(port, self.baud, timeout=0.05)
        self._stop.clear()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._ser:
            self._ser.close()
            self._ser = None

    def on_event(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    def send(self, line: str) -> None:
        if not self._ser:
            raise RuntimeError("bridge not open")
        data = (line.strip() + "\n").encode("utf-8", errors="replace")
        with self._lock:
            self._ser.write(data)

    def _reader(self) -> None:
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = self._ser.read(256) if self._ser else b""
            except Exception:
                time.sleep(0.2)
                continue
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                self._rx.append(text)
                kind = text.split(" ", 1)[0]
                for h in self._handlers:
                    try:
                        h(kind, text)
                    except Exception:
                        pass

    def request_status(self) -> None:
        self.send("STATUS")

    def ping(self) -> None:
        self.send("PING")

    def lora_send(self, text: str, target: int = 0) -> None:
        if target:
            self.send(f"LORA SEND {target} {text}")
        else:
            self.send(f"LORA SEND {text}")

    def lora_sos(self) -> None:
        self.send("LORA SOS")

    def notif(self, title: str, body: str, kind: str = "info") -> None:
        """Show alert on ESP ST7735 notify panel. Format: NOTIF kind|title|body"""
        t = (title or "Alert").replace("|", "/").replace("\n", " ")[:40]
        b = (body or "").replace("|", "/").replace("\n", " ")[:80]
        k = (kind or "info").replace("|", "/")[:16]
        self.send(f"NOTIF {k}|{t}|{b}")

    def notif_clear(self) -> None:
        self.send("CLEAR")

    def steps_query(self) -> None:
        self.send("STEPS?")

    def steps_reset(self) -> None:
        self.send("STEPS RESET")
