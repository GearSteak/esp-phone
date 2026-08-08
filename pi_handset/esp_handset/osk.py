"""Digivice on-screen keyboard with predictive candidates."""

from __future__ import annotations

from typing import Callable, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
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
        self._shift = False
        self._sym = False
        self._prefix = ""
        self._cand: List[str] = []
        self._cand_i = 0
        self._focus_row = 0
        self._focus_col = 0
        self._key_btns: List[List[QPushButton]] = []

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
                padding: 2px;
                font-size: 11px;
                font-weight: 600;
                min-height: 22px;
            }
            QPushButton:checked, QPushButton[oskFocus=\"1\"] {
                background: #1f6feb;
                border-color: #58a6ff;
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
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)

        self._pred_row = QHBoxLayout()
        self._pred_labs: List[QPushButton] = []
        for i in range(3):
            b = QPushButton("")
            b.setFixedHeight(20)
            b.clicked.connect(lambda _=False, idx=i: self._pick_cand(idx))
            self._pred_labs.append(b)
            self._pred_row.addWidget(b)
        lay.addLayout(self._pred_row)

        self._hint = QLabel("F2 close · arrows move · Enter type")
        self._hint.setObjectName("predLab")
        lay.addWidget(self._hint)

        self._grid = QVBoxLayout()
        self._grid.setSpacing(2)
        lay.addLayout(self._grid)
        self._rebuild_keys()

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
        # replace current prefix: emit backspaces then word+space
        for _ in self._prefix:
            self.commit.emit("\b")
        self.commit.emit(word + " ")
        self._prefix = ""
        self._cand = []
        self._refresh_cands()

    def _rows(self) -> List[List[str]]:
        if self._sym:
            return [list(r) for r in ROWS_SYM]
        return [list(r) for r in (ROWS_UPPER if self._shift else ROWS_LOWER)]

    def _rebuild_keys(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                lay = item.layout()
                while lay.count():
                    c = lay.takeAt(0)
                    if c.widget():
                        c.widget().deleteLater()
        self._key_btns = []
        rows = self._rows()
        # action row tokens
        special = ["⇧" if not self._sym else "ABC", "123" if not self._sym else "⇧", "␣", "⌫", "⏎"]
        for ri, row in enumerate(rows):
            h = QHBoxLayout()
            h.setSpacing(2)
            btns: List[QPushButton] = []
            for ch in row:
                b = QPushButton(ch)
                b.clicked.connect(lambda _=False, c=ch: self._tap(c))
                h.addWidget(b, 1)
                btns.append(b)
            self._grid.addLayout(h)
            self._key_btns.append(btns)
        h = QHBoxLayout()
        h.setSpacing(2)
        act_btns: List[QPushButton] = []
        for tok in special:
            b = QPushButton(tok)
            b.clicked.connect(lambda _=False, t=tok: self._tap_special(t))
            h.addWidget(b, 1)
            act_btns.append(b)
        self._grid.addLayout(h)
        self._key_btns.append(act_btns)
        self._focus_row = min(self._focus_row, len(self._key_btns) - 1)
        self._focus_col = min(self._focus_col, max(0, len(self._key_btns[self._focus_row]) - 1))
        self._paint_focus()

    def _tap(self, ch: str) -> None:
        self.commit.emit(ch)
        if self._shift and not self._sym:
            self._shift = False
            self._rebuild_keys()

    def _tap_special(self, tok: str) -> None:
        if tok in ("⇧",):
            self._shift = not self._shift
            self._rebuild_keys()
        elif tok == "123":
            self._sym = True
            self._rebuild_keys()
        elif tok == "ABC":
            self._sym = False
            self._rebuild_keys()
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
        for r, row in enumerate(self._key_btns):
            for c, b in enumerate(row):
                on = r == self._focus_row and c == self._focus_col
                b.setProperty("oskFocus", "1" if on else "0")
                b.style().unpolish(b)
                b.style().polish(b)

    def nav(self, key: str) -> bool:
        """Handle Digivice nav while OSK open. Returns True if consumed."""
        if key == "left":
            self._focus_col = max(0, self._focus_col - 1)
            self._paint_focus()
            return True
        if key == "right":
            row = self._key_btns[self._focus_row]
            self._focus_col = min(len(row) - 1, self._focus_col + 1)
            self._paint_focus()
            return True
        if key == "up":
            if self._focus_row == 0 and self._cand:
                self._cand_i = (self._cand_i - 1) % len(self._cand)
                self._refresh_cands()
                return True
            self._focus_row = max(0, self._focus_row - 1)
            self._focus_col = min(self._focus_col, len(self._key_btns[self._focus_row]) - 1)
            self._paint_focus()
            return True
        if key == "down":
            self._focus_row = min(len(self._key_btns) - 1, self._focus_row + 1)
            self._focus_col = min(self._focus_col, len(self._key_btns[self._focus_row]) - 1)
            self._paint_focus()
            return True
        if key == "ok":
            if self._focus_row == 0 and self._cand and False:
                pass
            # if on pred row via special: picking cand when up-focused
            btn = self._key_btns[self._focus_row][self._focus_col]
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
