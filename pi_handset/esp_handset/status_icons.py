"""Status-bar glyphs: cellular bars + Wi‑Fi (painted, tiny Digivice sizes)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QWidget


def wifi_is_up() -> bool:
    """True if a wireless iface looks associated / has carrier."""
    for name in ("wlan0", "wlan1", "wlp1s0"):
        if _iface_up(name):
            return True
    try:
        net = Path("/sys/class/net")
        if net.is_dir():
            for p in net.iterdir():
                n = p.name
                if n.startswith("wlan") or n.startswith("wlp") or n.startswith("wlx"):
                    if _iface_up(n):
                        return True
    except OSError:
        pass
    try:
        r = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "dev"],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
        for line in (r.stdout or "").splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[1] == "wifi" and parts[2].startswith(
                "connected"
            ):
                return True
    except Exception:
        pass
    return False


def _iface_up(name: str) -> bool:
    base = Path("/sys/class/net") / name
    if not base.is_dir():
        return False
    try:
        oper = (base / "operstate").read_text().strip()
    except OSError:
        return False
    if oper != "up":
        return False
    # Prefer carrier if present
    try:
        carrier = (base / "carrier").read_text().strip()
        if carrier == "0":
            return False
    except OSError:
        pass
    return True


def parse_csq_rssi(csq_line: Optional[str]) -> Optional[int]:
    """Extract RSSI 0–31 from '+CSQ: n,m' (99 = unknown → None)."""
    if not csq_line:
        return None
    try:
        # "+CSQ: 18,0" or "CSQ 18"
        chunk = csq_line
        if ":" in chunk:
            chunk = chunk.split(":", 1)[1]
        chunk = chunk.strip().split(",")[0].strip()
        n = int(chunk)
        if n == 99 or n < 0:
            return None
        return max(0, min(31, n))
    except Exception:
        return None


def rssi_to_bars(rssi: Optional[int], *, max_bars: int = 4) -> int:
    """Map 0–31 CSQ to 0..max_bars (0 = no service / unknown)."""
    if rssi is None:
        return 0
    # Rough LTE-ish bands
    if rssi <= 1:
        return 0
    if rssi < 10:
        return 1
    if rssi < 15:
        return 2
    if rssi < 20:
        return 3
    return max_bars


class BtGlyph(QWidget):
    """Bluetooth mark — bright when a device is connected, dim + slash otherwise."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._on = False
        self.setFixedSize(12, 14)
        self.setToolTip("Bluetooth")

    def set_connected(self, on: bool) -> None:
        on = bool(on)
        if on == self._on:
            return
        self._on = on
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        col = QColor("#c8e0f0") if self._on else QColor("#4a5560")
        p.setPen(QPen(col, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        # Runic BT shape
        p.drawLine(6, 1, 6, 13)
        p.drawLine(6, 1, 10, 4)
        p.drawLine(10, 4, 6, 7)
        p.drawLine(6, 7, 10, 10)
        p.drawLine(10, 10, 6, 13)
        p.drawLine(6, 7, 2, 4)
        p.drawLine(6, 7, 2, 10)
        if not self._on:
            p.setPen(QPen(QColor("#ff6b6b"), 1.6, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(2, 2, 10, 12)


class BatGlyph(QWidget):
    """Battery icon: fill by % when UPS present; grey + slash when absent/USB."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pct = -1  # -1 = absent
        self._charging = False
        self.setFixedSize(18, 12)
        self.setToolTip("UPS battery")

    def set_status(self, percent: int, *, charging: bool = False) -> None:
        try:
            p = int(percent)
        except (TypeError, ValueError):
            p = -1
        if p < 0:
            p = -1
        else:
            p = max(0, min(100, p))
        if p == self._pct and bool(charging) == self._charging:
            return
        self._pct = p
        self._charging = bool(charging)
        if p < 0:
            self.setToolTip("No UPS — USB / external power")
        else:
            tag = f"UPS {p}%"
            if self._charging:
                tag += " charging"
            self.setToolTip(tag)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        absent = self._pct < 0
        if absent:
            col = QColor("#4a5560")
        elif self._pct >= 40:
            col = QColor("#5ec4a8")
        elif self._pct >= 20:
            col = QColor("#e8c66a")
        else:
            col = QColor("#e07070")
        # Body
        p.setPen(QPen(col, 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(1, 2, 13, 8, 1.5, 1.5)
        # Nipple
        p.setBrush(col)
        p.setPen(Qt.NoPen)
        p.drawRect(14, 4, 2, 4)
        if not absent:
            fill_w = max(1, int(11 * self._pct / 100.0))
            p.drawRoundedRect(2, 3, fill_w, 6, 1.0, 1.0)
            if self._charging:
                p.setPen(QPen(QColor("#0a1218"), 1.2))
                p.drawLine(5, 8, 7, 3)
                p.drawLine(7, 3, 8, 7)
                p.drawLine(8, 7, 10, 3)
        else:
            p.setPen(QPen(QColor("#ff6b6b"), 1.6, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(3, 2, 15, 10)


class HeltecGlyph(QWidget):
    """Heltec LoRa bridge mark — bright when the board answers status probes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._on = False
        self.setFixedSize(15, 14)
        self.setToolTip("Heltec LoRa — no response")

    def set_connected(self, on: bool) -> None:
        on = bool(on)
        if on == self._on:
            return
        self._on = on
        self.setToolTip(
            "Heltec LoRa — connected" if on else "Heltec LoRa — no response"
        )
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        col = QColor("#c8e0f0") if self._on else QColor("#4a5560")
        p.setPen(QPen(col, 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawLine(7, 3, 7, 12)
        p.drawLine(3, 13, 11, 13)
        p.drawArc(1, 1, 12, 10, 25 * 16, 130 * 16)
        if not self._on:
            p.setPen(QPen(QColor("#ff6b6b"), 1.6, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(2, 2, 12, 12)


def _btctl(*args: str, timeout: float = 1.5) -> str:
    try:
        r = subprocess.run(
            ["bluetoothctl", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return r.stdout or ""
    except Exception:
        return ""


def _bt_macs_from_devices(out: str) -> list:
    macs: list = []
    for line in (out or "").splitlines():
        parts = line.split()
        # "Device AA:BB:CC:DD:EE:FF Name…"
        if len(parts) >= 2 and parts[0] == "Device":
            macs.append(parts[1])
    return macs


def _bt_hid_input_present() -> bool:
    """True if a Bluetooth HID input device is attached (Bus=0005)."""
    try:
        text = Path("/proc/bus/input/devices").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    blocks = text.split("\n\n")
    for block in blocks:
        # Bus=0005 → Bluetooth; ignore empty name stubs
        if "Bus=0005" in block and "Name=" in block:
            return True
    return False


def bluetooth_connected() -> bool:
    """True if any Bluetooth device is connected (keyboard, headset, etc.)."""
    # BlueZ ≥ 5.65: filtered list
    out = _btctl("devices", "Connected")
    if _bt_macs_from_devices(out):
        return True

    # Older bluetoothctl: walk known/paired devices and check Connected
    macs: list = []
    for cmd in (("devices",), ("paired-devices",)):
        macs.extend(_bt_macs_from_devices(_btctl(*cmd)))
    seen = set()
    for mac in macs:
        if mac in seen:
            continue
        seen.add(mac)
        if len(seen) > 12:
            break
        info = _btctl("info", mac, timeout=0.8)
        for line in info.splitlines():
            if line.strip().lower() == "connected: yes":
                return True

    # HID keyboards/mice often show as Bus=0005 even when bluetoothctl is slow
    if _bt_hid_input_present():
        return True

    return False


class WifiGlyph(QWidget):
    """Fan arcs — bright when connected, dim + slash when not."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._on = False
        self.setFixedSize(16, 14)
        self.setToolTip("Wi‑Fi")

    def set_connected(self, on: bool) -> None:
        on = bool(on)
        if on == self._on:
            return
        self._on = on
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self._on
        col = QColor("#c8e0f0") if on else QColor("#4a5560")
        p.setPen(QPen(col, 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        # Nested arcs (bottom-centered)
        cx, cy = 8, 12
        for r in (3, 6, 9):
            p.drawArc(cx - r, cy - r, r * 2, r * 2, 45 * 16, 90 * 16)
        p.setBrush(col)
        p.setPen(Qt.NoPen)
        p.drawEllipse(cx - 1, cy - 1, 3, 3)
        if not on:
            p.setPen(QPen(QColor("#ff6b6b"), 1.6, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(3, 3, 13, 11)


class CellGlyph(QWidget):
    """Ascending signal bars (0–4)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bars = 0
        self._known = False
        self.setFixedSize(18, 14)
        self.setToolTip("Cellular")

    def set_bars(self, bars: int, *, known: bool = True) -> None:
        bars = max(0, min(4, int(bars)))
        if bars == self._bars and known == self._known:
            return
        self._bars = bars
        self._known = known
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = self._bars
        heights = (4, 7, 10, 13)
        gap = 2
        bw = 3
        x0 = 1
        base_y = 13
        for i, h in enumerate(heights):
            x = x0 + i * (bw + gap)
            y = base_y - h
            if self._known and i < n:
                p.setBrush(QColor("#c8e0f0"))
            else:
                p.setBrush(QColor("#3a4550"))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(x, y, bw, h, 1, 1)
        if not self._known or n == 0:
            # No-service slash
            p.setPen(QPen(QColor("#ff6b6b"), 1.4, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(2, 3, 15, 12)


def probe_status_icons(
    modem_signal_line: Optional[str] = None,
) -> Tuple[bool, int, bool]:
    """Return (wifi_on, cell_bars 0-4, cell_known)."""
    wifi = wifi_is_up()
    rssi = parse_csq_rssi(modem_signal_line)
    known = rssi is not None
    bars = rssi_to_bars(rssi) if known else 0
    return wifi, bars, known
