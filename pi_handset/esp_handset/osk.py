"""Digivice on-screen keyboard with predictive candidates."""

from __future__ import annotations

from typing import List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from esp_handset import predict as pred


ROWS_LOWER = [
    list("qwertyuiop"),
    list("asdfghjkl"),
    list("zxcvbnm"),
]
ROWS_UPPER = [
    list("QWERTYUIOP"),
    list("ASDFGHJKL"),
    list("ZXCVBNM"),
]
ROWS_SYM = [
    list("1234567890"),
    list("@#$%&*-+="),
    list("()_!?,.;/"),
]


class OnScreenKeyboard(QWidget):
    """Compact OSK. Emits `commit` for each character / action string.

    Actions: \"\\b\" backspace, \"\\n\" enter, \" \" space, or a prediction word+space.
    """

    commit = pyqtSignal(str)
    closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("oskRoot")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._shift = False
        self._sym = False
        self._prefix = ""
        self._cand: List[str] = []
        self._cand_i = 0
        self._focus_row = 0
        self._focus_col = 0
        self._key_btns: List[List[QPushButton]] = []
        self._special_btns: List[QPushButton] = []

        self.setStyleSheet(
            """
            #oskRoot {
                background: rgba(8, 14, 22, 0.96);
                border-top: 1px solid rgba(255,255,255,0.12);
            }
            QPushButton {
                background: #1a2838;
                color: #e8eef5;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 4px;
                padding: 1px;
                font-size: 11px;
                font-weight: 600;
                min-height: 24px;
                max-height: 28px;
            }
            QPushButton:checked, QPushButton[oskFocus="1"] {
                background: #FFE600;
                color: #000000;
                border: 3px solid #000000;
                font-weight: 800;
            }
            QLabel#predLab {
                color: #9ab;
                font-size: 10px;
                background: transparent;
                border: none;
            }
            """
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(3)

        self._pred_row = QHBoxLayout()
        self._pred_row.setSpacing(2)
        self._pred_labs: List[QPushButton] = []
        for i in range(3):
            b = QPushButton("")
            b.setFixedHeight(22)
            b.clicked.connect(lambda _=False, idx=i: self._pick_cand(idx))
            self._pred_labs.append(b)
            self._pred_row.addWidget(b)
        lay.addLayout(self._pred_row)

        # Letter / symbol rows — built once; labels update on shift/123
        self._grid = QVBoxLayout()
        self._grid.setSpacing(2)
        lay.addLayout(self._grid)

        self._build_grid_once()
        self._apply_mode_labels()
        self._paint_focus()

    def _letter_rows(self) -> List[List[str]]:
        if self._sym:
            return [list(r) for r in ROWS_SYM]
        return [list(r) for r in (ROWS_UPPER if self._shift else ROWS_LOWER)]

    def _special_tokens(self) -> List[str]:
        if self._sym:
            return ["ABC", "⇧", "␣", "⌫", "⏎"]
        return ["⇧", "123", "␣", "⌫", "⏎"]

    def _build_grid_once(self) -> None:
        """Create key buttons once. Never stack duplicate rows on shift/123."""
        # Clear any leftover (safety)
        self._clear_layout(self._grid)
        self._key_btns = []
        self._special_btns = []

        # Max width among letter layouts so columns stay stable
        template = ROWS_LOWER
        for row in template:
            h = QHBoxLayout()
            h.setSpacing(2)
            btns: List[QPushButton] = []
            for _ch in row:
                b = QPushButton("")
                b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                b.setFixedHeight(26)
                b.clicked.connect(self._on_letter_click)
                h.addWidget(b, 1)
                btns.append(b)
            self._grid.addLayout(h)
            self._key_btns.append(btns)

        h = QHBoxLayout()
        h.setSpacing(2)
        for _ in range(5):
            b = QPushButton("")
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setFixedHeight(26)
            b.clicked.connect(self._on_special_click)
            h.addWidget(b, 1)
            self._special_btns.append(b)
        self._grid.addLayout(h)
        self._key_btns.append(self._special_btns)

    @staticmethod
    def _clear_layout(layout) -> None:
        """Remove and destroy all items immediately (no ghost overlapping rows)."""
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                break
            child_lay = item.layout()
            if child_lay is not None:
                OnScreenKeyboard._clear_layout(child_lay)
                # Nested layout object: schedule delete via parentless QObject
                child_lay.setParent(None)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
            # Caller owns the QLayoutItem after takeAt — must delete
            del item

    def _apply_mode_labels(self) -> None:
        rows = self._letter_rows()
        for ri, row in enumerate(rows):
            if ri >= len(self._key_btns) - 1:
                break
            btns = self._key_btns[ri]
            # Hide extras if this mode's row is shorter (e.g. zxcvbnm vs qwerty)
            for ci, b in enumerate(btns):
                if ci < len(row):
                    b.setText(row[ci])
                    b.setProperty("oskChar", row[ci])
                    b.setVisible(True)
                    b.setEnabled(True)
                else:
                    b.setText("")
                    b.setProperty("oskChar", "")
                    b.setVisible(False)
                    b.setEnabled(False)
        for b, tok in zip(self._special_btns, self._special_tokens()):
            b.setText(tok)
            b.setProperty("oskTok", tok)
            b.setVisible(True)

    def _on_letter_click(self) -> None:
        b = self.sender()
        if not isinstance(b, QPushButton):
            return
        ch = b.property("oskChar")
        if not ch:
            return
        self._tap(str(ch))

    def _on_special_click(self) -> None:
        b = self.sender()
        if not isinstance(b, QPushButton):
            return
        tok = b.property("oskTok")
        if tok:
            self._tap_special(str(tok))

    def set_prefix_from_text(self, text: str, cursor: int = -1) -> None:
        self._prefix = pred.current_word(text, cursor)
        self._cand = pred.predict(self._prefix, 3)
        self._cand_i = 0
        self._refresh_cands()

    def _refresh_cands(self) -> None:
        for i, b in enumerate(self._pred_labs):
            if i < len(self._cand):
                mark = "› " if i == self._cand_i else ""
                b.setText(mark + self._cand[i])
                b.setEnabled(True)
            else:
                b.setText("")
                b.setEnabled(False)

    def _pick_cand(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._cand):
            return
        word = self._cand[idx]
        for _ in self._prefix:
            self.commit.emit("\b")
        self.commit.emit(word + " ")
        self._prefix = ""
        self._cand = []
        self._refresh_cands()

    def _tap(self, ch: str) -> None:
        self.commit.emit(ch)
        if self._shift and not self._sym:
            self._shift = False
            self._apply_mode_labels()
            self._paint_focus()

    def _tap_special(self, tok: str) -> None:
        if tok == "⇧":
            self._shift = not self._shift
            self._apply_mode_labels()
            self._paint_focus()
        elif tok == "123":
            self._sym = True
            self._shift = False
            self._apply_mode_labels()
            self._paint_focus()
        elif tok == "ABC":
            self._sym = False
            self._apply_mode_labels()
            self._paint_focus()
        elif tok == "␣":
            self.commit.emit(" ")
            self._prefix = ""
            self._cand = []
            self._refresh_cands()
        elif tok == "⌫":
            self.commit.emit("\b")
        elif tok == "⏎":
            self.commit.emit("\n")

    def _paint_focus(self) -> None:
        if not self._key_btns:
            return
        self._focus_row = max(0, min(self._focus_row, len(self._key_btns) - 1))
        row = self._key_btns[self._focus_row]
        visible = [b for b in row if b.isVisible()]
        if not visible:
            return
        self._focus_col = max(0, min(self._focus_col, len(row) - 1))
        # Snap to a visible key if current is hidden
        if not row[self._focus_col].isVisible():
            for i, b in enumerate(row):
                if b.isVisible():
                    self._focus_col = i
                    break
        for r, rbtns in enumerate(self._key_btns):
            for c, b in enumerate(rbtns):
                on = r == self._focus_row and c == self._focus_col and b.isVisible()
                b.setProperty("oskFocus", "1" if on else "0")
                b.style().unpolish(b)
                b.style().polish(b)
                b.update()

    def nav(self, key: str) -> bool:
        """Handle Digivice nav while OSK open. Returns True if consumed."""
        if not self._key_btns:
            return False
        if key == "left":
            row = self._key_btns[self._focus_row]
            c = self._focus_col - 1
            while c >= 0 and not row[c].isVisible():
                c -= 1
            if c >= 0:
                self._focus_col = c
                self._paint_focus()
            return True
        if key == "right":
            row = self._key_btns[self._focus_row]
            c = self._focus_col + 1
            while c < len(row) and not row[c].isVisible():
                c += 1
            if c < len(row):
                self._focus_col = c
                self._paint_focus()
            return True
        if key == "up":
            if self._focus_row == 0 and self._cand:
                self._cand_i = (self._cand_i - 1) % len(self._cand)
                self._refresh_cands()
                return True
            self._focus_row = max(0, self._focus_row - 1)
            self._focus_col = min(
                self._focus_col, len(self._key_btns[self._focus_row]) - 1
            )
            self._paint_focus()
            return True
        if key == "down":
            self._focus_row = min(len(self._key_btns) - 1, self._focus_row + 1)
            self._focus_col = min(
                self._focus_col, len(self._key_btns[self._focus_row]) - 1
            )
            self._paint_focus()
            return True
        if key == "ok":
            btn = self._key_btns[self._focus_row][self._focus_col]
            if btn.isVisible() and btn.isEnabled():
                btn.click()
            return True
        if key == "pred":
            if self._cand:
                self._pick_cand(self._cand_i)
                return True
        if key == "close":
            self.hide()
            self.closed.emit()
            return True
        return False
