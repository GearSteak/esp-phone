"""Contacts carousel: ↑↓ letters, ←→ contacts in letter; photo or initials."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, Qt, pyqtProperty, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import QWidget

from esp_handset.radial_menu import _scale_for_offset


def contact_letter(c: dict) -> str:
    name = str(c.get("name") or "").strip()
    ch = name[:1].upper() if name else "#"
    return ch if ch.isalpha() else "#"


def bucket_contacts(contacts: List[dict]) -> Tuple[List[str], Dict[str, List[Tuple[int, dict]]]]:
    """A–Z then #. Values are (global_index, contact) in sorted name order."""
    groups: Dict[str, List[Tuple[int, dict]]] = {}
    for i, c in enumerate(contacts):
        letter = contact_letter(c)
        groups.setdefault(letter, []).append((i, c))
    letters = sorted((L for L in groups if L != "#"), key=str)
    if "#" in groups:
        letters.append("#")
    return letters, groups


class ContactsRadial(QWidget):
    """Horizontal contact carousel; vertical axis switches alphabet buckets."""

    activated = pyqtSignal(int)  # global contact index in contacts.json order

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        on_activate: Optional[Callable[[int], None]] = None,
        channels_line: Optional[Callable[[dict], str]] = None,
        photo_path: Optional[Callable[[dict], Optional[str]]] = None,
        avatar_color: Optional[Callable[[str], str]] = None,
    ):
        super().__init__(parent)
        self._channels_line = channels_line or (lambda _c: "")
        self._photo_path = photo_path or (lambda _c: None)
        self._avatar_color = avatar_color or (lambda _k: "#2a6f97")
        self._letters: List[str] = []
        self._groups: Dict[str, List[Tuple[int, dict]]] = {}
        self._letter_i = 0
        self._contact_i = 0
        self._shift = 0.0
        self._anim: Optional[QPropertyAnimation] = None
        self._pix_cache: Dict[str, QPixmap] = {}
        self.setMinimumSize(200, 140)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setProperty("digiPad", True)
        if on_activate:
            self.activated.connect(on_activate)

    def _get_shift(self) -> float:
        return self._shift

    def _set_shift(self, v: float) -> None:
        self._shift = v
        self.update()

    shift = pyqtProperty(float, _get_shift, _set_shift)

    def set_contacts(self, contacts: List[dict]) -> None:
        prev_letter = self.current_letter()
        prev_idx = self.current_index()
        self._letters, self._groups = bucket_contacts(contacts)
        self._pix_cache.clear()
        if not self._letters:
            self._letter_i = 0
            self._contact_i = 0
            self._shift = 0.0
            self.update()
            return
        # Restore letter / contact when possible
        if prev_letter in self._groups:
            self._letter_i = self._letters.index(prev_letter)
            group = self._groups[prev_letter]
            self._contact_i = 0
            if prev_idx is not None:
                for j, (gi, _) in enumerate(group):
                    if gi == prev_idx:
                        self._contact_i = j
                        break
        else:
            self._letter_i = 0
            self._contact_i = 0
        self._clamp()
        self._shift = 0.0
        self.update()

    def _clamp(self) -> None:
        if not self._letters:
            self._letter_i = 0
            self._contact_i = 0
            return
        self._letter_i = max(0, min(self._letter_i, len(self._letters) - 1))
        group = self._groups.get(self.current_letter(), [])
        if not group:
            self._contact_i = 0
            return
        self._contact_i = max(0, min(self._contact_i, len(group) - 1))

    def current_letter(self) -> str:
        if not self._letters:
            return ""
        return self._letters[self._letter_i]

    def _group(self) -> List[Tuple[int, dict]]:
        letter = self.current_letter()
        return self._groups.get(letter, []) if letter else []

    def current_index(self) -> Optional[int]:
        group = self._group()
        if not group:
            return None
        self._clamp()
        return group[self._contact_i][0]

    def current_contact(self) -> Optional[dict]:
        group = self._group()
        if not group:
            return None
        self._clamp()
        return group[self._contact_i][1]

    def move_h(self, delta: int) -> bool:
        group = self._group()
        if not group or delta == 0:
            return False
        n = len(group)
        if self._anim is not None:
            self._anim.stop()
            self._shift = 0.0
        direction = 1 if delta > 0 else -1
        self._pending_contact = (self._contact_i + direction) % n
        self._anim = QPropertyAnimation(self, b"shift", self)
        self._anim.setDuration(140)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(float(direction))
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        def _done() -> None:
            self._contact_i = self._pending_contact
            self._shift = 0.0
            self.update()

        self._anim.finished.connect(_done)
        self._anim.start()
        return True

    def move_v(self, delta: int, *, wrap: bool = False) -> bool:
        if not self._letters or delta == 0:
            return False
        if self._anim is not None:
            self._anim.stop()
            self._shift = 0.0
        n = len(self._letters)
        nxt = self._letter_i + (1 if delta > 0 else -1)
        if wrap:
            self._letter_i = nxt % n
        else:
            if nxt < 0 or nxt >= n:
                return False
            self._letter_i = nxt
        self._contact_i = 0
        self._shift = 0.0
        self.update()
        return True

    def digi_confirm(self) -> bool:
        idx = self.current_index()
        if idx is None:
            return False
        self.activated.emit(idx)
        return True

    def activate(self) -> None:
        self.digi_confirm()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        w = self.window()
        if w is not None and hasattr(w, "keyPressEvent"):
            w.keyPressEvent(event)
            if event.isAccepted():
                return
        super().keyPressEvent(event)

    def _entry_at(self, offset: int) -> Tuple[int, dict]:
        group = self._group()
        n = len(group)
        return group[(self._contact_i + offset) % n]

    def _circle_pixmap(self, path: str, size: int) -> Optional[QPixmap]:
        key = f"{path}:{size}"
        cached = self._pix_cache.get(key)
        if cached is not None:
            return cached
        src = QPixmap(path)
        if src.isNull():
            return None
        scaled = src.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x = max(0, (scaled.width() - size) // 2)
        y = max(0, (scaled.height() - size) // 2)
        cropped = scaled.copy(x, y, size, size)
        out = QPixmap(size, size)
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing)
        path_clip = QPainterPath()
        path_clip.addEllipse(0, 0, size, size)
        p.setClipPath(path_clip)
        p.drawPixmap(0, 0, cropped)
        p.end()
        self._pix_cache[key] = out
        return out

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0 - 10
        group = self._group()
        n = len(group)
        letter = self.current_letter()

        # Letter index strip
        p.setPen(QColor("#8aa"))
        p.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
        if self._letters:
            i0 = max(0, self._letter_i - 5)
            chunk = self._letters[i0 : i0 + 12]
            shown = " ".join(f"[{L}]" if L == letter else L for L in chunk)
            p.drawText(4, 2, w - 8, 14, Qt.AlignHCenter | Qt.AlignTop, shown)
        p.setPen(QPen(QColor("#58a6ff"), 2))
        p.setFont(QFont("DejaVu Sans", 11, QFont.Bold))
        p.drawText(2, 14, 20, 18, Qt.AlignCenter, "▴")
        p.drawText(2, int(cy + 28), 20, 18, Qt.AlignCenter, "▾")

        if n == 0:
            p.setPen(QColor("#9ab"))
            p.setFont(QFont("DejaVu Sans", 11))
            p.drawText(self.rect().adjusted(0, 16, 0, -24), Qt.AlignCenter, "No contacts")
            return

        p.setPen(QPen(QColor("#58a6ff"), 2))
        p.setFont(QFont("DejaVu Sans", 18, QFont.Bold))
        p.drawText(2, int(cy - 14), 22, 28, Qt.AlignCenter, "‹")
        p.drawText(w - 24, int(cy - 14), 22, 28, Qt.AlignCenter, "›")

        slot_offsets = [-2, -1, 1, 2, 0] if n >= 3 else ([-1, 1, 0] if n == 2 else [0])
        for logical_off in slot_offsets:
            if n < 3 and abs(logical_off) >= 2:
                continue
            visual_off = logical_off - self._shift
            _gi, contact = self._entry_at(logical_off)
            scale = _scale_for_offset(visual_off)
            if abs(visual_off) < 0.15:
                scale = max(scale, 0.92 + 0.08 * (1.0 - abs(visual_off) / 0.15))
            r = max(8, int(30 * scale))
            x = cx + visual_off * 48
            y = cy
            alpha = int(90 + 165 * min(1.0, scale))
            focused = abs(visual_off) < 0.35
            name = str(contact.get("name") or "Unknown")
            initial = name[:1].upper() if name else "?"
            if not initial.isalnum():
                initial = "#"
            photo = self._photo_path(contact)

            if focused:
                p.setBrush(QColor(255, 230, 0, min(255, alpha + 40)))
                p.setPen(QPen(QColor("#000000"), 3))
            else:
                p.setBrush(QColor(40, 55, 75, alpha))
                p.setPen(QPen(QColor(255, 255, 255, 45), 1))
            p.drawEllipse(int(x - r), int(y - r), r * 2, r * 2)

            drew_photo = False
            if photo:
                pix = self._circle_pixmap(photo, r * 2)
                if pix is not None:
                    p.drawPixmap(int(x - r), int(y - r), pix)
                    if focused:
                        p.setPen(QPen(QColor("#000000"), 3))
                        p.setBrush(Qt.NoBrush)
                        p.drawEllipse(int(x - r), int(y - r), r * 2, r * 2)
                    drew_photo = True
            if not drew_photo:
                if focused:
                    fill = QColor("#FFE600")
                else:
                    fill = QColor(self._avatar_color(name))
                    fill.setAlpha(alpha)
                p.setBrush(fill)
                p.setPen(QPen(QColor("#000000"), 3) if focused else QPen(QColor(255, 255, 255, 45), 1))
                p.drawEllipse(int(x - r), int(y - r), r * 2, r * 2)
                glyph_size = max(8, int(24 * scale))
                p.setPen(QColor(0, 0, 0, 255) if focused else QColor(232, 238, 245, alpha))
                p.setFont(QFont("DejaVu Sans", glyph_size, QFont.Bold))
                p.drawText(int(x - r), int(y - r), r * 2, r * 2, Qt.AlignCenter, initial)

            if focused:
                p.setPen(QPen(QColor("#000000"), 2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(int(x - r - 4), int(y - r - 4), (r + 4) * 2, (r + 4) * 2)

        show_i = self._contact_i
        if abs(self._shift) > 0.5:
            show_i = (self._contact_i + (1 if self._shift > 0 else -1)) % n
        _gi, cur = group[show_i]
        title = str(cur.get("name") or "Unknown")
        sub = self._channels_line(cur)
        p.setPen(QColor("#e8eef5"))
        p.setFont(QFont("DejaVu Sans", 12, QFont.Bold))
        p.drawText(8, h - 34, w - 16, 18, Qt.AlignHCenter | Qt.AlignTop, title)
        p.setPen(QColor("#8aa"))
        p.setFont(QFont("DejaVu Sans", 8))
        letter_bit = f"{letter} · {show_i + 1}/{n}"
        line = f"{letter_bit}  {sub}" if sub else letter_bit
        p.drawText(8, h - 16, w - 16, 14, Qt.AlignHCenter | Qt.AlignTop, line)
