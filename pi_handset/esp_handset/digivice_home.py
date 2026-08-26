"""Digivice main home: icon row top + row bottom, center preview."""

from __future__ import annotations

from typing import Callable, List, Optional

from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtGui import QFont, QPainter, QColor, QPen, QPolygon
from PyQt5.QtWidgets import QWidget

from esp_handset.shell_data import AppEntry


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
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(200, 180)
        if on_activate:
            self.activated.connect(on_activate)

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
        w, h = self.width(), self.height()
        cur = self.current()

        def draw_row(entries: List[AppEntry], y: int, row_i: int) -> None:
            if not entries:
                return
            n = len(entries)
            slot = w / n
            for i, e in enumerate(entries):
                cx = int(slot * (i + 0.5))
                focused = row_i == self._row and i == self._col
                r = 18 if focused else 12
                if focused:
                    # Yellow + black frame: high luminance contrast (not blue-on-blue)
                    p.setBrush(QColor("#FFE600"))
                    p.setPen(QPen(QColor("#000000"), 3))
                    p.drawEllipse(cx - r - 2, y - r - 2, (r + 2) * 2, (r + 2) * 2)
                    p.setBrush(QColor("#FFE600"))
                    p.setPen(QPen(QColor("#000000"), 2))
                else:
                    p.setBrush(QColor(30, 45, 65, 220))
                    p.setPen(QPen(QColor(255, 255, 255, 50), 1))
                p.drawEllipse(cx - r, y - r, r * 2, r * 2)
                if focused:
                    # Filled triangle tip under bubble (shape cue)
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
                p.setPen(QColor("#000000" if focused else "#9ab"))
                p.setFont(QFont("DejaVu Sans", 12 if focused else 9, QFont.Bold))
                p.drawText(cx - 14, y - 10, 28, 20, Qt.AlignCenter, e.glyph[:1])

        # Top row
        draw_row(self._top(), 22, 0)

        # Center Digivice stage
        stage_m = 28
        stage = self.rect().adjusted(stage_m, 44, -stage_m, -44)
        p.setBrush(QColor(10, 18, 28, 230))
        p.setPen(QPen(QColor(88, 166, 255, 90), 2))
        p.drawRoundedRect(stage, 16, 16)
        # inner oval hint
        p.setPen(QPen(QColor(255, 255, 255, 25), 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(stage.adjusted(10, 8, -10, -8))

        if cur:
            p.setPen(QColor("#e8eef5"))
            p.setFont(QFont("DejaVu Sans", 28, QFont.Bold))
            p.drawText(stage.adjusted(0, 4, 0, -28), Qt.AlignHCenter | Qt.AlignVCenter, cur.glyph)
            p.setFont(QFont("DejaVu Sans", 11, QFont.Bold))
            p.drawText(
                stage.left(),
                stage.bottom() - 22,
                stage.width(),
                16,
                Qt.AlignHCenter | Qt.AlignTop,
                cur.title,
            )
            if cur.subtitle:
                pass  # Titles only — no hint text under icons

        # Bottom row
        draw_row(self._bot(), h - 22, 1)
