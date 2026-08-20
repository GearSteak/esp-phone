"""Heltec Digivice bridge — USB CDC, GPIO UART, or soft-UART (preferred Digivice).

Digivice power rules:
  • USB port = audio dongle only (modem / Heltec trip the Pi polyfuse)
  • /dev/serial0 = SIM7600 AT
  • I2C1 = CardKB
  • BCM23/24 soft-UART = Heltec notify + battery (LiPo, common GND only)
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Callable, Deque, Optional, Union

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
        self._soft = None
        self._rx: Deque[str] = deque(maxlen=500)
        self._handlers: list[EventHandler] = []
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    @staticmethod
    def find_port(prefer: str = "/dev/esp-bridge") -> Optional[str]:
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
        from esp_handset.softuart_pigpio import SoftUartLink, softuart_enabled

        self._stop.clear()
        if softuart_enabled() or (
            os.environ.get("ESP_BRIDGE_SOFTUART", "").strip().lower()
            in ("1", "true", "yes", "on")
        ):
            link = SoftUartLink()
            link.open()
            self._soft = link
            self.port = f"softuart:tx{link.tx}/rx{link.rx}@{link.baud}"
            self._thread = threading.Thread(target=self._reader_soft, daemon=True)
            self._thread.start()
            return

        if serial is None:
            raise RuntimeError("pyserial not installed")
        port = self.port or self.find_port()
        if not port:
            raise RuntimeError(
                "No ESP serial port — for Digivice set ESP_BRIDGE_SOFTUART=1 "
                "(Heltec on BCM23/24, battery powered)"
            )
        self.port = port
        self._ser = serial.Serial(port, self.baud, timeout=0.05)
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._ser:
            self._ser.close()
            self._ser = None
        if self._soft:
            self._soft.close()
            self._soft = None

    def on_event(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    def send(self, line: str) -> None:
        data = (line.strip() + "\n").encode("utf-8", errors="replace")
        with self._lock:
            if self._soft is not None:
                self._soft.write(data)
                return
            if not self._ser:
                raise RuntimeError("bridge not open")
            self._ser.write(data)

    def _dispatch(self, text: str) -> None:
        self._rx.append(text)
        kind = text.split(" ", 1)[0]
        for h in self._handlers:
            try:
                h(kind, text)
            except Exception:
                pass

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
                if text:
                    self._dispatch(text)

    def _reader_soft(self) -> None:
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = self._soft.read(256) if self._soft else b""
            except Exception:
                time.sleep(0.2)
                continue
            if not chunk:
                time.sleep(0.02)
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    self._dispatch(text)

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
        t = (title or "Alert").replace("|", "/").replace("\n", " ")[:40]
        b = (body or "").replace("|", "/").replace("\n", " ")[:80]
        k = (kind or "info").replace("|", "/")[:16]
        self.send(f"NOTIF {k}|{t}|{b}")

    def notif_clear(self) -> None:
        self.send("CLEAR")

    def battery_query(self) -> None:
        self.send("BATTERY")

    def steps_query(self) -> None:
        self.send("STEPS?")

    def steps_reset(self) -> None:
        self.send("STEPS RESET")
