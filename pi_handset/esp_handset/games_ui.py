"""Simple built-in games (ESP Phone games menu parity)."""

from __future__ import annotations

import random
from typing import Callable, List, Tuple

from PyQt5.QtCore import Qt, QTimer, QRectF
from PyQt5.QtGui import QColor, QPainter, QPen, QBrush, QFont, QKeyEvent
from PyQt5.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget, QHBoxLayout

from esp_handset.pages import page_chrome


class SnakeBoard(QWidget):
    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(320)
        self.cell = 16
        self.cols = 20
        self.rows = 20
        self.reset()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(120)

    def reset(self):
        self.snake: List[Tuple[int, int]] = [(5, 10), (4, 10), (3, 10)]
        self.dir = (1, 0)
        self.pending = (1, 0)
        self.food = (12, 10)
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

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(10, 18, 28))
        for x, y in self.snake:
            p.fillRect(x * self.cell, y * self.cell, self.cell - 1, self.cell - 1, QColor(80, 200, 120))
        fx, fy = self.food
        p.fillRect(fx * self.cell, fy * self.cell, self.cell - 1, self.cell - 1, QColor(220, 80, 80))
        p.setPen(QColor(230, 230, 230))
        p.drawText(8, 20, f"Score {self.score}" + ("" if self.alive else "  GAME OVER — Space"))


class PongBoard(QWidget):
    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(320)
        self.reset()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    def reset(self):
        self.w = 320
        self.h = 320
        self.px = 20
        self.py = 120
        self.ph = 70
        self.bx = 160.0
        self.by = 160.0
        self.vx = 3.2
        self.vy = 2.4
        self.score = 0
        self.alive = True

    def keyPressEvent(self, e: QKeyEvent):  # noqa: N802
        if e.key() in (Qt.Key_Up, Qt.Key_W):
            self.py = max(0, self.py - 24)
        elif e.key() in (Qt.Key_Down, Qt.Key_S):
            self.py = min(self.h - self.ph, self.py + 24)
        elif e.key() == Qt.Key_Space and not self.alive:
            self.reset()

    def tick(self):
        if not self.alive:
            self.update()
            return
        self.bx += self.vx
        self.by += self.vy
        if self.by < 0 or self.by > self.h - 8:
            self.vy *= -1
        if self.bx < self.px + 12 and self.py < self.by < self.py + self.ph:
            self.vx = abs(self.vx) + 0.1
            self.score += 1
        if self.bx > self.w - 8:
            self.vx *= -1
        if self.bx < 0:
            self.alive = False
        self.update()

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(10, 18, 28))
        p.fillRect(self.px, self.py, 10, self.ph, QColor(100, 180, 255))
        p.fillRect(int(self.bx), int(self.by), 8, 8, QColor(240, 240, 240))
        p.setPen(QColor(230, 230, 230))
        p.drawText(8, 20, f"Score {self.score}" + ("" if self.alive else "  LOST — Space"))


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
        self.setMinimumHeight(360)
        self.cols, self.rows = 10, 18
        self.cell = 16
        self.reset()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(450)

    def reset(self):
        self.grid = [[0] * self.cols for _ in range(self.rows)]
        self.score = 0
        self.alive = True
        self._spawn()

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
        # clear lines
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
        for y in range(self.rows):
            for x in range(self.cols):
                if self.grid[y][x]:
                    p.fillRect(x * self.cell, y * self.cell, self.cell - 1, self.cell - 1, QColor(90, 140, 220))
        if self.alive:
            for j, row in enumerate(self.shape):
                for i, v in enumerate(row):
                    if v:
                        p.fillRect(
                            (self.x + i) * self.cell,
                            (self.y + j) * self.cell,
                            self.cell - 1,
                            self.cell - 1,
                            QColor(120, 220, 160),
                        )
        p.setPen(QColor(230, 230, 230))
        p.drawText(8, self.rows * self.cell + 18, f"Score {self.score}" + ("" if self.alive else "  OVER — Space"))


class SolitaireBoard(QWidget):
    """Very small draw-3 klondike-lite: flip through deck, stack same-color descending stub."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(280)
        self.reset()

    def reset(self):
        ranks = "A23456789TJQK"
        suits = "CDHS"
        self.deck = [f"{r}{s}" for r in ranks for s in suits]
        random.shuffle(self.deck)
        self.waste: List[str] = []
        self.foundation: List[str] = []
        self.message = "Tap Draw — build foundation A→K (any suit, simplified)"

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
        p.setFont(QFont("DejaVu Sans", 12))
        p.drawText(12, 28, f"Deck: {len(self.deck)}   Waste: {self.waste[-1] if self.waste else '-'}")
        p.drawText(12, 56, f"Foundation: {' '.join(self.foundation[-5:]) or '-'}")
        p.drawText(12, 90, self.message)


class UnoBoard(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(280)
        self.reset()

    def reset(self):
        colors = ["R", "G", "B", "Y"]
        self.deck = [f"{c}{n}" for c in colors for n in list(range(10)) + list(range(1, 10))]
        random.shuffle(self.deck)
        self.hand = [self.deck.pop() for _ in range(7)]
        self.pile = [self.deck.pop()]
        self.message = "Play matching color/number · Draw if stuck"

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
        p.drawText(12, 28, f"Pile: {self.pile[-1]}   Deck: {len(self.deck)}")
        p.drawText(12, 56, "Hand: " + "  ".join(f"{i}:{c}" for i, c in enumerate(self.hand)))
        p.drawText(12, 90, self.message)


def _wrap_game(title: str, board: QWidget, on_back: Callable[[], None], extra_btns=None) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    tip = QLabel("Focus the board · arrows/WASD · Space restarts")
    tip.setStyleSheet("color:#9ab;font-size:11px;")
    lay.addWidget(tip)
    lay.addWidget(board, 1)
    if extra_btns:
        row = QHBoxLayout()
        for b in extra_btns:
            row.addWidget(b)
        lay.addLayout(row)
    board.setFocus()
    return page_chrome(title, body, on_back)


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
        b = QPushButton(str(i))
        b.clicked.connect(lambda _=False, idx=i: board.play_index(idx))
        row_btns.append(b)
    return _wrap_game("Uno", board, on_back, row_btns)
