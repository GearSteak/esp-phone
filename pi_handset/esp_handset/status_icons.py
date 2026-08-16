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
    for name in ("wlan0", "wlan1", "wlp1s0", "wlx"):
        # exact names first
        if name == "wlx":
            net = Path("/sys/class/net")
            if not net.is_dir():
                continue
            for p in net.iterdir():
                if p.name.startswith("wlx") or p.name.startswith("wl"):
                    if _iface_up(p.name):
                        return True
            continue
        if _iface_up(name):
            return True
    # nmcli fallback
    try:
        r = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "dev"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        for line in (r.stdout or "").splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[1] == "wifi" and parts[2] in (
                "connected",
                "connecting (getting IP configuration)",
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
