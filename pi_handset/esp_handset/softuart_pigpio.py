"""Pigpio soft-UART link to Heltec DigiUART (GPIO ↔ Heltec UART0).

Digivice buses:
  USB          → audio only (modem/Heltec trip the Pi polyfuse)
  /dev/serial0 → SIM7600
  I2C1         → CardKB
  BCM23 / 24   → Heltec notify + battery (this module)

Heltec is LiPo-powered. Common GND only — no USB cable in normal use.
Requires: sudo apt install pigpio python3-pigpio && sudo systemctl enable --now pigpiod
"""
from __future__ import annotations

import os
import threading
import time
from typing import Callable, Optional

# Header pin 16 = BCM23 (Pi TX → Heltec RX 44)
# Header pin 18 = BCM24 (Pi RX ← Heltec TX 43)
DEFAULT_TX = int(os.environ.get("ESP_BRIDGE_SOFT_TX", "23") or "23")
DEFAULT_RX = int(os.environ.get("ESP_BRIDGE_SOFT_RX", "24") or "24")
DEFAULT_BAUD = int(os.environ.get("ESP_BRIDGE_SOFT_BAUD", "9600") or "9600")


class SoftUartLink:
    """Minimal serial-like link using pigpio bit-bang UART."""

    def __init__(
        self,
        *,
        tx: int = DEFAULT_TX,
        rx: int = DEFAULT_RX,
        baud: int = DEFAULT_BAUD,
    ) -> None:
        self.tx = int(tx)
        self.rx = int(rx)
        self.baud = int(baud)
        self._pi = None
        self._lock = threading.Lock()
        self._opened = False

    def open(self) -> None:
        try:
            import pigpio  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "python3-pigpio required for Heltec soft-UART "
                "(sudo apt install python3-pigpio pigpio)"
            ) from e
        pi = pigpio.pi()
        if not pi.connected:
            raise RuntimeError(
                "pigpiod not running — sudo systemctl enable --now pigpiod"
            )
        self._pi = pi
        pi.set_mode(self.tx, pigpio.OUTPUT)
        pi.write(self.tx, 1)  # idle high
        pi.set_mode(self.rx, pigpio.INPUT)
        pi.set_pull_up_down(self.rx, pigpio.PUD_UP)
        try:
            pi.bb_serial_read_close(self.rx)
        except Exception:
            pass
        err = pi.bb_serial_read_open(self.rx, self.baud, 8)
        if err != 0:
            pi.stop()
            self._pi = None
            raise RuntimeError(f"bb_serial_read_open failed ({err})")
        self._opened = True

    def close(self) -> None:
        pi = self._pi
        self._pi = None
        self._opened = False
        if pi is None:
            return
        try:
            pi.bb_serial_read_close(self.rx)
        except Exception:
            pass
        try:
            pi.stop()
        except Exception:
            pass

    def write(self, data: bytes) -> None:
        if not self._opened or self._pi is None:
            raise RuntimeError("soft-UART not open")
        pi = self._pi
        with self._lock:
            pi.wave_clear()
            pi.wave_add_serial(self.tx, self.baud, data)
            wid = pi.wave_create()
            if wid < 0:
                raise RuntimeError(f"wave_create failed ({wid})")
            pi.wave_send_once(wid)
            while pi.wave_tx_busy():
                time.sleep(0.002)
            pi.wave_delete(wid)

    def read(self, max_bytes: int = 256) -> bytes:
        if not self._opened or self._pi is None:
            return b""
        try:
            count, data = self._pi.bb_serial_read(self.rx)
        except Exception:
            return b""
        if count and data:
            return bytes(data[:count])
        return b""


def softuart_enabled() -> bool:
    v = os.environ.get("ESP_BRIDGE_SOFTUART", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    # Digivice default when explicitly configured in /etc/esp-handset/env
    try:
        path = "/etc/esp-handset/env"
        if os.path.isfile(path):
            text = open(path, encoding="utf-8", errors="replace").read()
            for line in text.splitlines():
                if line.strip().startswith("ESP_BRIDGE_SOFTUART="):
                    val = line.split("=", 1)[1].strip().strip('"').lower()
                    return val in ("1", "true", "yes", "on")
    except OSError:
        pass
    return False
