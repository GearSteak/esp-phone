"""Waveshare SIM7600G-H 4G HAT — AT over USB (SMS / GNSS).

Modem uses USB to the Pi (cable or Zero pogo). Heltec is a separate USB CDC
device. Optional stack under the Digivice LCD is mechanical only — see
docs/SIM7600_STACK.md.

Leave HAT PWR jumper on 3V3 (not D6) so GPIO 6 stays free for LCD joy Up.
Typical AT port: /dev/sim7600-at or ttyUSB2 (SimTech 1e0e).
"""

from __future__ import annotations

import glob
import os
import re
import threading
import time
from typing import Callable, Optional

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    serial = None
    list_ports = None

SmsHandler = Callable[[str, str], None]


class Sim7600:
    def __init__(self, port: Optional[str] = None, baud: int = 115200):
        self.port = port
        self.baud = baud
        self._ser = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sms_handlers: list[SmsHandler] = []
        self._rx_buf = ""

    @staticmethod
    def find_at_port(prefer: str = "/dev/sim7600-at") -> Optional[str]:
        """Prefer USB AT (/dev/sim7600-at / SimTech ttyUSB*)."""
        env = os.environ.get("SIM7600_PORT", "").strip()
        if env and os.path.exists(env):
            return env
        if prefer and os.path.exists(prefer):
            # Skip stale UART symlink left from older installs
            try:
                real = os.path.realpath(prefer)
                if real.endswith(("serial0", "ttyAMA0", "ttyS0")):
                    pass  # fall through to USB scan
                else:
                    return prefer
            except OSError:
                return prefer
        candidates: list[str] = []
        if list_ports:
            for p in list_ports.comports():
                vid = p.vid or 0
                desc = (p.description or "").lower()
                if vid in (0x1E0E, 0x05C6) or "simcom" in desc or "sim7600" in desc:
                    candidates.append(p.device)
        for path in sorted(glob.glob("/dev/ttyUSB*"), reverse=True):
            if path not in candidates:
                candidates.append(path)
        for want in ("ttyUSB2", "ttyUSB3", "ttyUSB1"):
            for c in candidates:
                if c.endswith(want):
                    return c
        return candidates[0] if candidates else None

    def open(self) -> None:
        if serial is None:
            raise RuntimeError("pyserial not installed")
        port = self.port or self.find_at_port()
        if not port:
            raise RuntimeError(
                "No SIM7600 AT port (plug HAT USB / Zero pogo; check /dev/ttyUSB*)"
            )
        self.port = port
        self._ser = serial.Serial(port, self.baud, timeout=0.2)
        self._at("ATE0")
        self._at("AT+CMGF=1")  # text mode
        self._at("AT+CNMI=2,1,0,0,0")
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

    def on_sms(self, handler: SmsHandler) -> None:
        self._sms_handlers.append(handler)

    def _at(self, cmd: str, wait: float = 1.5) -> str:
        if not self._ser:
            raise RuntimeError("modem not open")
        with self._lock:
            self._ser.write((cmd + "\r").encode("utf-8", errors="replace"))
            deadline = time.time() + wait
            out = ""
            while time.time() < deadline:
                chunk = self._ser.read(256)
                if chunk:
                    out += chunk.decode("utf-8", errors="replace")
                    if "OK" in out or "ERROR" in out or ">" in out:
                        break
                else:
                    time.sleep(0.02)
            return out

    def send_sms(self, number: str, text: str) -> bool:
        num = number.strip()
        body = text.replace("\n", " ").strip()
        if not num or not body:
            return False
        if not self._ser:
            return False
        with self._lock:
            self._ser.write(f'AT+CMGS="{num}"\r'.encode("utf-8"))
            deadline = time.time() + 3
            buf = ""
            while time.time() < deadline:
                chunk = self._ser.read(64)
                if chunk:
                    buf += chunk.decode("utf-8", errors="replace")
                    if ">" in buf:
                        break
                else:
                    time.sleep(0.02)
            self._ser.write((body + "\x1a").encode("utf-8", errors="replace"))
            deadline = time.time() + 30
            buf = ""
            while time.time() < deadline:
                chunk = self._ser.read(256)
                if chunk:
                    buf += chunk.decode("utf-8", errors="replace")
                    if "OK" in buf:
                        return True
                    if "ERROR" in buf:
                        return False
                else:
                    time.sleep(0.05)
        return False

    def gps_on(self) -> bool:
        """Power on GNSS (SIM7600: CGPS; some fw also accept CGNSSPWR)."""
        if not self._ser:
            raise RuntimeError("SIM7600 not open — check USB /dev/ttyUSB*")
        # Prefer classic SIM7600 standalone GPS; try a few variants
        for cmd, wait in (
            ("AT+CGPS=1", 8.0),
            ("AT+CGPS=1,1", 8.0),
            ("AT+CGNSSPWR=1", 15.0),
        ):
            r = self._at(cmd, wait=wait)
            if "OK" in r or "READY" in r.upper():
                return True
        # Already on often returns ERROR — treat as ok if INFO responds
        info = self._at("AT+CGPSINFO", wait=3.0)
        if "+CGPSINFO:" in info:
            return True
        raise RuntimeError(
            "GNSS failed to start.\n"
            "Check GNSS antenna (IPEX),\n"
            "modem USB, and AT port."
        )

    def gps_off(self) -> bool:
        if not self._ser:
            return False
        r = self._at("AT+CGPS=0", wait=3.0)
        self._at("AT+CGNSSPWR=0", wait=5.0)
        return "OK" in r

    def gps_info(self) -> Optional[str]:
        """Raw +CGPSINFO line, or None."""
        if not self._ser:
            raise RuntimeError("SIM7600 not open")
        r = self._at("AT+CGPSINFO", wait=3.0)
        for line in r.splitlines():
            if "+CGPSINFO:" in line:
                return line.strip()
        if "ERROR" in r:
            raise RuntimeError("AT+CGPSINFO ERROR — turn GPS on first")
        return None

    @staticmethod
    def _nmea_ddmm_to_deg(ddmm: str, hemi: str) -> Optional[float]:
        try:
            v = float(ddmm)
        except ValueError:
            return None
        deg = int(v // 100)
        minutes = v - deg * 100
        dec = deg + minutes / 60.0
        if hemi.upper() in ("S", "W"):
            dec = -dec
        return dec

    def gps_fix(self) -> dict:
        """Parsed GNSS state for UI.

        Returns keys: ok, searching, raw, lat, lon, alt, summary, detail
        """
        out: dict = {
            "ok": False,
            "searching": False,
            "raw": "",
            "lat": None,
            "lon": None,
            "alt": None,
            "summary": "No data",
            "detail": "",
        }
        raw = self.gps_info()
        if not raw:
            out["summary"] = "No CGPSINFO yet"
            out["detail"] = "Start GPS, wait outdoors 30–120s"
            out["searching"] = True
            return out
        out["raw"] = raw
        payload = raw.split(":", 1)[-1].strip()
        parts = [p.strip() for p in payload.split(",")]
        # Empty fix: +CGPSINFO:,,,,,,,,
        if not parts or not parts[0]:
            out["searching"] = True
            out["summary"] = "Searching for satellites"
            out["detail"] = (
                "Needs GNSS antenna + sky view.\n"
                "Cold start often 30–120 seconds."
            )
            return out
        lat = self._nmea_ddmm_to_deg(parts[0], parts[1] if len(parts) > 1 else "N")
        lon = self._nmea_ddmm_to_deg(
            parts[2] if len(parts) > 2 else "",
            parts[3] if len(parts) > 3 else "E",
        )
        alt = None
        if len(parts) > 6 and parts[6]:
            try:
                alt = float(parts[6])
            except ValueError:
                alt = None
        if lat is None or lon is None:
            out["searching"] = True
            out["summary"] = "Searching for satellites"
            out["detail"] = "Partial CGPSINFO — keep waiting outdoors"
            return out
        out["ok"] = True
        out["lat"] = lat
        out["lon"] = lon
        out["alt"] = alt
        out["summary"] = f"{lat:.5f}, {lon:.5f}"
        detail = f"Lat {lat:.6f}\nLon {lon:.6f}"
        if alt is not None:
            detail += f"\nAlt {alt:.1f} m"
        if len(parts) > 5 and parts[4] and parts[5]:
            detail += f"\nUTC {parts[4]} {parts[5]}"
        out["detail"] = detail
        return out

    def signal(self) -> Optional[str]:
        r = self._at("AT+CSQ", wait=1.5)
        for line in r.splitlines():
            if "+CSQ:" in line:
                return line.strip()
        return None

    def poll_unread_sms(self) -> None:
        """Poll storage for unread SMS and notify handlers."""
        if not self._ser:
            return
        with self._lock:
            self._ser.write(b'AT+CMGL="REC UNREAD"\r')
            time.sleep(0.8)
            raw = ""
            deadline = time.time() + 3
            while time.time() < deadline:
                chunk = self._ser.read(512)
                if chunk:
                    raw += chunk.decode("utf-8", errors="replace")
                    if "OK" in raw or "ERROR" in raw:
                        break
                else:
                    time.sleep(0.05)
        parts = re.split(r"\+CMGL:\s*", raw)
        for part in parts[1:]:
            lines = part.strip().splitlines()
            if not lines:
                continue
            header = lines[0]
            nums = re.findall(r'"([^"]*)"', header)
            number = nums[1] if len(nums) > 1 else "?"
            text = " ".join(lines[1:]).strip()
            if text.endswith("OK"):
                text = text[:-2].strip()
            idx_m = re.match(r"(\d+)", header)
            if idx_m:
                try:
                    self._at(f"AT+CMGD={idx_m.group(1)}", wait=1.0)
                except Exception:
                    pass
            for h in self._sms_handlers:
                try:
                    h(number, text)
                except Exception:
                    pass

    def _reader(self) -> None:
        """Background: URCs + periodic unread poll (serial locked vs AT cmds)."""
        last_poll = 0.0
        while not self._stop.is_set():
            chunk = b""
            try:
                with self._lock:
                    if self._ser:
                        chunk = self._ser.read(256)
            except Exception:
                time.sleep(0.3)
                continue
            if chunk:
                self._rx_buf += chunk.decode("utf-8", errors="replace")
                while "\n" in self._rx_buf:
                    line, self._rx_buf = self._rx_buf.split("\n", 1)
                    line = line.strip()
                    if line.startswith("+CMTI:"):
                        last_poll = 0
            now = time.time()
            if now - last_poll > 8.0:
                last_poll = now
                try:
                    self.poll_unread_sms()
                except Exception:
                    pass
            if not chunk:
                time.sleep(0.05)
