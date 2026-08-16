"""Digivice arcade + card games — splash, title menu, polished playfields."""
from __future__ import annotations

import random
from typing import Callable, Optional

from PyQt5.QtCore import QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
    QRadialGradient,
)
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from esp_handset.pages import page_chrome
from esp_handset import store

# ── palette ──────────────────────────────────────────────────────────────────
_BG = QColor("#0a0e14")
_PANEL = QColor("#121820")
_EDGE = QColor("#1e2a38")
_INK = QColor("#e8f0ff")
_MUTED = QColor("#7a8fa8")
_GOLD = QColor("#ffd56a")


def _scores() -> dict:
    return dict(store.load("games_scores.json", {}) or {})


def _best(key: str) -> int:
    try:
        return int(_scores().get(key, 0))
    except Exception:
        return 0


def _save_best(key: str, score: int) -> int:
    cur = _best(key)
    if score <= cur:
        return cur
    scores = _scores()
    scores[key] = int(score)
    store.save("games_scores.json", scores)
    return int(score)


def _font(px: int, bold: bool = False) -> QFont:
    f = QFont("DejaVu Sans")
    f.setPixelSize(max(9, int(px)))
    f.setBold(bool(bold))
    return f


def _fill_crt(p: QPainter, r: QRect, accent: QColor) -> None:
    g = QLinearGradient(0, r.top(), 0, r.bottom())
    g.setColorAt(0.0, QColor("#0d1520"))
    g.setColorAt(0.55, _BG)
    g.setColorAt(1.0, QColor("#05080c"))
    p.fillRect(r, g)
    # soft vignette
    rg = QRadialGradient(r.center(), max(r.width(), r.height()) * 0.72)
    rg.setColorAt(0.0, QColor(0, 0, 0, 0))
    rg.setColorAt(1.0, QColor(0, 0, 0, 110))
    p.fillRect(r, rg)
    # scanlines
    p.setPen(QPen(QColor(255, 255, 255, 10), 1))
    for y in range(r.top(), r.bottom(), 3):
        p.drawLine(r.left(), y, r.right(), y)
    # corner glow
    p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 40), 2))
    p.drawRoundedRect(r.adjusted(3, 3, -3, -3), 8, 8)


def _draw_title_block(
    p: QPainter,
    r: QRect,
    title: str,
    tagline: str,
    accent: QColor,
    *,
    phase: float = 0.0,
) -> None:
    _fill_crt(p, r, accent)
    # decorative marquee bars
    bar = QRect(r.left() + 14, r.top() + 18, r.width() - 28, 6)
    g = QLinearGradient(bar.left(), 0, bar.right(), 0)
    g.setColorAt(0.0, QColor(0, 0, 0, 0))
    g.setColorAt(0.2 + 0.15 * abs((phase % 1.0) - 0.5), accent)
    g.setColorAt(0.8, accent.darker(140))
    g.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.fillRect(bar, g)
    p.fillRect(QRect(bar.left(), r.bottom() - 24, bar.width(), 4), g)

    p.setPen(QColor(accent.red(), accent.green(), accent.blue(), 90))
    p.setFont(_font(28, True))
    shadow = QRect(r.left() + 2, r.top() + 52, r.width(), 36)
    p.drawText(shadow, Qt.AlignHCenter | Qt.AlignTop, title)
    p.setPen(accent)
    p.drawText(QRect(r.left(), r.top() + 50, r.width(), 36), Qt.AlignHCenter | Qt.AlignTop, title)

    p.setPen(_MUTED)
    p.setFont(_font(11))
    p.drawText(QRect(r.left() + 10, r.top() + 92, r.width() - 20, 36), Qt.AlignHCenter | Qt.AlignTop, tagline)


class SplashPane(QWidget):
    finished = pyqtSignal()

    def __init__(self, title: str, tagline: str, accent: QColor, parent=None):
        super().__init__(parent)
        self.title = title
        self.tagline = tagline
        self.accent = accent
        self._t = 0.0
        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._hold = QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.timeout.connect(self.finished.emit)
        self.setFocusPolicy(Qt.StrongFocus)

    def showEvent(self, e):
        super().showEvent(e)
        self._t = 0.0
        self._anim.start(40)
        self._hold.start(1600)
        self.setFocus()

    def hideEvent(self, e):
        self._anim.stop()
        self._hold.stop()
        super().hideEvent(e)

    def _tick(self):
        self._t += 0.04
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        _draw_title_block(p, self.rect(), self.title, self.tagline, self.accent, phase=self._t)
        # press hint fades in
        alpha = min(220, int(max(0, self._t - 0.6) * 280))
        p.setPen(QColor(200, 220, 255, alpha))
        p.setFont(_font(10))
        p.drawText(self.rect().adjusted(0, 0, 0, -28), Qt.AlignHCenter | Qt.AlignBottom, "Confirm · skip")

    def digi_confirm(self):
        self._hold.stop()
        self.finished.emit()

    def digi_back(self):
        return False


