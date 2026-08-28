"""Per-emulator ROM shelf — SNES Classic–style cover carousel for Digivice."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt5.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import QWidget

# Accent per system key (fallback: blue)
_ACCENTS = {
    "gb": "#8bac0f",
    "nes": "#e52521",
    "smsgg": "#1a3c6e",
    "gba": "#6a5acd",
    "snes": "#7b68c8",
    "genesis": "#1a1a2e",
    "ps1": "#003087",
}


@dataclass
class RomEntry:
    path: Path
    title: str
    cover: Optional[Path] = None
    from_cart: bool = False


def _pretty_title(name: str) -> str:
    stem = Path(name).stem
    stem = stem.replace("_", " ").replace(".", " ")
    # Strip common dump tags in brackets/parens for display only
    out = []
    depth_b = depth_p = 0
    for ch in stem:
        if ch == "[":
            depth_b += 1
            continue
        if ch == "]" and depth_b:
            depth_b -= 1
            continue
        if ch == "(":
            depth_p += 1
            continue
        if ch == ")" and depth_p:
            depth_p -= 1
            continue
        if depth_b or depth_p:
            continue
        out.append(ch)
    cleaned = "".join(out).strip(" -_")
    return cleaned or stem


def _cover_match_key(name: str) -> str:
    """Normalize ROM/cover names for forgiving local artwork matching."""
    stem = Path(name).stem
    stem = re.sub(r"\s*[\(\[].*?[\)\]]", " ", stem)
    stem = re.sub(r"[^a-zA-Z0-9]+", " ", stem).casefold()
    words = [
        word
        for word in stem.split()
        if word not in {"version", "rev", "revision"}
    ]
    return " ".join(words)


def find_cover(rom: Path, folder: str, data_root: Path) -> Optional[Path]:
    """Find exact or normalized matching artwork near the ROM."""
    stem = rom.stem
    names = (
        f"{stem}.png",
        f"{stem}.jpg",
        f"{stem}.jpeg",
        f"{stem}.webp",
        f"{rom.name}.png",
        f"{rom.name}.jpg",
    )
    dirs = (
        rom.parent / "covers",
        rom.parent,
        data_root / "roms" / folder / "covers",
        data_root / "covers" / folder,
    )
    for d in dirs:
        if not d.is_dir() and d != rom.parent:
            continue
        for name in names:
            p = d / name
            if p.is_file():
                return p
    wanted = _cover_match_key(rom.name)
    if wanted:
        for d in dirs:
            if not d.is_dir():
                continue
            try:
                candidates = sorted(d.iterdir(), key=lambda p: p.name.casefold())
            except OSError:
                continue
            for p in candidates:
                if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                    continue
                if _cover_match_key(p.name) == wanted:
                    return p
    return None


def _scale_for_offset(off: float) -> float:
    d = abs(off)
    if d < 0.08:
        return 1.0
    if d < 1.05:
        return 0.58 + 0.42 * max(0.0, 1.0 - d)
    if d < 2.05:
        return 0.38
    return 0.28


class RomShelf(QWidget):
    """Horizontal cover shelf: big center art, smaller neighbors, ←→ browse."""

    activated = pyqtSignal()  # Confirm / digi_confirm on center ROM
    index_changed = pyqtSignal(int)

    def __init__(
        self,
        *,
        system_key: str = "",
        glyph: str = "◆",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._entries: List[RomEntry] = []
        self._index = 0
        self._shift = 0.0
        self._anim: Optional[QPropertyAnimation] = None
        self._pending_index = 0
        self._system_key = system_key
        self._glyph = glyph or "◆"
        self._accent = QColor(_ACCENTS.get(system_key, "#58a6ff"))
        self._cover_cache: dict = {}
        self.setMinimumHeight(168)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setProperty("digiPad", True)

    def _get_shift(self) -> float:
        return self._shift

    def _set_shift(self, v: float) -> None:
        self._shift = v
        self.update()

    shift = pyqtProperty(float, _get_shift, _set_shift)

    def set_system(self, key: str, glyph: str) -> None:
        self._system_key = key
        self._glyph = glyph or "◆"
        self._accent = QColor(_ACCENTS.get(key, "#58a6ff"))
        self._cover_cache.clear()
        self.update()

    def set_entries(self, entries: List[RomEntry], index: int = 0) -> None:
        self._entries = list(entries)
        self._cover_cache.clear()
        if self._entries:
            self._index = max(0, min(index, len(self._entries) - 1))
        else:
            self._index = 0
        self._shift = 0.0
        self.update()
        self.index_changed.emit(self._index)

    def current(self) -> Optional[RomEntry]:
        if not self._entries:
            return None
        return self._entries[self._index]

    def current_path(self) -> Optional[Path]:
        cur = self.current()
        return cur.path if cur else None

    def count(self) -> int:
        return len(self._entries)

    def _commit_pending(self) -> None:
        """Apply in-flight index so interrupting a scroll never snaps backward."""
        if getattr(self, "_pending_index", None) is None:
            return
        if self._pending_index != self._index:
            self._index = int(self._pending_index)
            self.index_changed.emit(self._index)
        self._shift = 0.0

    def _warm_covers(self, center: int) -> None:
        """Decode neighbor art before the slide so paint stays smooth."""
        n = len(self._entries)
        if n == 0:
            return
        for off in (-2, -1, 0, 1, 2):
            if n < abs(off) + 1 and off != 0:
                continue
            entry = self._entries[(center + off) % n]
            try:
                self._pixmap_for(entry, 96 if off == 0 else 56, 84 if off == 0 else 50)
            except Exception:
                pass

    def move_by(self, delta: int) -> bool:
        if not self._entries or delta == 0:
            return False
        n = len(self._entries)
        if n == 1:
            return True
        # Mid-scroll press: finish the current step, then animate the next.
        if self._anim is not None:
            try:
                self._anim.finished.disconnect()
            except Exception:
                pass
            self._anim.stop()
            self._anim = None
            self._commit_pending()
        direction = 1 if delta > 0 else -1
        self._pending_index = (self._index + direction) % n
        self._warm_covers(self._pending_index)
        self._anim = QPropertyAnimation(self, b"shift", self)
        self._anim.setDuration(200)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(float(direction))
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        def _done() -> None:
            self._anim = None
            self._commit_pending()
            self.update()

        self._anim.finished.connect(_done)
        self._anim.start()
        return True

    def move_h(self, delta: int) -> bool:
        return self.move_by(delta)

    def move_v(self, _delta: int) -> bool:
        # Let ↑↓ leave the shelf for Play / Delete / Wi‑Fi
        return False

    def digi_confirm(self) -> bool:
        if not self._entries:
            return False
        self.activated.emit()
        return True

    def _entry_at(self, offset: int) -> RomEntry:
        n = len(self._entries)
        return self._entries[(self._index + offset) % n]

    def _pixmap_for(self, entry: RomEntry, tw: int, th: int) -> QPixmap:
        key = (str(entry.path), tw, th)
        hit = self._cover_cache.get(key)
        if hit is not None:
            return hit
        pix = QPixmap()
        if entry.cover is not None and entry.cover.is_file():
            raw = QPixmap(str(entry.cover))
            if not raw.isNull():
                pix = raw.scaled(
                    tw, th, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )
                if pix.width() > tw or pix.height() > th:
                    x = max(0, (pix.width() - tw) // 2)
                    y = max(0, (pix.height() - th) // 2)
                    pix = pix.copy(x, y, tw, th)
        if pix.isNull():
            pix = self._placeholder(entry, tw, th)
        self._cover_cache[key] = pix
        return pix

    def _placeholder(self, entry: RomEntry, tw: int, th: int) -> QPixmap:
        pm = QPixmap(tw, th)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, 0, th)
        base = self._accent
        grad.setColorAt(0.0, base.darker(140))
        grad.setColorAt(1.0, QColor("#0a121c"))
        path = QPainterPath()
        path.addRoundedRect(QRectF(1, 1, tw - 2, th - 2), 6, 6)
        p.fillPath(path, grad)
        p.setPen(QPen(base.lighter(130), 1.5))
        p.drawPath(path)
        p.setPen(QColor("#e8eef5"))
        p.setFont(QFont("DejaVu Sans", max(14, tw // 6), QFont.Bold))
        p.drawText(QRect(0, 8, tw, th // 3), Qt.AlignHCenter | Qt.AlignVCenter, self._glyph)
        p.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
        title = entry.title
        if len(title) > 18:
            title = title[:16] + "…"
        p.setPen(QColor("#c8d4e0"))
        p.drawText(
            QRect(6, th // 2 - 4, tw - 12, th // 2),
            Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
            title,
        )
        p.end()
        return pm

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        n = len(self._entries)

        # Soft floor glow
        floor = QLinearGradient(0, h * 0.55, 0, h)
        floor.setColorAt(0.0, QColor(0, 0, 0, 0))
        floor.setColorAt(1.0, QColor(0, 20, 40, 90))
        p.fillRect(0, 0, w, h, floor)

        if n == 0:
            p.setPen(QColor("#9ab"))
            p.setFont(QFont("DejaVu Sans", 11))
            p.drawText(
                self.rect(),
                Qt.AlignCenter,
                "No ROMs yet\n→ Receive (Wi‑Fi)",
            )
            return

        # Arrows
        p.setPen(QPen(QColor("#58a6ff"), 2))
        p.setFont(QFont("DejaVu Sans", 16, QFont.Bold))
        cy_art = int(h * 0.42)
        p.drawText(0, cy_art - 12, 18, 24, Qt.AlignCenter, "‹")
        p.drawText(w - 18, cy_art - 12, 18, 24, Qt.AlignCenter, "›")

        cover_w, cover_h = 96, 84
        side_w, side_h = 56, 50
        slot_x = {0: 0.0, -1: -0.72, 1: 0.72, -2: -1.25, 2: 1.25}

        slots = [-2, -1, 1, 2, 0] if n >= 3 else ([-1, 1, 0] if n == 2 else [0])
        for logical_off in slots:
            if n < 3 and abs(logical_off) >= 2:
                continue
            if n < 5 and abs(logical_off) >= 2:
                continue
            visual_off = logical_off - self._shift
            entry = self._entry_at(logical_off)
            scale = _scale_for_offset(visual_off)
            is_center = abs(visual_off) < 0.2
            tw = int((cover_w if is_center else side_w) * max(scale, 0.35))
            th = int((cover_h if is_center else side_h) * max(scale, 0.35))
            # interpolate x from slot
            base_off = slot_x.get(logical_off, float(logical_off) * 0.72)
            # during anim, slide toward next slot
            x_norm = base_off - self._shift * 0.72
            cx = w * 0.5 + x_norm * (w * 0.42)
            cy = cy_art + (0 if is_center else 10)
            pix = self._pixmap_for(entry, max(tw, 40), max(th, 36))
            x = int(cx - tw / 2)
            y = int(cy - th / 2)
            # Drop shadow
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 100 if is_center else 60))
            p.drawRoundedRect(x + 2, y + 4, tw, th, 5, 5)
            p.drawPixmap(QRect(x, y, tw, th), pix)
            if is_center:
                p.setPen(QPen(QColor("#FFE600"), 2))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(x - 1, y - 1, tw + 2, th + 2, 6, 6)

        # Title + counter under shelf
        cur = self._entries[self._index]
        p.setPen(QColor("#e8eef5"))
        p.setFont(QFont("DejaVu Sans", 11, QFont.Bold))
        title = cur.title
        if len(title) > 28:
            title = title[:26] + "…"
        p.drawText(8, h - 36, w - 16, 18, Qt.AlignHCenter | Qt.AlignVCenter, title)
        p.setPen(QColor("#8aa0b5"))
        p.setFont(QFont("DejaVu Sans", 9))
        tag = " · cart" if cur.from_cart else ""
        p.drawText(
            8,
            h - 18,
            w - 16,
            16,
            Qt.AlignHCenter | Qt.AlignVCenter,
            f"{self._index + 1} / {n}{tag}",
        )


def build_entries(
    roms: List[Path],
    *,
    folder: str,
    data_root: Path,
    cart_titles: Optional[List[Tuple[str, Path]]] = None,
) -> List[RomEntry]:
    if cart_titles:
        out: List[RomEntry] = []
        for title, p in cart_titles:
            out.append(
                RomEntry(
                    path=p,
                    title=title or _pretty_title(p.name),
                    cover=find_cover(p, folder, data_root),
                    from_cart=True,
                )
            )
        return out
    return [
        RomEntry(
            path=p,
            title=_pretty_title(p.name),
            cover=find_cover(p, folder, data_root),
            from_cart=False,
        )
        for p in roms
    ]


def rom_deletable(path: Path, data_root: Path) -> bool:
    """Only user ROMs under ~/.esp-handset/roms — never cart /opt."""
    try:
        resolved = path.resolve()
        root = (data_root / "roms").resolve()
        return root == resolved.parent or root in resolved.parents
    except OSError:
        return False


def delete_rom_files(path: Path, data_root: Path, folder: str) -> Tuple[bool, str]:
    if not rom_deletable(path, data_root):
        return False, "Can't delete (cart or system ROM)"
    if not path.is_file():
        return False, "ROM missing"
    try:
        path.unlink()
    except OSError as e:
        return False, str(e)[:60]
    # Best-effort: remove matching covers
    stem = path.stem
    for cdir in (
        path.parent / "covers",
        data_root / "roms" / folder / "covers",
    ):
        if not cdir.is_dir():
            continue
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            for cand in (cdir / f"{stem}{ext}", cdir / f"{path.name}{ext}"):
                try:
                    if cand.is_file():
                        cand.unlink()
                except OSError:
                    pass
    return True, "Deleted"
