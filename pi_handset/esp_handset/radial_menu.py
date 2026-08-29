"""Digivice submenu carousel — big center icon, smaller neighbors, wrap-around."""

from __future__ import annotations

from typing import Callable, List, Optional

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, Qt, pyqtProperty, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import QWidget

from esp_handset.asset_icons import bubble_for_state, icon_for_key
from esp_handset.shell_data import AppEntry


def _scale_for_offset(off: float) -> float:
    """Center (0) = 1.0; neighbors shrink with distance."""
    d = abs(off)
    if d < 0.01:
        return 1.0
    if d < 1.01:
        return 0.55 + 0.45 * (1.0 - d)  # during anim
    if d < 2.01:
        return 0.35
    return 0.25


class RadialMenu(QWidget):
    """Carousel: one large icon, side icons smaller; ←→ wraps first↔last.

    Icons grow into the highlight and shrink as they leave center.
    """

    activated = pyqtSignal(str)

    def __init__(
        self,
        entries: List[AppEntry],
        parent: Optional[QWidget] = None,
        on_activate: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(parent)
        self._entries = list(entries)
        self._index = 0
        self._shift = 0.0  # animated: 0 = settled; ±1 during slide toward next
        self._anim: Optional[QPropertyAnimation] = None
        self.setMinimumSize(200, 160)
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

    def set_entries(self, entries: List[AppEntry], index: int = 0) -> None:
        self._entries = list(entries)
        self._index = max(0, min(index, len(self._entries) - 1)) if self._entries else 0
        self._shift = 0.0
        self.update()

    def current(self) -> Optional[AppEntry]:
        if not self._entries:
            return None
        return self._entries[self._index]

    def move_by(self, delta: int) -> bool:
        if not self._entries or delta == 0:
            return False
        n = len(self._entries)
        # Mid-scroll press: commit the in-flight step so we never snap back.
        if self._anim is not None:
            try:
                self._anim.finished.disconnect()
            except Exception:
                pass
            self._anim.stop()
            self._anim = None
            pending = getattr(self, "_pending_index", self._index)
            self._index = int(pending) % n
            self._shift = 0.0

        direction = 1 if delta > 0 else -1
        self._pending_index = (self._index + direction) % n

        self._anim = QPropertyAnimation(self, b"shift", self)
        self._anim.setDuration(180)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(float(direction))
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        def _done():
            self._anim = None
            self._index = self._pending_index
            self._shift = 0.0
            self.update()

        self._anim.finished.connect(_done)
        self._anim.start()
        return True

    def move_h(self, delta: int) -> bool:
        """1D carousel: left/right (and digi pad)."""
        return self.move_by(delta)

    def move_v(self, delta: int) -> bool:
        """Same axis as horizontal — nested radials share one ring."""
        return self.move_by(delta)

    def activate(self) -> None:
        self.digi_confirm()

    def digi_confirm(self) -> bool:
        cur = self.current()
        if not cur:
            return False
        self.activated.emit(cur.key)
        return True

    def keyPressEvent(self, event) -> None:  # noqa: N802
        w = self.window()
        if w is not None and hasattr(w, "keyPressEvent"):
            w.keyPressEvent(event)
            if event.isAccepted():
                return
        super().keyPressEvent(event)

    def _entry_at(self, offset: int) -> AppEntry:
        n = len(self._entries)
        return self._entries[(self._index + offset) % n]

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0 - 6
        n = len(self._entries)

        if n == 0:
            p.setPen(QColor("#9ab"))
            p.drawText(self.rect(), Qt.AlignCenter, "Empty")
            return

        # Side arrows (always — wrap-around)
        p.setPen(QPen(QColor("#58a6ff"), 2))
        p.setFont(QFont("DejaVu Sans", 18, QFont.Bold))
        p.drawText(2, int(cy - 14), 22, 28, Qt.AlignCenter, "‹")
        p.drawText(w - 24, int(cy - 14), 22, 28, Qt.AlignCenter, "›")

        # Visual slots: logical offsets relative to current, shifted by anim
        # Draw from far to near so center paints last
        slot_offsets = [-2, -1, 1, 2, 0] if n >= 3 else ([-1, 1, 0] if n == 2 else [0])

        for logical_off in slot_offsets:
            if n < 3 and abs(logical_off) >= 2:
                continue
            # During shift toward +1, center moves right visually → subtract shift
            visual_off = logical_off - self._shift
            entry = self._entry_at(logical_off)
            scale = _scale_for_offset(visual_off)
            # bump center a bit more when settled
            if abs(visual_off) < 0.15:
                scale = max(scale, 0.92 + 0.08 * (1.0 - abs(visual_off) / 0.15))

            r = max(8, int(30 * scale))
            x = cx + visual_off * 48
            y = cy
            alpha = int(90 + 165 * min(1.0, scale))

            focused = abs(visual_off) < 0.35
            bubble = bubble_for_state(focused)
            if bubble is not None:
                bubble_size = r * 2
                scaled_bubble = bubble.scaled(
                    bubble_size,
                    bubble_size,
                    Qt.IgnoreAspectRatio,
                    Qt.FastTransformation,
                )
                p.save()
                p.setOpacity(max(0.4, alpha / 255.0))
                p.drawPixmap(int(x - r), int(y - r), scaled_bubble)
                p.restore()
            else:
                if focused:
                    # High-contrast center (yellow/black) — not blue-on-blue
                    p.setBrush(QColor(255, 230, 0, min(255, alpha + 40)))
                    p.setPen(QPen(QColor("#000000"), 3))
                else:
                    p.setBrush(QColor(40, 55, 75, alpha))
                    p.setPen(QPen(QColor(255, 255, 255, 45), 1))
                p.drawEllipse(int(x - r), int(y - r), r * 2, r * 2)

            icon = icon_for_key(entry.key)
            if icon is not None and not icon.isNull():
                icon_size = max(8, int(42 * scale))
                scaled_icon = icon.scaled(
                    icon_size,
                    icon_size,
                    Qt.KeepAspectRatio,
                    Qt.FastTransformation,
                )
                p.drawPixmap(
                    int(x - scaled_icon.width() // 2),
                    int(y - scaled_icon.height() // 2),
                    scaled_icon,
                )
            else:
                glyph_size = max(8, int(24 * scale))
                p.setPen(
                    QColor(0, 0, 0, 255)
                    if focused
                    else QColor(232, 238, 245, alpha)
                )
                p.setFont(QFont("DejaVu Sans", glyph_size, QFont.Bold))
                p.drawText(
                    int(x - r),
                    int(y - r),
                    r * 2,
                    r * 2,
                    Qt.AlignCenter,
                    entry.glyph[:1],
                )
            if focused:
                # Black ring already drawn; add outer ticks for non-color cue
                p.setPen(QPen(QColor("#000000"), 2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(int(x - r - 4), int(y - r - 4), (r + 4) * 2, (r + 4) * 2)

        # Label for settled (or nearly settled) center
        show_idx = self._index
        if abs(self._shift) > 0.5:
            show_idx = (self._index + (1 if self._shift > 0 else -1)) % n
        cur = self._entries[show_idx]
        p.setPen(QColor("#e8eef5"))
        p.setFont(QFont("DejaVu Sans", 12, QFont.Bold))
        p.drawText(8, h - 34, w - 16, 18, Qt.AlignHCenter | Qt.AlignTop, cur.title)
        p.setPen(QColor("#8aa"))
        p.setFont(QFont("DejaVu Sans", 8))
        p.drawText(8, h - 16, w - 16, 14, Qt.AlignHCenter | Qt.AlignTop, f"{show_idx + 1}/{n}")