class MenuPane(QWidget):
    play = pyqtSignal()
    back = pyqtSignal()

    def __init__(self, title: str, tagline: str, accent: QColor, score_key: str, howto: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.tagline = tagline
        self.accent = accent
        self.score_key = score_key
        self.howto = howto
        self._idx = 0  # 0 play, 1 how-to toggle
        self._show_how = False
        self._pulse = 0.0
        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(160)

    def showEvent(self, e):
        super().showEvent(e)
        self._show_how = False
        self._idx = 0
        self._anim.start(50)
        self.setFocus()
        self.update()

    def hideEvent(self, e):
        self._anim.stop()
        super().hideEvent(e)

    def _tick(self):
        self._pulse = (self._pulse + 0.05) % 1.0
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()
        _fill_crt(p, r, self.accent)

        p.setPen(self.accent)
        p.setFont(_font(22, True))
        p.drawText(QRect(0, 14, r.width(), 28), Qt.AlignHCenter | Qt.AlignTop, self.title)
        p.setPen(_MUTED)
        p.setFont(_font(10))
        p.drawText(QRect(12, 42, r.width() - 24, 18), Qt.AlignHCenter | Qt.AlignTop, self.tagline)

        best = _best(self.score_key) if self.score_key else 0
        if self.score_key:
            p.setPen(_GOLD)
            p.setFont(_font(11, True))
            p.drawText(QRect(12, 62, r.width() - 24, 18), Qt.AlignHCenter | Qt.AlignTop, f"HIGH SCORE  {best}")
            menu_top = 92
        else:
            menu_top = 78

        if self._show_how:
            box = QRect(14, 88, r.width() - 28, r.height() - 120)
            p.setBrush(QColor(18, 24, 32, 220))
            p.setPen(QPen(_EDGE, 1))
            p.drawRoundedRect(box, 8, 8)
            p.setPen(_INK)
            p.setFont(_font(10))
            p.drawText(box.adjusted(8, 8, -8, -8), Qt.TextWordWrap | Qt.AlignTop | Qt.AlignLeft, self.howto)
            p.setPen(_MUTED)
            p.setFont(_font(9))
            p.drawText(r.adjusted(0, 0, 0, -10), Qt.AlignHCenter | Qt.AlignBottom, "Confirm · close")
            return

        # menu items
        items = ["▶  PLAY", "◆  HOW TO PLAY"]
        y0 = menu_top
        for i, label in enumerate(items):
            br = QRect(28, y0 + i * 36, r.width() - 56, 30)
            sel = i == self._idx
            if sel:
                glow = QColor(self.accent)
                glow.setAlpha(40 + int(30 * abs(self._pulse - 0.5) * 2))
                p.setBrush(glow)
                p.setPen(QPen(self.accent, 2))
            else:
                p.setBrush(QColor(20, 28, 38, 180))
                p.setPen(QPen(_EDGE, 1))
            p.drawRoundedRect(br, 8, 8)
            p.setPen(self.accent if sel else _INK)
            p.setFont(_font(12, sel))
            p.drawText(br, Qt.AlignCenter, label)

        p.setPen(QColor(120, 140, 160, 160))
        p.setFont(_font(9))
        p.drawText(r.adjusted(0, 0, 0, -8), Qt.AlignHCenter | Qt.AlignBottom, "↑↓ select · Confirm · Back")

    def digi_nav(self, dx: int, dy: int) -> bool:
        if self._show_how:
            return True
        if dy:
            self._idx = (self._idx + (1 if dy > 0 else -1)) % 2
            self.update()
            return True
        return bool(dx)

    def digi_confirm(self):
        if self._show_how:
            self._show_how = False
            self.update()
            return
        if self._idx == 0:
            self.play.emit()
        else:
            self._show_how = True
            self.update()

    def digi_back(self):
        if self._show_how:
            self._show_how = False
            self.update()
            return True
        return False


class GameOverPane(QWidget):
    again = pyqtSignal()
    menu = pyqtSignal()

    def __init__(self, accent: QColor, score_key: str, parent=None):
        super().__init__(parent)
        self.accent = accent
        self.score_key = score_key
        self.score = 0
        self.best = 0
        self.is_new = False
        self._idx = 0
        self.setFocusPolicy(Qt.StrongFocus)

    def set_result(self, score: int):
        self.score = int(score)
        prev = _best(self.score_key)
        self.best = _save_best(self.score_key, self.score)
        self.is_new = self.score > prev
        self._idx = 0
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()
        _fill_crt(p, r, self.accent)
        p.setPen(self.accent)
        p.setFont(_font(20, True))
        p.drawText(QRect(0, 24, r.width(), 28), Qt.AlignHCenter, "GAME OVER")
        p.setPen(_INK)
        p.setFont(_font(14, True))
        p.drawText(QRect(0, 58, r.width(), 22), Qt.AlignHCenter, f"SCORE  {self.score}")
        p.setPen(_GOLD if self.is_new else _MUTED)
        p.setFont(_font(11, True))
        label = "NEW HIGH SCORE!" if self.is_new else f"BEST  {self.best}"
        p.drawText(QRect(0, 84, r.width(), 18), Qt.AlignHCenter, label)

        items = ["PLAY AGAIN", "TITLE"]
        y0 = 120
        for i, label in enumerate(items):
            br = QRect(36, y0 + i * 34, r.width() - 72, 28)
            sel = i == self._idx
            p.setBrush(QColor(self.accent.red(), self.accent.green(), self.accent.blue(), 50) if sel else QColor(20, 28, 38))
            p.setPen(QPen(self.accent if sel else _EDGE, 2 if sel else 1))
            p.drawRoundedRect(br, 8, 8)
            p.setPen(self.accent if sel else _INK)
            p.setFont(_font(11, sel))
            p.drawText(br, Qt.AlignCenter, label)

    def digi_nav(self, dx: int, dy: int) -> bool:
        if dy:
            self._idx = (self._idx + (1 if dy > 0 else -1)) % 2
            self.update()
            return True
        return bool(dx)

    def digi_confirm(self):
        if self._idx == 0:
            self.again.emit()
        else:
            self.menu.emit()

    def digi_back(self):
        self.menu.emit()
        return True


class ArcadeShell(QWidget):
    """Splash → menu → play → game over for timed arcade games."""

    def __init__(
        self,
        *,
        title: str,
        tagline: str,
        accent: QColor,
        score_key: str,
        howto: str,
        board: QWidget,
        on_back: Callable,
        parent=None,
    ):
        super().__init__(parent)
        self._on_back = on_back
        self.board = board
        self.score_key = score_key
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)

        self.splash = SplashPane(title, tagline, accent)
        self.menu = MenuPane(title, tagline, accent, score_key, howto)
        self.over = GameOverPane(accent, score_key)

        play = QWidget()
        pl = QVBoxLayout(play)
        pl.setContentsMargins(4, 4, 4, 4)
        pl.setSpacing(4)
        self._hud = QLabel("SCORE 0")
        self._hud.setAlignment(Qt.AlignCenter)
        self._hud.setStyleSheet(
            f"color:{accent.name()};font-size:11px;font-weight:700;"
            "background:#101820;border:1px solid #243040;border-radius:6px;padding:4px;"
        )
        pl.addWidget(self._hud)
        pl.addWidget(board, 1)
        tip = QLabel("D-pad move · Confirm pause · Space restart")
        tip.setAlignment(Qt.AlignCenter)
        tip.setStyleSheet("color:#6a7a8a;font-size:9px;")
        tip.setWordWrap(True)
        pl.addWidget(tip)
        self.play_page = play

        self.stack.addWidget(self.splash)
        self.stack.addWidget(self.menu)
        self.stack.addWidget(self.play_page)
        self.stack.addWidget(self.over)

        self.splash.finished.connect(self._to_menu)
        self.menu.play.connect(self._to_play)
        self.over.again.connect(self._to_play)
        self.over.menu.connect(self._to_menu)

        if hasattr(board, "scoreChanged"):
            board.scoreChanged.connect(self._on_score)
        if hasattr(board, "gameOver"):
            board.gameOver.connect(self._on_game_over)

        self.stack.setCurrentWidget(self.splash)

    def showEvent(self, e):
        super().showEvent(e)
        self.stack.setCurrentWidget(self.splash)

    def _to_menu(self):
        if hasattr(self.board, "stop"):
            self.board.stop()
        self.stack.setCurrentWidget(self.menu)
        self.menu.setFocus()

    def _to_play(self):
        self._hud.setText("SCORE 0")
        self.stack.setCurrentWidget(self.play_page)
        if hasattr(self.board, "begin"):
            self.board.begin()
        self.board.setFocus()

    def _on_score(self, n: int):
        best = _best(self.score_key)
        self._hud.setText(f"SCORE {int(n)}   ·   BEST {best}")

    def _on_game_over(self, n: int):
        if hasattr(self.board, "stop"):
            self.board.stop()
        self.over.set_result(int(n))
        self.stack.setCurrentWidget(self.over)
        self.over.setFocus()

    def digi_nav(self, dx: int, dy: int) -> bool:
        w = self.stack.currentWidget()
        if w is self.play_page:
            if hasattr(self.board, "digi_nav"):
                return bool(self.board.digi_nav(dx, dy))
            return False
        if hasattr(w, "digi_nav"):
            return bool(w.digi_nav(dx, dy))
        return False

    def digi_confirm(self):
        w = self.stack.currentWidget()
        if w is self.play_page:
            if hasattr(self.board, "digi_confirm"):
                self.board.digi_confirm()
            return
        if hasattr(w, "digi_confirm"):
            w.digi_confirm()

    def digi_back(self):
        w = self.stack.currentWidget()
        if w is self.play_page:
            self._to_menu()
            return True
        if w is self.over:
            self._to_menu()
            return True
        if w is self.splash:
            self._to_menu()
            return True
        if w is self.menu and hasattr(w, "digi_back"):
            return bool(w.digi_back())
        return False


