"""Simple built-in games (ESP Phone games menu parity).

Boards scale paint to the widget rect so they fit Digivice 240×320 chrome.
"""

from __future__ import annotations

import random
from typing import Callable, List, Tuple

from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QColor, QPainter, QFont, QKeyEvent
from PyQt5.QtWidgets import (
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QSizePolicy,
)

from esp_handset.pages import page_chrome


class SnakeBoard(QWidget):
    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(160)
        self.cols = 14
        self.rows = 12
        self.reset()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(220, 200)

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self.reset()
        self.timer.start(120)
        self.setFocus(Qt.OtherFocusReason)

    def hideEvent(self, e):  # noqa: N802
        self.timer.stop()
        super().hideEvent(e)

    def reset(self):
        self.snake: List[Tuple[int, int]] = [(4, 6), (3, 6), (2, 6)]
        self.dir = (1, 0)
        self.pending = (1, 0)
        self.food = (8, 6)
        self.alive = True
        self.score = 0
        self._place_food()

    def _place_food(self):
        while True:
            f = (random.randrange(self.cols), random.randrange(self.rows))
            if f not in self.snake:
                self.food = f
                return

    def keyPressEvent(self, e: QKeyEvent):  # noqa: N802
        k = e.key()
        dx, dy = self.dir
        if k in (Qt.Key_Left, Qt.Key_A) and dx == 0:
            self.pending = (-1, 0)
        elif k in (Qt.Key_Right, Qt.Key_D) and dx == 0:
            self.pending = (1, 0)
        elif k in (Qt.Key_Up, Qt.Key_W) and dy == 0:
            self.pending = (0, -1)
        elif k in (Qt.Key_Down, Qt.Key_S) and dy == 0:
            self.pending = (0, 1)
        elif k == Qt.Key_Space and not self.alive:
            self.reset()

    def tick(self):
        if not self.alive:
            self.update()
            return
        self.dir = self.pending
        hx, hy = self.snake[0]
        nx, ny = hx + self.dir[0], hy + self.dir[1]
        if nx < 0 or ny < 0 or nx >= self.cols or ny >= self.rows or (nx, ny) in self.snake:
            self.alive = False
            self.update()
            return
        self.snake.insert(0, (nx, ny))
        if (nx, ny) == self.food:
            self.score += 1
            self._place_food()
        else:
            self.snake.pop()
        self.update()

    def _cell(self) -> int:
        # Leave band for score text at top
        return max(6, min(self.width() // self.cols, (self.height() - 18) // self.rows))

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(10, 18, 28))
        cell = self._cell()
        ox = max(0, (self.width() - cell * self.cols) // 2)
        oy = 16
        for x, y in self.snake:
            p.fillRect(
                ox + x * cell, oy + y * cell, cell - 1, cell - 1, QColor(80, 200, 120)
            )
        fx, fy = self.food
        p.fillRect(
            ox + fx * cell, oy + fy * cell, cell - 1, cell - 1, QColor(220, 80, 80)
        )
        p.setPen(QColor(230, 230, 230))
        p.setFont(QFont("DejaVu Sans", 9))
        p.drawText(
            4,
            12,
            f"Score {self.score}" + ("" if self.alive else "  OVER — Space"),
        )


class PongBoard(QWidget):
    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(160)
        self.reset()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(220, 200)

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self.reset()
        self.timer.start(16)
        self.setFocus(Qt.OtherFocusReason)

    def hideEvent(self, e):  # noqa: N802
        self.timer.stop()
        super().hideEvent(e)

    def _dims(self) -> Tuple[int, int]:
        return max(80, self.width()), max(80, self.height())

    def reset(self):
        w, h = self._dims()
        self.field_w = w
        self.field_h = h
        self.px = 12
        self.ph = max(28, h // 5)
        self.py = h // 2 - self.ph // 2
        self.bx = float(w // 2)
        self.by = float(h // 2)
        self.vx = 2.8
        self.vy = 2.1
        self.score = 0
        self.alive = True

    def keyPressEvent(self, e: QKeyEvent):  # noqa: N802
        _, h = self._dims()
        step = max(12, h // 10)
        if e.key() in (Qt.Key_Up, Qt.Key_W):
            self.py = max(0, self.py - step)
        elif e.key() in (Qt.Key_Down, Qt.Key_S):
            self.py = min(h - self.ph, self.py + step)
        elif e.key() == Qt.Key_Space and not self.alive:
            self.reset()

    def tick(self):
        if not self.alive:
            self.update()
            return
        w, h = self._dims()
        self.field_w, self.field_h = w, h
        self.ph = max(28, h // 5)
        self.py = min(self.py, h - self.ph)
        self.bx += self.vx
        self.by += self.vy
        if self.by < 0 or self.by > h - 8:
            self.vy *= -1
        if self.bx < self.px + 12 and self.py < self.by < self.py + self.ph:
            self.vx = abs(self.vx) + 0.08
            self.score += 1
        if self.bx > w - 8:
            self.vx *= -1
        if self.bx < 0:
            self.alive = False
        self.update()

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(10, 18, 28))
        w, h = self._dims()
        p.fillRect(self.px, int(self.py), 8, int(self.ph), QColor(100, 180, 255))
        p.fillRect(int(self.bx), int(self.by), 7, 7, QColor(240, 240, 240))
        p.setPen(QColor(230, 230, 230))
        p.setFont(QFont("DejaVu Sans", 9))
        p.drawText(
            4, 12, f"Score {self.score}" + ("" if self.alive else "  LOST — Space")
        )


class TetrisBoard(QWidget):
    SHAPES = [
        [[1, 1, 1, 1]],
        [[1, 1], [1, 1]],
        [[0, 1, 0], [1, 1, 1]],
        [[1, 0, 0], [1, 1, 1]],
        [[0, 0, 1], [1, 1, 1]],
        [[0, 1, 1], [1, 1, 0]],
        [[1, 1, 0], [0, 1, 1]],
    ]

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(180)
        self.cols, self.rows = 10, 14  # shorter fit digivice
        self.reset()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(220, 220)

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self.reset()
        self.timer.start(450)
        self.setFocus(Qt.OtherFocusReason)

    def hideEvent(self, e):  # noqa: N802
        self.timer.stop()
        super().hideEvent(e)

    def reset(self):
        self.grid = [[0] * self.cols for _ in range(self.rows)]
        self.score = 0
        self.alive = True
        self._spawn()

    def _cell(self) -> int:
        return max(6, min(self.width() // self.cols, (self.height() - 16) // self.rows))

    def _spawn(self):
        self.shape = [row[:] for row in random.choice(self.SHAPES)]
        self.x = self.cols // 2 - len(self.shape[0]) // 2
        self.y = 0
        if self._hits(self.x, self.y, self.shape):
            self.alive = False

    def _hits(self, x, y, shape) -> bool:
        for j, row in enumerate(shape):
            for i, v in enumerate(row):
                if not v:
                    continue
                gx, gy = x + i, y + j
                if gx < 0 or gx >= self.cols or gy >= self.rows:
                    return True
                if gy >= 0 and self.grid[gy][gx]:
                    return True
        return False

    def _merge(self):
        for j, row in enumerate(self.shape):
            for i, v in enumerate(row):
                if v and self.y + j >= 0:
                    self.grid[self.y + j][self.x + i] = 1
        new_g = [r for r in self.grid if not all(r)]
        cleared = self.rows - len(new_g)
        self.score += cleared * 100
        while len(new_g) < self.rows:
            new_g.insert(0, [0] * self.cols)
        self.grid = new_g
        self._spawn()

    def _rotate(self):
        rotated = [list(r) for r in zip(*self.shape[::-1])]
        if not self._hits(self.x, self.y, rotated):
            self.shape = rotated

    def keyPressEvent(self, e: QKeyEvent):  # noqa: N802
        if not self.alive:
            if e.key() == Qt.Key_Space:
                self.reset()
            return
        if e.key() in (Qt.Key_Left, Qt.Key_A):
            if not self._hits(self.x - 1, self.y, self.shape):
                self.x -= 1
        elif e.key() in (Qt.Key_Right, Qt.Key_D):
            if not self._hits(self.x + 1, self.y, self.shape):
                self.x += 1
        elif e.key() in (Qt.Key_Down, Qt.Key_S):
            self.tick()
        elif e.key() in (Qt.Key_Up, Qt.Key_W):
            self._rotate()
        self.update()

    def tick(self):
        if not self.alive:
            self.update()
            return
        if not self._hits(self.x, self.y + 1, self.shape):
            self.y += 1
        else:
            self._merge()
        self.update()

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(10, 18, 28))
        cell = self._cell()
        ox = max(0, (self.width() - cell * self.cols) // 2)
        oy = 2
        for y in range(self.rows):
            for x in range(self.cols):
                if self.grid[y][x]:
                    p.fillRect(
                        ox + x * cell,
                        oy + y * cell,
                        cell - 1,
                        cell - 1,
                        QColor(90, 140, 220),
                    )
        if self.alive:
            for j, row in enumerate(self.shape):
                for i, v in enumerate(row):
                    if v:
                        p.fillRect(
                            ox + (self.x + i) * cell,
                            oy + (self.y + j) * cell,
                            cell - 1,
                            cell - 1,
                            QColor(120, 220, 160),
                        )
        p.setPen(QColor(230, 230, 230))
        p.setFont(QFont("DejaVu Sans", 9))
        p.drawText(
            4,
            min(self.height() - 4, oy + self.rows * cell + 12),
            f"Score {self.score}" + ("" if self.alive else "  OVER — Space"),
        )


class SolitaireBoard(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.reset()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(220, 110)

    def reset(self):
        ranks = "A23456789TJQK"
        suits = "CDHS"
        self.deck = [f"{r}{s}" for r in ranks for s in suits]
        random.shuffle(self.deck)
        self.waste: List[str] = []
        self.foundation: List[str] = []
        self.message = "Draw · foundation A→K"

    def draw(self):
        if not self.deck:
            self.deck = self.waste[::-1]
            self.waste = []
            return
        self.waste.append(self.deck.pop())

    def to_foundation(self):
        if not self.waste:
            return
        card = self.waste[-1]
        if not self.foundation:
            if card[0] == "A":
                self.foundation.append(self.waste.pop())
            return
        order = "A23456789TJQK"
        top = self.foundation[-1][0]
        if order.index(card[0]) == order.index(top) + 1:
            self.foundation.append(self.waste.pop())
            if len(self.foundation) == 13:
                self.message = "Foundation complete!"

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(18, 80, 40))
        p.setPen(QColor(240, 240, 240))
        p.setFont(QFont("DejaVu Sans", 10))
        p.drawText(8, 22, f"Deck {len(self.deck)}  Waste {self.waste[-1] if self.waste else '-'}")
        p.drawText(8, 44, f"Found {' '.join(self.foundation[-4:]) or '-'}")
        p.drawText(8, 70, self.message)


class UnoBoard(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.reset()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(220, 110)

    def reset(self):
        colors = ["R", "G", "B", "Y"]
        self.deck = [f"{c}{n}" for c in colors for n in list(range(10)) + list(range(1, 10))]
        random.shuffle(self.deck)
        self.hand = [self.deck.pop() for _ in range(7)]
        self.pile = [self.deck.pop()]
        self.message = "Match color/number"

    def can_play(self, card: str) -> bool:
        top = self.pile[-1]
        return card[0] == top[0] or card[1:] == top[1:]

    def play_index(self, i: int):
        if 0 <= i < len(self.hand) and self.can_play(self.hand[i]):
            self.pile.append(self.hand.pop(i))
            if not self.hand:
                self.message = "You win!"
            self.update()

    def draw_card(self):
        if self.deck:
            self.hand.append(self.deck.pop())
            self.update()

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(30, 30, 50))
        p.setPen(QColor(240, 240, 240))
        p.setFont(QFont("DejaVu Sans", 10))
        p.drawText(8, 22, f"Pile {self.pile[-1]}  Deck {len(self.deck)}")
        hand = " ".join(f"{i}:{c}" for i, c in enumerate(self.hand[:8]))
        p.drawText(8, 48, hand[:40] + ("…" if len(hand) > 40 else ""))
        p.drawText(8, 74, self.message)


def _wrap_game(title: str, board: QWidget, on_back: Callable[[], None], extra_btns=None) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(4)
    tip = QLabel("D-pad · Space=restart")
    tip.setStyleSheet("color:#9ab;font-size:10px;")
    tip.setWordWrap(True)
    lay.addWidget(tip)
    # Arcade boards fill remaining; solitaire/uno size naturally and scroll
    if hasattr(board, "tick"):
        lay.addWidget(board, 1)
    else:
        lay.addWidget(board)
    if extra_btns:
        # Wrap buttons so they scroll instead of overflowing
        for b in extra_btns:
            b.setMinimumHeight(28)
            lay.addWidget(b)
    return page_chrome(title, body, on_back, scroll=not hasattr(board, "tick"))


def make_snake(on_back):
    return _wrap_game("Snake", SnakeBoard(), on_back)


def make_pong(on_back):
    return _wrap_game("Pong", PongBoard(), on_back)


def make_tetris(on_back):
    return _wrap_game("Tetris", TetrisBoard(), on_back)


def make_solitaire(on_back):
    board = SolitaireBoard()
    draw = QPushButton("Draw")
    found = QPushButton("To foundation")
    reset = QPushButton("New")
    draw.clicked.connect(lambda: (board.draw(), board.update()))
    found.clicked.connect(lambda: (board.to_foundation(), board.update()))
    reset.clicked.connect(lambda: (board.reset(), board.update()))
    return _wrap_game("Solitaire", board, on_back, [draw, found, reset])


def make_uno(on_back):
    board = UnoBoard()
    row_btns = []
    draw = QPushButton("Draw")
    draw.clicked.connect(board.draw_card)
    row_btns.append(draw)
    for i in range(7):
        b = QPushButton(f"Play #{i}")
        b.clicked.connect(lambda _=False, idx=i: board.play_index(idx))
        row_btns.append(b)
    return _wrap_game("Uno", board, on_back, row_btns)
