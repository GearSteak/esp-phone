"""Waveshare SIM7600G-H 4G HAT — AT over USB *or* Pi GPIO UART.

USB (SimTech 1e0e → /dev/sim7600-at / ttyUSB*) or HAT on the 40-pin header
using /dev/serial0 (GPIO 14/15). Mode: /etc/esp-handset/modem-backend
  usb | uart | auto
Digivice (USB audio owns the only USB port): set modem-backend=uart.
auto = try USB first, then UART (legacy).

Leave HAT PWR jumper on 3V3 (not D6) so GPIO 6 stays free for Digivice Down.
"""

from __future__ import annotations

import glob
import os
import re
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    serial = None
    list_ports = None

SmsHandler = Callable[[str, str], None]

_UART_PORTS = (
    "/dev/serial0",
    "/dev/ttyAMA0",
    "/dev/ttyS0",
)


def modem_backend() -> str:
    """usb | uart | auto"""
    env = (os.environ.get("SIM7600_BACKEND") or "").strip().lower()
    if env in ("usb", "uart", "auto", "gpio", "serial"):
        if env in ("gpio", "serial"):
            return "uart"
        return env
    for path in (
        Path("/etc/esp-handset/modem-backend"),
        Path.home() / ".esp-handset" / "modem-backend",
    ):
        try:
            if path.is_file():
                raw = path.read_text(encoding="utf-8").strip().lower().split()[0]
                if raw in ("gpio", "serial"):
                    return "uart"
                if raw in ("usb", "uart", "auto"):
                    return raw
        except (OSError, IndexError):
            continue
    if Path("/etc/esp-handset/modem-uart").is_file():
        return "uart"
    return "auto"


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
    def _is_uart_path(path: str) -> bool:
        real = path
        try:
            real = os.path.realpath(path)
        except OSError:
            pass
        base = os.path.basename(real)
        return base in ("serial0", "ttyAMA0", "ttyS0") or path in _UART_PORTS

    @staticmethod
    def uart_candidates() -> List[str]:
        out: List[str] = []
        for p in _UART_PORTS:
            if os.path.exists(p) and p not in out:
                out.append(p)
        return out

    @staticmethod
    def find_at_port(prefer: str = "/dev/sim7600-at") -> Optional[str]:
        """Pick AT port: env → symlink → USB SimTech → GPIO UART."""
        backend = modem_backend()
        env = os.environ.get("SIM7600_PORT", "").strip()
        if env and os.path.exists(env):
            return env

        def _usb_pick() -> Optional[str]:
            if prefer and os.path.exists(prefer):
                try:
                    real = os.path.realpath(prefer)
                    if not Sim7600._is_uart_path(prefer) and not Sim7600._is_uart_path(
                        real
                    ):
                        return prefer
                except OSError:
                    return prefer
            candidates: list[str] = []
            if list_ports:
                for p in list_ports.comports():
                    vid = p.vid or 0
                    desc = (p.description or "").lower()
                    if (
                        vid in (0x1E0E, 0x05C6)
                        or "simcom" in desc
                        or "sim7600" in desc
                    ):
                        candidates.append(p.device)
            ranked: list[str] = []
            for want in (
                "ttyUSB2",
                "ttyUSB3",
                "ttyUSB1",
                "ttyUSB4",
                "ttyUSB0",
                "ttyUSB5",
            ):
                for c in candidates:
                    if c.endswith(want) and c not in ranked:
                        ranked.append(c)
            for c in candidates:
                if c not in ranked:
                    ranked.append(c)
            if ranked:
                return ranked[0]
            usbs = sorted(glob.glob("/dev/ttyUSB*"))
            return usbs[2] if len(usbs) > 2 else (usbs[0] if usbs else None)

        def _uart_pick() -> Optional[str]:
            if prefer and os.path.exists(prefer) and Sim7600._is_uart_path(prefer):
                return prefer
            if prefer and os.path.exists(prefer):
                try:
                    if Sim7600._is_uart_path(os.path.realpath(prefer)):
                        return prefer
                except OSError:
                    pass
            uarts = Sim7600.uart_candidates()
            return uarts[0] if uarts else None

        if backend == "uart":
            return _uart_pick() or _usb_pick()
        if backend == "usb":
            return _usb_pick()
        return _usb_pick() or _uart_pick()

    @staticmethod
    def list_usb_serial() -> list[str]:
        """One line per /dev/ttyUSB* with VID if known."""
        lines: list[str] = []
        by_dev: dict[str, object] = {}
        if list_ports:
            for p in list_ports.comports():
                by_dev[p.device] = p
        for path in sorted(glob.glob("/dev/ttyUSB*")):
            p = by_dev.get(path)
            if p is not None:
                vid = getattr(p, "vid", None) or 0
                pid = getattr(p, "pid", None) or 0
                desc = (getattr(p, "description", None) or "")[:28]
                tag = ""
                if vid == 0x1E0E:
                    tag = " SIM7600-modem"
                elif vid == 0x10C4:
                    tag = " CP2102-UART-jack?"
                elif vid == 0x05C6:
                    tag = " Qualcomm"
                lines.append(
                    f"{os.path.basename(path)} {vid:04x}:{pid:04x}{tag} {desc}"
                )
            else:
                lines.append(os.path.basename(path))
        return lines

    @staticmethod
    def diagnose() -> str:
        """Human-readable modem presence (USB and/or GPIO UART)."""
        lines: list[str] = []
        backend = modem_backend()
        lines.append(f"backend: {backend}")
        prefer = "/dev/sim7600-at"
        if os.path.exists(prefer):
            try:
                real = os.path.realpath(prefer)
                lines.append(f"symlink: {prefer}")
                lines.append(f" → {real}")
                if Sim7600._is_uart_path(real):
                    lines.append("(GPIO UART OK)")
            except OSError:
                lines.append(f"{prefer} exists")
        else:
            lines.append("no /dev/sim7600-at yet")
        uarts = Sim7600.uart_candidates()
        if uarts:
            lines.append("GPIO UART:")
            for u in uarts:
                lines.append(f"  {u}")
        else:
            lines.append("no /dev/serial0 (enable UART?)")
        usb_lines = Sim7600.list_usb_serial()
        if usb_lines:
            lines.append("USB serial:")
            lines.extend("  " + x for x in usb_lines)
        else:
            lines.append("no /dev/ttyUSB*")
        if backend in ("uart", "auto") and not uarts and not usb_lines:
            lines.append("")
            lines.append("GPIO UART tips:")
            lines.append("• PWR→3V3 on HAT")
            lines.append("• enable_uart=1 / reboot")
            lines.append("• echo uart | sudo tee /etc/esp-handset/modem-backend")
        found = Sim7600.find_at_port()
        if found:
            lines.append(f"pick: {found}")
        else:
            lines.append("AT port: NOT FOUND")
        return "\n".join(lines)

    @staticmethod
    def _probe_at(port: str, baud: int = 115200) -> bool:
        """True if this serial port answers AT with OK."""
        if serial is None:
            return False
        try:
            ser = serial.Serial(port, baud, timeout=0.4)
        except Exception:
            return False
        try:
            ser.reset_input_buffer()
            ser.write(b"AT\r")
            deadline = time.time() + 1.2
            buf = ""
            while time.time() < deadline:
                chunk = ser.read(64)
                if chunk:
                    buf += chunk.decode("utf-8", errors="replace")
                    if "OK" in buf:
                        return True
                    if "ERROR" in buf:
                        break
                else:
                    time.sleep(0.05)
            return False
        except Exception:
            return False
        finally:
            try:
                ser.close()
            except Exception:
                pass

    @classmethod
    def find_live_at_port(cls, baud: int = 115200) -> Optional[str]:
        """Scan USB + GPIO UART; return first that answers AT."""
        backend = modem_backend()
        ordered: list[str] = []
        prefer = cls.find_at_port()
        if prefer:
            ordered.append(prefer)

        def add_usb() -> None:
            if list_ports:
                for p in list_ports.comports():
                    vid = p.vid or 0
                    if vid in (0x1E0E, 0x05C6) and p.device not in ordered:
                        ordered.append(p.device)
            for path in sorted(glob.glob("/dev/ttyUSB*")):
                if path not in ordered:
                    ordered.append(path)

        def add_uart() -> None:
            for path in cls.uart_candidates():
                if path not in ordered:
                    ordered.append(path)

        if backend == "uart":
            add_uart()
            add_usb()
        elif backend == "usb":
            add_usb()
        else:
            add_usb()
            add_uart()

        for port in ordered:
            if cls._probe_at(port, baud=baud):
                return port
        return None

    def open(self, retries: int = 1, retry_s: float = 2.0) -> None:
        if serial is None:
            raise RuntimeError("pyserial not installed")
        last_err: Optional[Exception] = None
        for _attempt in range(max(1, retries)):
            port = (
                self.port
                or self.find_live_at_port(baud=self.baud)
                or self.find_at_port()
            )
            if not port:
                last_err = RuntimeError(
                    "No SIM7600 AT port yet.\n"
                    "GPIO: serial0 + PWR→3V3\n"
                    "or USB modem jack."
                )
                time.sleep(retry_s)
                continue
            try:
                self.port = port
                self._ser = serial.Serial(port, self.baud, timeout=0.2)
                r = self._at("AT", wait=1.5)
                if "OK" not in r:
                    self._ser.close()
                    self._ser = None
                    last_err = RuntimeError(f"No AT OK on {port}")
                    time.sleep(retry_s)
                    continue
                return
            except Exception as e:
                last_err = e
                try:
                    if self._ser:
                        self._ser.close()
                except Exception:
                    pass
                self._ser = None
                time.sleep(retry_s)
        raise last_err or RuntimeError("SIM7600 open failed")

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
            raise RuntimeError("SIM7600 not open — check UART/USB")
        for cmd, wait in (
            ("AT+CGPS=1", 8.0),
            ("AT+CGPS=1,1", 8.0),
            ("AT+CGNSSPWR=1", 15.0),
        ):
            r = self._at(cmd, wait=wait)
            if "OK" in r or "READY" in r.upper():
                return True
        info = self._at("AT+CGPSINFO", wait=3.0)
        if "+CGPSINFO:" in info:
            return True
        raise RuntimeError(
            "GNSS failed to start.\n"
            "Check GNSS antenna (IPEX),\n"
            "modem link, and AT port."
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