# ── Snake ────────────────────────────────────────────────────────────────────
class SnakeBoard(QWidget):
    scoreChanged = pyqtSignal(int)
    gameOver = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(150)
        self.cols, self.rows = 14, 16
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.paused = False
        self.reset(silent=True)

    def reset(self, silent: bool = False):
        self.snake = [QPoint(5, 8), QPoint(4, 8), QPoint(3, 8)]
        self.dir = QPoint(1, 0)
        self.pending = QPoint(1, 0)
        self.food = QPoint(9, 8)
        self.alive = True
        self.score = 0
        self.paused = False
        self._place_food()
        if not silent:
            self.scoreChanged.emit(0)
        self.update()

    def begin(self):
        self.reset()
        self.timer.start(120)
        self.setFocus()

    def stop(self):
        self.timer.stop()

    def _place_food(self):
        cells = { (p.x(), p.y()) for p in self.snake }
        for _ in range(200):
            x, y = random.randrange(self.cols), random.randrange(self.rows)
            if (x, y) not in cells:
                self.food = QPoint(x, y)
                return

    def tick(self):
        if not self.alive or self.paused:
            return
        self.dir = QPoint(self.pending.x(), self.pending.y())
        head = self.snake[0] + self.dir
        if head.x() < 0 or head.y() < 0 or head.x() >= self.cols or head.y() >= self.rows:
            self.alive = False
            self.timer.stop()
            self.gameOver.emit(self.score)
            self.update()
            return
        if any(head == s for s in self.snake):
            self.alive = False
            self.timer.stop()
            self.gameOver.emit(self.score)
            self.update()
            return
        self.snake.insert(0, head)
        if head == self.food:
            self.score += 10
            self.scoreChanged.emit(self.score)
            self._place_food()
        else:
            self.snake.pop()
        self.update()

    def digi_nav(self, dx: int, dy: int) -> bool:
        if not self.alive:
            return False
        nd = QPoint(dx, dy)
        if nd.x() == -self.dir.x() and nd.y() == -self.dir.y():
            return True
        if dx or dy:
            self.pending = nd
            return True
        return False

    def digi_confirm(self):
        if not self.alive:
            return
        self.paused = not self.paused
        self.update()

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Space, Qt.Key_Return) and not self.alive:
            self.begin()
            return
        m = {
            Qt.Key_Left: QPoint(-1, 0),
            Qt.Key_Right: QPoint(1, 0),
            Qt.Key_Up: QPoint(0, -1),
            Qt.Key_Down: QPoint(0, 1),
            Qt.Key_A: QPoint(-1, 0),
            Qt.Key_D: QPoint(1, 0),
            Qt.Key_W: QPoint(0, -1),
            Qt.Key_S: QPoint(0, 1),
        }
        if k in m:
            self.digi_nav(m[k].x(), m[k].y())

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()
        accent = QColor("#3dff9a")
        _fill_crt(p, r, accent)
        margin = 8
        board = r.adjusted(margin, margin, -margin, -margin)
        cw = board.width() / self.cols
        ch = board.height() / self.rows
        # grid wash
        p.setPen(QPen(QColor(40, 60, 50, 50), 1))
        for x in range(self.cols + 1):
            xx = int(board.left() + x * cw)
            p.drawLine(xx, board.top(), xx, board.bottom())
        for y in range(self.rows + 1):
            yy = int(board.top() + y * ch)
            p.drawLine(board.left(), yy, board.right(), yy)

        # food — glowing apple
        fx = board.left() + self.food.x() * cw
        fy = board.top() + self.food.y() * ch
        fr = QRect(int(fx + 2), int(fy + 2), int(cw - 4), int(ch - 4))
        glow = QRadialGradient(fr.center(), fr.width())
        glow.setColorAt(0.0, QColor("#ff6b6b"))
        glow.setColorAt(1.0, QColor("#ff6b6b00"))
        p.setBrush(glow)
        p.setPen(Qt.NoPen)
        p.drawEllipse(fr.adjusted(-2, -2, 2, 2))
        p.setBrush(QColor("#ff5252"))
        p.drawRoundedRect(fr, 4, 4)

        n = len(self.snake)
        for i, s in enumerate(self.snake):
            t = i / max(1, n - 1)
            c = QColor("#7dffb0") if i == 0 else QColor(
                int(30 + 40 * (1 - t)),
                int(180 + 40 * (1 - t)),
                int(90 + 30 * (1 - t)),
            )
            sx = board.left() + s.x() * cw
            sy = board.top() + s.y() * ch
            cell = QRect(int(sx + 1), int(sy + 1), int(cw - 2), int(ch - 2))
            p.setBrush(c)
            p.setPen(QPen(c.lighter(130), 1))
            p.drawRoundedRect(cell, 4, 4)
            if i == 0:
                p.setBrush(QColor("#0a120e"))
                eye = 2
                p.drawEllipse(cell.center() + QPoint(-3, -2), eye, eye)
                p.drawEllipse(cell.center() + QPoint(3, -2), eye, eye)

        if self.paused and self.alive:
            p.fillRect(r, QColor(0, 0, 0, 120))
            p.setPen(accent)
            p.setFont(_font(16, True))
            p.drawText(r, Qt.AlignCenter, "PAUSED")


