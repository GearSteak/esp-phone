"""Digivice main home: icon row top + row bottom, center preview."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional

from PyQt5.QtCore import QTimer, Qt, QPoint, QRect, pyqtSignal
from PyQt5.QtGui import QFont, QPainter, QColor, QPen, QPixmap, QPolygon
from PyQt5.QtWidgets import QWidget

from esp_handset.asset_icons import bubble_for_state, icon_for_key
from esp_handset.shell_data import AppEntry
from esp_handset.ui_font import font_family

_PENGUN_ASSET_DIR = Path(__file__).resolve().parents[1] / "Assets"


class DigiviceHome(QWidget):
    """Two rows of icons (top / bottom) with a Digivice-style center stage.

    Joystick: ←→ along a row, ↑↓ switch rows, Confirm activates.
    """

    activated = pyqtSignal(str)

    def __init__(
        self,
        entries: List[AppEntry],
        parent: Optional[QWidget] = None,
        top_count: int = 5,
        on_activate: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(parent)
        self._entries = list(entries)
        self._top_n = max(1, min(top_count, len(self._entries)))
        self._row = 0  # 0 = top, 1 = bottom
        self._col = 0
        # Optional center-stage art per app key (e.g. media cart logo)
        self._stage_art: Dict[str, QPixmap] = {}
        self._pengun_frames = [
            QPixmap(str(_PENGUN_ASSET_DIR / f"pengun_walk_right_{i}.png"))
            for i in range(1, 5)
        ]
        self._pengun_frames = [
            frame for frame in self._pengun_frames if not frame.isNull()
        ]
        self._pengun_frame = 0
        self._pengun_timer = QTimer(self)
        self._pengun_timer.setInterval(140)
        self._pengun_timer.timeout.connect(self._advance_pengun)
        if self._pengun_frames:
            self._pengun_timer.start()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(200, 180)
        if on_activate:
            self.activated.connect(on_activate)

    def set_entries(self, entries: List[AppEntry]) -> None:
        """Replace home icons (e.g. Media → cart title) without resetting focus hard."""
        prev = self.current()
        prev_key = prev.key if prev else None
        self._entries = list(entries)
        self._top_n = max(1, min(self._top_n, len(self._entries))) if self._entries else 1
        if prev_key:
            for row_i, row in enumerate((self._top(), self._bot())):
                for col_i, e in enumerate(row):
                    if e.key == prev_key:
                        self._row = row_i
                        self._col = col_i
                        self.update()
                        return
        self._row = 0
        self._col = min(self._col, max(0, len(self._top()) - 1))
        self.update()

    def set_stage_art(self, key: str, pixmap: Optional[QPixmap]) -> None:
        """Logo/image shown in the center stage when that app is focused."""
        if pixmap is None or pixmap.isNull():
            self._stage_art.pop(key, None)
        else:
            self._stage_art[key] = QPixmap(pixmap)
        self.update()

    def _top(self) -> List[AppEntry]:
        return self._entries[: self._top_n]

    def _bot(self) -> List[AppEntry]:
        return self._entries[self._top_n :]

    def _row_entries(self) -> List[AppEntry]:
        return self._top() if self._row == 0 else self._bot()

    def current(self) -> Optional[AppEntry]:
        row = self._row_entries()
        if not row:
            return None
        self._col = max(0, min(self._col, len(row) - 1))
        return row[self._col]

    def move_h(self, delta: int) -> None:
        row = self._row_entries()
        if not row:
            return
        self._col = (self._col + delta) % len(row)
        self.update()

    def move_v(self, delta: int) -> None:
        top, bot = self._top(), self._bot()
        if not bot:
            return
        if delta > 0 and self._row == 0:
            self._row = 1
            self._col = min(self._col, len(bot) - 1)
        elif delta < 0 and self._row == 1:
            self._row = 0
            self._col = min(self._col, len(top) - 1)
        self.update()

    def activate(self) -> None:
        cur = self.current()
        if cur:
            self.activated.emit(cur.key)

    def _advance_pengun(self) -> None:
        if not self._pengun_frames:
            return
        self._pengun_frame = (self._pengun_frame + 1) % len(self._pengun_frames)
        self.update()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        w = self.window()
        if w is not None and hasattr(w, "keyPressEvent"):
            w.keyPressEvent(event)
            if event.isAccepted():
                return
        super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        cur = self.current()

        if self._pengun_frames:
            pengun = self._pengun_frames[self._pengun_frame]
            p.drawPixmap(
                w - pengun.width() - 8,
                (h - pengun.height()) // 2,
                pengun,
            )

        def draw_row(entries: List[AppEntry], y: int, row_i: int) -> None:
            if not entries:
                return
            n = len(entries)
            slot = w / n
            for i, e in enumerate(entries):
                cx = int(slot * (i + 0.5))
                focused = row_i == self._row and i == self._col
                bubble_size = 32
                bubble = bubble_for_state(focused)
                if bubble is not None:
                    p.drawPixmap(cx - bubble_size // 2, y - bubble_size // 2, bubble)
                else:
                    r = bubble_size // 2
                    p.setBrush(QColor("#FFE600" if focused else "#1e2d41"))
                    p.setPen(QPen(QColor("#000000" if focused else "#ffffff"), 2))
                    p.drawEllipse(cx - r, y - r, bubble_size, bubble_size)
                if focused:
                    # Filled triangle tip under bubble (shape cue)
                    r = bubble_size // 2
                    tri = QPolygon(
                        [
                            QPoint(cx, y + r + 8),
                            QPoint(cx - 7, y + r + 1),
                            QPoint(cx + 7, y + r + 1),
                        ]
                    )
                    p.setBrush(QColor("#FFE600"))
                    p.setPen(QPen(QColor("#000000"), 2))
                    p.drawPolygon(tri)
                art = icon_for_key(e.key, inverted=focused)
                if art is not None and not art.isNull():
                    icon = art
                    p.drawPixmap(
                        cx - icon.width() // 2,
                        y - icon.height() // 2,
                        icon,
                    )
                else:
                    p.setPen(QColor("#000000" if focused else "#9ab"))
                    p.setFont(QFont(font_family(), 12 if focused else 10, QFont.Bold))
                    p.drawText(cx - 14, y - 10, 28, 20, Qt.AlignCenter, e.glyph[:1])

        # Top row
        draw_row(self._top(), 22, 0)

        # Center Digivice stage
        stage_m = 28
        stage = self.rect().adjusted(stage_m, 44, -stage_m, -44)

        if cur:
            art = self._stage_art.get(cur.key)
            title_h = 18
            if art is not None and not art.isNull():
                # Logo above the name (cart Media takeover)
                max_w = max(40, stage.width() - 20)
                max_h = max(40, stage.height() - title_h - 16)
                scaled = art.scaled(
                    max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                x = stage.center().x() - scaled.width() // 2
                y = stage.top() + 6
                p.drawPixmap(x, y, scaled)
            title_rect = QRect(
                stage.left() + 8,
                stage.top() + 2,
                stage.width() - 16,
                title_h + 4,
            )
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 155))
            p.drawRoundedRect(title_rect, 6, 6)
            p.setPen(QColor("#e8eef5"))
            p.setFont(QFont(font_family(), 11, QFont.Bold))
            p.drawText(
                title_rect,
                Qt.AlignHCenter | Qt.AlignVCenter,
                cur.title,
            )

        # Bottom row
        draw_row(self._bot(), h - 22, 1)