# ── Pong ─────────────────────────────────────────────────────────────────────
class PongBoard(QWidget):
    scoreChanged = pyqtSignal(int)
    gameOver = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(150)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.paused = False
        self.reset(silent=True)

    def reset(self, silent: bool = False):
        self.player_y = 0.5
        self.ai_y = 0.5
        self.ball = [0.5, 0.5]
        self.vel = [0.012, 0.008]
        self.score_p = 0
        self.score_ai = 0
        self.alive = True
        self.paused = False
        if not silent:
            self.scoreChanged.emit(0)
        self.update()

    def begin(self):
        self.reset()
        self.timer.start(28)
        self.setFocus()

    def stop(self):
        self.timer.stop()

    def tick(self):
        if not self.alive or self.paused:
            return
        self.ball[0] += self.vel[0]
        self.ball[1] += self.vel[1]
        if self.ball[1] <= 0.02 or self.ball[1] >= 0.98:
            self.vel[1] *= -1
        py = self.player_y
        if abs(self.ball[0] - 0.06) < 0.02 and abs(self.ball[1] - py) < 0.12:
            self.vel[0] = abs(self.vel[0])
            self.vel[1] += (self.ball[1] - py) * 0.04
        target = self.ball[1]
        self.ai_y += max(-0.018, min(0.018, target - self.ai_y))
        if abs(self.ball[0] - 0.94) < 0.02 and abs(self.ball[1] - self.ai_y) < 0.12:
            self.vel[0] = -abs(self.vel[0])
        if self.ball[0] < 0:
            self.score_ai += 1
            self._serve(1)
        elif self.ball[0] > 1:
            self.score_p += 1
            self.scoreChanged.emit(self.score_p)
            self._serve(-1)
        if self.score_ai >= 5:
            self.alive = False
            self.timer.stop()
            self.gameOver.emit(self.score_p)
        self.update()

    def _serve(self, direction: int):
        self.ball = [0.5, 0.5]
        self.vel = [0.012 * direction, random.choice([-0.008, 0.008])]

    def digi_nav(self, dx: int, dy: int) -> bool:
        if dy:
            self.player_y = max(0.08, min(0.92, self.player_y + 0.06 * (1 if dy > 0 else -1)))
            self.update()
            return True
        return bool(dx)

    def digi_confirm(self):
        if self.alive:
            self.paused = not self.paused
            self.update()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Up, Qt.Key_W):
            self.digi_nav(0, -1)
        elif e.key() in (Qt.Key_Down, Qt.Key_S):
            self.digi_nav(0, 1)
        elif e.key() == Qt.Key_Space and not self.alive:
            self.begin()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()
        accent = QColor("#5ad1ff")
        _fill_crt(p, r, accent)
        court = r.adjusted(10, 10, -10, -10)
        p.setPen(QPen(QColor("#2a4058"), 2, Qt.DashLine))
        mid = court.center().x()
        p.drawLine(mid, court.top(), mid, court.bottom())
        p.setPen(QPen(QColor("#3a5570"), 2))
        p.drawRoundedRect(court, 6, 6)

        ph = int(court.height() * 0.2)
        pw = 8
        py = int(court.top() + self.player_y * court.height() - ph / 2)
        ay = int(court.top() + self.ai_y * court.height() - ph / 2)
        p.setBrush(QColor("#7ee0ff"))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRect(court.left() + 4, py, pw, ph), 3, 3)
        p.setBrush(QColor("#ff8fab"))
        p.drawRoundedRect(QRect(court.right() - 12, ay, pw, ph), 3, 3)

        bx = int(court.left() + self.ball[0] * court.width())
        by = int(court.top() + self.ball[1] * court.height())
        glow = QRadialGradient(QPoint(bx, by), 14)
        glow.setColorAt(0.0, QColor("#ffffff"))
        glow.setColorAt(1.0, QColor("#5ad1ff00"))
        p.setBrush(glow)
        p.drawEllipse(QPoint(bx, by), 10, 10)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QPoint(bx, by), 5, 5)

        p.setPen(_INK)
        p.setFont(_font(14, True))
        p.drawText(QRect(court.left(), court.top() + 4, court.width() // 2, 20), Qt.AlignCenter, str(self.score_p))
        p.drawText(QRect(mid, court.top() + 4, court.width() // 2, 20), Qt.AlignCenter, str(self.score_ai))

        if self.paused and self.alive:
            p.fillRect(r, QColor(0, 0, 0, 120))
            p.setPen(accent)
            p.setFont(_font(16, True))
            p.drawText(r, Qt.AlignCenter, "PAUSED")


# ── Tetris ───────────────────────────────────────────────────────────────────
_SHAPES = {
    "I": [[1, 1, 1, 1]],
    "O": [[1, 1], [1, 1]],
    "T": [[0, 1, 0], [1, 1, 1]],
    "S": [[0, 1, 1], [1, 1, 0]],
    "Z": [[1, 1, 0], [0, 1, 1]],
    "J": [[1, 0, 0], [1, 1, 1]],
    "L": [[0, 0, 1], [1, 1, 1]],
}
_COLORS = {
    "I": "#5ad1ff",
    "O": "#ffd56a",
    "T": "#c792ea",
    "S": "#3dff9a",
    "Z": "#ff6b6b",
    "J": "#82aaff",
    "L": "#ff9e64",
}


class TetrisBoard(QWidget):
    scoreChanged = pyqtSignal(int)
    gameOver = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(160)
        self.w, self.h = 10, 16
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.paused = False
        self.reset(silent=True)

    def reset(self, silent: bool = False):
        self.grid = [[None for _ in range(self.w)] for _ in range(self.h)]
        self.score = 0
        self.alive = True
        self.paused = False
        self._spawn()
        if not silent:
            self.scoreChanged.emit(0)
        self.update()

    def begin(self):
        self.reset()
        self.timer.start(420)
        self.setFocus()

    def stop(self):
        self.timer.stop()

    def _spawn(self):
        self.kind = random.choice(list(_SHAPES.keys()))
        self.shape = [row[:] for row in _SHAPES[self.kind]]
        self.px = self.w // 2 - len(self.shape[0]) // 2
        self.py = 0
        if self._hits(self.px, self.py, self.shape):
            self.alive = False

    def _hits(self, x, y, shape) -> bool:
        for r, row in enumerate(shape):
            for c, v in enumerate(row):
                if not v:
                    continue
                gx, gy = x + c, y + r
                if gx < 0 or gx >= self.w or gy >= self.h:
                    return True
                if gy >= 0 and self.grid[gy][gx]:
                    return True
        return False

    def _lock(self):
        for r, row in enumerate(self.shape):
            for c, v in enumerate(row):
                if not v:
                    continue
                gy, gx = self.py + r, self.px + c
                if 0 <= gy < self.h and 0 <= gx < self.w:
                    self.grid[gy][gx] = self.kind
        cleared = 0
        new_grid = []
        for row in self.grid:
            if all(row):
                cleared += 1
            else:
                new_grid.append(row)
        while len(new_grid) < self.h:
            new_grid.insert(0, [None for _ in range(self.w)])
        self.grid = new_grid
        if cleared:
            self.score += (cleared * cleared) * 100
            self.scoreChanged.emit(self.score)
            self.timer.setInterval(max(140, 420 - self.score // 50))
        self._spawn()
        if not self.alive:
            self.timer.stop()
            self.gameOver.emit(self.score)

    def tick(self):
        if not self.alive or self.paused:
            return
        if not self._hits(self.px, self.py + 1, self.shape):
            self.py += 1
        else:
            self._lock()
        self.update()

    def _rotate(self):
        rotated = [list(row) for row in zip(*self.shape[::-1])]
        if not self._hits(self.px, self.py, rotated):
            self.shape = rotated

    def digi_nav(self, dx: int, dy: int) -> bool:
        if not self.alive or self.paused:
            return False
        if dx and not self._hits(self.px + dx, self.py, self.shape):
            self.px += dx
            self.update()
            return True
        if dy > 0 and not self._hits(self.px, self.py + 1, self.shape):
            self.py += 1
            self.update()
            return True
        if dy < 0:
            self._rotate()
            self.update()
            return True
        return False

    def digi_confirm(self):
        if self.alive:
            self.paused = not self.paused
            self.update()

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Left, Qt.Key_A):
            self.digi_nav(-1, 0)
        elif k in (Qt.Key_Right, Qt.Key_D):
            self.digi_nav(1, 0)
        elif k in (Qt.Key_Down, Qt.Key_S):
            self.digi_nav(0, 1)
        elif k in (Qt.Key_Up, Qt.Key_W):
            self.digi_nav(0, -1)
        elif k == Qt.Key_Space and not self.alive:
            self.begin()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()
        accent = QColor("#c792ea")
        _fill_crt(p, r, accent)
        margin = 8
        board = r.adjusted(margin, margin, -margin, -margin)
        cw = board.width() / self.w
        ch = board.height() / self.h
        p.setBrush(QColor("#0c1218"))
        p.setPen(QPen(QColor("#2a3545"), 2))
        p.drawRoundedRect(board, 6, 6)

        def draw_cell(gx, gy, kind, ghost=False):
            if gy < 0:
                return
            x = int(board.left() + gx * cw)
            y = int(board.top() + gy * ch)
            cell = QRect(x + 1, y + 1, int(cw - 2), int(ch - 2))
            col = QColor(_COLORS.get(kind, "#888"))
            if ghost:
                col.setAlpha(70)
            g = QLinearGradient(cell.topLeft(), cell.bottomRight())
            g.setColorAt(0.0, col.lighter(130))
            g.setColorAt(1.0, col.darker(120))
            p.setBrush(g)
            p.setPen(QPen(col.lighter(150), 1))
            p.drawRoundedRect(cell, 3, 3)

        for y in range(self.h):
            for x in range(self.w):
                if self.grid[y][x]:
                    draw_cell(x, y, self.grid[y][x])

        # ghost
        gy = self.py
        while not self._hits(self.px, gy + 1, self.shape):
            gy += 1
        for rr, row in enumerate(self.shape):
            for cc, v in enumerate(row):
                if v:
                    draw_cell(self.px + cc, gy + rr, self.kind, ghost=True)

        for rr, row in enumerate(self.shape):
            for cc, v in enumerate(row):
                if v:
                    draw_cell(self.px + cc, self.py + rr, self.kind)

        if self.paused and self.alive:
            p.fillRect(r, QColor(0, 0, 0, 120))
            p.setPen(accent)
            p.setFont(_font(16, True))
            p.drawText(r, Qt.AlignCenter, "PAUSED")


# ── Solitaire ────────────────────────────────────────────────────────────────
_SUITS = "♠♥♦♣"
_RANKS = "A23456789TJQK"


def _card_color(suit: str) -> QColor:
    return QColor("#ff6b7a") if suit in "♥♦" else QColor("#e8f0ff")


class SolitaireBoard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self.setFocusPolicy(Qt.StrongFocus)
        self.reset()

    def reset(self):
        deck = [(r, s) for s in _SUITS for r in _RANKS]
        random.shuffle(deck)
        self.stock = deck
        self.waste: list = []
        self.foundations = {s: [] for s in _SUITS}
        self.tableau = [[] for _ in range(7)]
        for i in range(7):
            for j in range(i + 1):
                self.tableau[i].append(self.stock.pop())
        self.sel_col = 0
        self.message = "Draw · move · foundation"
        self.update()

    def draw(self):
        if not self.stock:
            self.stock = list(reversed(self.waste))
            self.waste = []
        elif self.stock:
            self.waste.append(self.stock.pop())
        self.update()

    def to_foundation(self):
        if not self.waste:
            self.message = "Nothing on waste"
            self.update()
            return
        r, s = self.waste[-1]
        pile = self.foundations[s]
        need = _RANKS[len(pile)] if len(pile) < 13 else None
        if need == r:
            pile.append(self.waste.pop())
            self.message = f"{r}{s} → foundation"
        else:
            self.message = "Can't place"
        self.update()

    def digi_nav(self, dx: int, dy: int) -> bool:
        if dx:
            self.sel_col = (self.sel_col + (1 if dx > 0 else -1)) % 7
            self.update()
            return True
        return bool(dy)

    def digi_confirm(self):
        self.draw()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()
        accent = QColor("#3dff9a")
        _fill_crt(p, r, accent)
        cw, ch = 28, 38
        y0 = 12
        # stock / waste
        self._draw_card_back(p, 12, y0, cw, ch)
        p.setPen(_MUTED)
        p.setFont(_font(8))
        p.drawText(QRect(8, y0 + ch + 2, cw + 8, 12), Qt.AlignCenter, f"{len(self.stock)}")
        if self.waste:
            self._draw_card(p, 48, y0, cw, ch, self.waste[-1])
        # foundations
        x = r.width() - 4 * (cw + 6) - 8
        for i, s in enumerate(_SUITS):
            pile = self.foundations[s]
            if pile:
                self._draw_card(p, x + i * (cw + 6), y0, cw, ch, pile[-1])
            else:
                self._draw_slot(p, x + i * (cw + 6), y0, cw, ch, s)

        # tableau
        ty = y0 + ch + 20
        gap = max(cw + 4, (r.width() - 16) // 7)
        for i, col in enumerate(self.tableau):
            tx = 8 + i * gap
            if not col:
                self._draw_slot(p, tx, ty, cw, ch, "")
            for j, card in enumerate(col):
                self._draw_card(p, tx, ty + j * 12, cw, ch, card, selected=(i == self.sel_col and j == len(col) - 1))
        p.setPen(_MUTED)
        p.setFont(_font(9))
        p.drawText(QRect(8, r.height() - 18, r.width() - 16, 14), Qt.AlignCenter, self.message)

    def _draw_slot(self, p, x, y, w, h, label):
        p.setBrush(QColor(20, 40, 30, 120))
        p.setPen(QPen(QColor("#2a5040"), 1, Qt.DashLine))
        p.drawRoundedRect(QRect(x, y, w, h), 4, 4)
        if label:
            p.setPen(QColor("#3a6050"))
            p.setFont(_font(12, True))
            p.drawText(QRect(x, y, w, h), Qt.AlignCenter, label)

    def _draw_card_back(self, p, x, y, w, h):
        p.setBrush(QColor("#1a3a5c"))
        p.setPen(QPen(QColor("#5ad1ff"), 1))
        p.drawRoundedRect(QRect(x, y, w, h), 4, 4)
        p.setPen(QPen(QColor("#3a6a9c"), 1))
        p.drawRect(x + 4, y + 4, w - 8, h - 8)

    def _draw_card(self, p, x, y, w, h, card, selected=False):
        rank, suit = card
        p.setBrush(QColor("#f4f7fb"))
        p.setPen(QPen(QColor("#ffd56a") if selected else QColor("#1a2030"), 2 if selected else 1))
        p.drawRoundedRect(QRect(x, y, w, h), 4, 4)
        p.setPen(_card_color(suit))
        p.setFont(_font(9, True))
        p.drawText(QRect(x + 2, y + 2, w - 4, 14), Qt.AlignLeft, f"{rank}{suit}")


# ── Uno (simple) ─────────────────────────────────────────────────────────────
_UNO_COLORS = ["R", "G", "B", "Y"]
_UNO_HEX = {"R": "#ff5252", "G": "#3dff9a", "B": "#5ad1ff", "Y": "#ffd56a"}


class UnoBoard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.setFocusPolicy(Qt.StrongFocus)
        self.reset()

    def reset(self):
        deck = [(c, n) for c in _UNO_COLORS for n in range(10)]
        random.shuffle(deck)
        self.hand = [deck.pop() for _ in range(7)]
        self.pile = [deck.pop()]
        self.deck = deck
        self.sel = 0
        self.message = "Match color or number"
        self.update()

    def draw_card(self):
        if self.deck:
            self.hand.append(self.deck.pop())
            self.message = "Drew a card"
            self.sel = len(self.hand) - 1
        else:
            self.message = "Deck empty"
        self.update()

    def play_index(self, idx: int):
        if idx < 0 or idx >= len(self.hand):
            return
        card = self.hand[idx]
        top = self.pile[-1]
        if card[0] == top[0] or card[1] == top[1]:
            self.pile.append(self.hand.pop(idx))
            self.sel = min(self.sel, max(0, len(self.hand) - 1))
            self.message = "Nice!"
            if not self.hand:
                self.message = "YOU WIN!"
        else:
            self.message = "Can't play"
        self.update()

    def digi_nav(self, dx: int, dy: int) -> bool:
        if not self.hand:
            return False
        if dx:
            self.sel = (self.sel + (1 if dx > 0 else -1)) % len(self.hand)
            self.update()
            return True
        return bool(dy)

    def digi_confirm(self):
        if self.hand:
            self.play_index(self.sel)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()
        accent = QColor("#ff6b6b")
        _fill_crt(p, r, accent)
        # discard
        top = self.pile[-1]
        self._card(p, r.width() // 2 - 22, 16, 44, 60, top, big=True)
        p.setPen(_MUTED)
        p.setFont(_font(9))
        p.drawText(QRect(0, 80, r.width(), 14), Qt.AlignCenter, self.message)
        # hand
        n = max(1, len(self.hand))
        cw = min(36, (r.width() - 16) // n)
        total = cw * n
        x0 = (r.width() - total) // 2
        for i, card in enumerate(self.hand):
            self._card(p, x0 + i * cw, 100, cw - 4, 48, card, selected=(i == self.sel))

    def _card(self, p, x, y, w, h, card, selected=False, big=False):
        col, num = card
        base = QColor(_UNO_HEX.get(col, "#888"))
        p.setBrush(base)
        p.setPen(QPen(QColor("#fff") if selected else base.darker(140), 2 if selected else 1))
        p.drawRoundedRect(QRect(x, y, w, h), 6, 6)
        p.setPen(QColor("#101820"))
        p.setFont(_font(16 if big else 11, True))
        p.drawText(QRect(x, y, w, h), Qt.AlignCenter, str(num))


# ── Card game shell (menu + play, no score race) ─────────────────────────────
class CardShell(QWidget):
    def __init__(self, title, tagline, accent, howto, board, controls, on_back, parent=None):
        super().__init__(parent)
        self._on_back = on_back
        self.board = board
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)

        self.splash = SplashPane(title, tagline, accent)
        self.menu = MenuPane(title, tagline, accent, "", howto)

        play = QWidget()
        pl = QVBoxLayout(play)
        pl.setContentsMargins(4, 4, 4, 4)
        pl.setSpacing(4)
        pl.addWidget(board, 1)
        row = QHBoxLayout()
        for b in controls:
            b.setMinimumHeight(30)
            b.setStyleSheet(
                "QPushButton{background:#182230;color:#e8f0ff;border:1px solid #2a3a4c;"
                "border-radius:8px;font-size:10px;padding:4px;}"
                "QPushButton:focus{border:2px solid %s;}" % accent.name()
            )
            row.addWidget(b)
        pl.addLayout(row)
        self.play_page = play

        self.stack.addWidget(self.splash)
        self.stack.addWidget(self.menu)
        self.stack.addWidget(self.play_page)
        self.splash.finished.connect(lambda: self.stack.setCurrentWidget(self.menu))
        self.menu.play.connect(self._to_play)
        self.stack.setCurrentWidget(self.splash)

    def showEvent(self, e):
        super().showEvent(e)
        self.stack.setCurrentWidget(self.splash)

    def _to_play(self):
        if hasattr(self.board, "reset"):
            self.board.reset()
        self.stack.setCurrentWidget(self.play_page)
        self.board.setFocus()

    def digi_nav(self, dx, dy):
        w = self.stack.currentWidget()
        if w is self.play_page and hasattr(self.board, "digi_nav"):
            return bool(self.board.digi_nav(dx, dy))
        if hasattr(w, "digi_nav"):
            return bool(w.digi_nav(dx, dy))
        return False

    def digi_confirm(self):
        w = self.stack.currentWidget()
        if w is self.play_page and hasattr(self.board, "digi_confirm"):
            self.board.digi_confirm()
            return
        if hasattr(w, "digi_confirm"):
            w.digi_confirm()

    def digi_back(self):
        w = self.stack.currentWidget()
        if w is self.play_page:
            self.stack.setCurrentWidget(self.menu)
            self.menu.setFocus()
            return True
        if w is self.splash:
            self.stack.setCurrentWidget(self.menu)
            return True
        if w is self.menu and hasattr(w, "digi_back"):
            return bool(w.digi_back())
        return False


def _wire_game_page(chrome: QWidget, shell: QWidget) -> QWidget:
    """Expose Digivice pad / Back hooks on the page chrome."""
    chrome.game_shell = shell  # type: ignore[attr-defined]

    def on_hardware_back() -> bool:
        return bool(shell.digi_back())

    chrome.on_hardware_back = on_hardware_back  # type: ignore[attr-defined]

    def digi_move_h(delta: int) -> bool:
        return bool(shell.digi_nav(int(delta), 0))

    def digi_move_v(delta: int) -> bool:
        return bool(shell.digi_nav(0, int(delta)))

    def digi_activate() -> bool:
        shell.digi_confirm()
        return True

    def digi_pad_active() -> bool:
        return True

    chrome.digi_move_h = digi_move_h  # type: ignore[attr-defined]
    chrome.digi_move_v = digi_move_v  # type: ignore[attr-defined]
    chrome.digi_activate = digi_activate  # type: ignore[attr-defined]
    chrome.digi_pad_active = digi_pad_active  # type: ignore[attr-defined]
    return chrome


def _wrap_arcade(title, tagline, accent, key, howto, board, on_back):
    shell = ArcadeShell(
        title=title,
        tagline=tagline,
        accent=accent,
        score_key=key,
        howto=howto,
        board=board,
        on_back=on_back,
    )
    return _wire_game_page(page_chrome(title, shell, on_back, scroll=False), shell)


def make_snake(on_back):
    return _wrap_arcade(
        "SNAKE",
        "Classic neon crawl",
        QColor("#3dff9a"),
        "snake",
        "Steer with the D-pad. Eat glowing orbs to grow. Don't hit the walls or yourself. Confirm pauses.",
        SnakeBoard(),
        on_back,
    )


def make_pong(on_back):
    return _wrap_arcade(
        "PONG",
        "First to five · retro court",
        QColor("#5ad1ff"),
        "pong",
        "Move your paddle with ↑↓. Score past the AI. First to miss five times loses. Confirm pauses.",
        PongBoard(),
        on_back,
    )


def make_tetris(on_back):
    return _wrap_arcade(
        "TETRIS",
        "Stack · clear · climb",
        QColor("#c792ea"),
        "tetris",
        "←→ move, ↓ soft drop, ↑ rotate. Clear lines to score. Speed rises with your score. Confirm pauses.",
        TetrisBoard(),
        on_back,
    )


def make_solitaire(on_back):
    board = SolitaireBoard()
    draw = QPushButton("Draw")
    found = QPushButton("Foundation")
    anew = QPushButton("New")
    draw.clicked.connect(board.draw)
    found.clicked.connect(board.to_foundation)
    anew.clicked.connect(board.reset)
    shell = CardShell(
        "SOLITAIRE",
        "Klondike · green felt",
        QColor("#3dff9a"),
        "Confirm draws from the stock. Foundation sends the waste card up if it fits. ←→ pick a tableau column.",
        board,
        [draw, found, anew],
        on_back,
    )
    return _wire_game_page(page_chrome("Solitaire", shell, on_back, scroll=False), shell)


def make_uno(on_back):
    board = UnoBoard()
    draw = QPushButton("Draw")
    play = QPushButton("Play")
    anew = QPushButton("New")
    draw.clicked.connect(board.draw_card)
    play.clicked.connect(lambda: board.play_index(board.sel))
    anew.clicked.connect(board.reset)
    shell = CardShell(
        "UNO",
        "Match color or number",
        QColor("#ff6b6b"),
        "←→ choose a card, Confirm to play it. Must match the discard pile's color or number. Draw if stuck.",
        board,
        [draw, play, anew],
        on_back,
    )
    return _wire_game_page(page_chrome("Uno", shell, on_back, scroll=False), shell)
