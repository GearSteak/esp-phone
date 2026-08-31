"""Four-player Magic: The Gathering life counter for the Digivice."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional

from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QWidget

from esp_handset import store
from esp_handset.ui_font import font_family

_BACKGROUND = Path(__file__).resolve().parents[1] / "Assets" / "mtg_life_background.png"
_MATCH_FILE = "mtg_life.json"
_SETTINGS_FILE = "mtg_life_settings.json"
_PLAYER_COUNT = 4
_MAX_COUNTER = 999
_MIN_LIFE = -999
_MAX_LIFE = 999
_COUNTERS = ("Life", "Commander Damage", "Commander Tax", "Poison")


def _clamp(value: int, low: int = 0, high: int = _MAX_COUNTER) -> int:
    return max(low, min(high, int(value)))


def _default_life() -> int:
    raw = store.load(_SETTINGS_FILE, {"starting_life": 40})
    try:
        return _clamp(int(raw.get("starting_life", 40)))
    except (AttributeError, TypeError, ValueError):
        return 40


def _new_match(starting_life: int) -> Dict[str, object]:
    players: List[dict] = []
    for _ in range(_PLAYER_COUNT):
        players.append(
            {
                "life": _clamp(starting_life, 0, _MAX_LIFE),
                "tax": 0,
                "poison": 0,
                "commander_damage": [0] * _PLAYER_COUNT,
            }
        )
    return {"version": 1, "players": players}


def _valid_match(raw) -> Optional[Dict[str, object]]:
    if not isinstance(raw, dict) or not isinstance(raw.get("players"), list):
        return None
    source = raw["players"]
    if len(source) != _PLAYER_COUNT:
        return None
    players: List[dict] = []
    try:
        for item in source:
            if not isinstance(item, dict):
                return None
            damage = item.get("commander_damage", [0] * _PLAYER_COUNT)
            if not isinstance(damage, list) or len(damage) != _PLAYER_COUNT:
                return None
            players.append(
                {
                    "life": max(_MIN_LIFE, min(_MAX_LIFE, int(item.get("life", 40)))),
                    "tax": _clamp(item.get("tax", 0)),
                    "poison": _clamp(item.get("poison", 0)),
                    "commander_damage": [_clamp(value) for value in damage],
                }
            )
    except (TypeError, ValueError):
        return None
    return {"version": 1, "players": players}


class MtgLifeCounter(QWidget):
    """LCD-style counter page with a hard-button navigation state machine."""

    def __init__(self, on_back: Callable[[], None], parent=None):
        super().__init__(parent)
        self._on_back = on_back
        self.setProperty("digiTitle", "MTG Life")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(240, 180)
        self._background = QPixmap(str(_BACKGROUND))
        self._match: Optional[Dict[str, object]] = None
        self._player = 0
        self._menu_index = 0
        self._opponent_index = 0
        self._setup_digit = 1
        self._setup_value = _default_life()
        self._resume_index = 0
        self._mode = "resume" if _valid_match(store.load(_MATCH_FILE, {})) else "setup"
        self._saved_match = _valid_match(store.load(_MATCH_FILE, {}))
        self.setFocus()

    def on_page_show(self) -> None:
        self.setFocus(Qt.OtherFocusReason)

    def _feedback(self, kind: str) -> None:
        try:
            from esp_handset.buzzer import beep_async

            beep_async(kind)
        except Exception:
            pass

    def on_hardware_back(self) -> bool:
        self._feedback("chirp")
        if self._mode == "players":
            self._save()
            self._on_back()
            return True
        if self._mode == "menu":
            self._mode = "players"
        elif self._mode == "damage":
            self._mode = "menu"
        elif self._mode == "setup":
            self._mode = "resume" if self._saved_match is not None else "players"
        else:
            self._on_back()
            return True
        self.update()
        return True

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key_Escape, Qt.Key_Backspace):
            self.on_hardware_back()
            event.accept()
            return
        if key in (
            Qt.Key_Up,
            Qt.Key_Down,
            Qt.Key_Left,
            Qt.Key_Right,
        ):
            self._feedback("nav")
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            self._feedback("chirp")
        if self._mode == "resume":
            self._resume_key(key)
        elif self._mode == "setup":
            self._setup_key(key)
        elif self._mode == "players":
            self._players_key(key)
        elif self._mode == "menu":
            self._menu_key(key)
        elif self._mode == "damage":
            self._damage_key(key)
        event.accept()

    def _resume_key(self, key: int) -> None:
        if key in (Qt.Key_Up, Qt.Key_Down):
            self._resume_index = 1 - self._resume_index
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            if self._resume_index == 0 and self._saved_match is not None:
                self._match = self._saved_match
                self._mode = "players"
            else:
                self._mode = "setup"
                self._setup_value = _default_life()
                self._setup_digit = 1
        self.update()

    def _setup_key(self, key: int) -> None:
        if key == Qt.Key_Up:
            self._setup_digit = max(0, self._setup_digit - 1)
        elif key == Qt.Key_Down:
            self._setup_digit = min(2, self._setup_digit + 1)
        elif key in (Qt.Key_Left, Qt.Key_Right):
            delta = -1 if key == Qt.Key_Left else 1
            place = 10 ** (2 - self._setup_digit)
            digit = (self._setup_value // place) % 10
            digit = (digit + delta) % 10
            self._setup_value += (digit - (self._setup_value // place) % 10) * place
            self._setup_value = _clamp(self._setup_value)
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            self._match = _new_match(self._setup_value)
            self._save()
            self._mode = "players"
        self.update()

    def _players_key(self, key: int) -> None:
        row, column = divmod(self._player, 2)
        if key == Qt.Key_Left:
            column = (column - 1) % 2
        elif key == Qt.Key_Right:
            column = (column + 1) % 2
        elif key == Qt.Key_Up:
            row = (row - 1) % 2
        elif key == Qt.Key_Down:
            row = (row + 1) % 2
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            self._mode = "menu"
            self._menu_index = 0
        else:
            return
        self._player = row * 2 + column
        self.update()

    def _menu_key(self, key: int) -> None:
        if key == Qt.Key_Up:
            self._menu_index = (self._menu_index - 1) % len(_COUNTERS)
        elif key == Qt.Key_Down:
            self._menu_index = (self._menu_index + 1) % len(_COUNTERS)
        elif key in (Qt.Key_Left, Qt.Key_Right):
            self._adjust_counter(-1 if key == Qt.Key_Left else 1)
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            if self._menu_index == 1:
                self._opponent_index = self._first_opponent()
                self._mode = "damage"
        self.update()

    def _damage_key(self, key: int) -> None:
        opponents = self._opponents()
        if key == Qt.Key_Up:
            index = opponents.index(self._opponent_index)
            self._opponent_index = opponents[(index - 1) % len(opponents)]
        elif key == Qt.Key_Down:
            index = opponents.index(self._opponent_index)
            self._opponent_index = opponents[(index + 1) % len(opponents)]
        elif key in (Qt.Key_Left, Qt.Key_Right):
            player = self._player_data()
            damage = player["commander_damage"]
            change = -1 if key == Qt.Key_Left else 1
            damage[self._opponent_index] = _clamp(
                damage[self._opponent_index] + change
            )
            self._save()
        self.update()

    def _adjust_counter(self, change: int) -> None:
        player = self._player_data()
        if self._menu_index == 0:
            player["life"] = max(_MIN_LIFE, min(_MAX_LIFE, player["life"] + change))
        elif self._menu_index == 2:
            player["tax"] = _clamp(player["tax"] + change * 2)
        elif self._menu_index == 3:
            player["poison"] = _clamp(player["poison"] + change)
        else:
            return
        self._save()

    def _player_data(self) -> dict:
        if self._match is None:
            self._match = _new_match(_default_life())
        return self._match["players"][self._player]

    def _opponents(self) -> List[int]:
        return [index for index in range(_PLAYER_COUNT) if index != self._player]

    def _first_opponent(self) -> int:
        return self._opponents()[0]

    def _save(self) -> None:
        if self._match is not None:
            store.save(_MATCH_FILE, self._match)

    def _draw_background(self, painter: QPainter) -> tuple:
        painter.fillRect(self.rect(), QColor("#969a79"))
        if self._background.isNull():
            return 0, 0, self.width(), self.height()
        scaled = self._background.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.FastTransformation
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        return x, y, scaled.width(), scaled.height()

    def _image_rect(self, origin: tuple, rect: tuple) -> QRect:
        ox, oy, width, height = origin
        return QRect(
            ox + int(rect[0] * width / 1024),
            oy + int(rect[1] * height / 768),
            max(1, int(rect[2] * width / 1024)),
            max(1, int(rect[3] * height / 768)),
        )

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        origin = self._draw_background(painter)
        if self._mode in ("resume", "setup"):
            self._draw_setup(painter, origin)
        elif self._mode == "players":
            self._draw_players(painter, origin)
        elif self._mode == "menu":
            self._draw_players(painter, origin)
            self._draw_counter_menu(painter, origin)
        elif self._mode == "damage":
            self._draw_players(painter, origin)
            self._draw_damage_menu(painter, origin)
        painter.end()

    def _lcd_font(self, pixels: int, bold: bool = False) -> QFont:
        font = QFont(font_family())
        font.setPixelSize(max(8, pixels))
        font.setBold(bold)
        return font

    def _draw_players(self, painter: QPainter, origin: tuple) -> None:
        if self._match is None:
            return
        boxes = (
            (48, 74, 224, 177),
            (752, 74, 224, 177),
            (48, 526, 224, 177),
            (752, 526, 224, 177),
        )
        ink = QColor("#202719")
        for index, box in enumerate(boxes):
            rect = self._image_rect(origin, box)
            if index == self._player:
                painter.setPen(QPen(QColor("#d7db9d"), max(1, rect.width() // 28)))
                painter.setBrush(QColor(210, 220, 150, 55))
                painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 3, 3)
            painter.setPen(ink)
            painter.setFont(self._lcd_font(max(12, rect.height() // 3), True))
            value = str(self._match["players"][index]["life"])
            painter.drawText(rect, Qt.AlignCenter, value)

    def _menu_rect(self, origin: tuple) -> QRect:
        ox, oy, width, height = origin
        return QRect(
            ox + int(325 * width / 1024),
            oy + int(230 * height / 768),
            max(80, int(375 * width / 1024)),
            max(80, int(310 * height / 768)),
        )

    def _draw_panel(self, painter: QPainter, rect: QRect) -> None:
        painter.setPen(QPen(QColor("#202719"), max(1, rect.width() // 90)))
        painter.setBrush(QColor(185, 192, 151, 238))
        painter.drawRoundedRect(rect, 5, 5)

    def _draw_counter_menu(self, painter: QPainter, origin: tuple) -> None:
        rect = self._menu_rect(origin)
        self._draw_panel(painter, rect)
        player = self._player_data()
        values = [
            player["life"],
            sum(player["commander_damage"]),
            player["tax"],
            player["poison"],
        ]
        painter.setPen(QColor("#202719"))
        painter.setFont(self._lcd_font(max(9, rect.height() // 12), True))
        title_height = max(14, rect.height() // 6)
        row_height = max(14, (rect.height() - title_height) // 4)
        title = QRect(
            rect.left() + 6, rect.top() + 2, rect.width() - 12, title_height
        )
        painter.drawText(title, Qt.AlignCenter, f"P{self._player + 1} COUNTERS")
        for index, (label, value) in enumerate(zip(_COUNTERS, values)):
            row = QRect(
                rect.left() + 8,
                rect.top() + title_height + row_height * index,
                rect.width() - 16,
                row_height,
            )
            if index == self._menu_index:
                painter.fillRect(row, QColor(45, 55, 34, 95))
            painter.drawText(
                row,
                Qt.AlignVCenter | Qt.AlignLeft,
                f"{label[:9]:<9} {value:>4}",
            )

    def _draw_damage_menu(self, painter: QPainter, origin: tuple) -> None:
        rect = self._menu_rect(origin)
        self._draw_panel(painter, rect)
        player = self._player_data()
        opponents = self._opponents()
        painter.setPen(QColor("#202719"))
        painter.setFont(self._lcd_font(max(9, rect.height() // 11), True))
        title_height = max(16, rect.height() // 5)
        title = QRect(
            rect.left() + 5, rect.top() + 2, rect.width() - 10, title_height
        )
        painter.drawText(title, Qt.AlignCenter, "COMMANDER DAMAGE")
        row_height = max(16, (rect.height() - title_height) // 3)
        painter.setFont(self._lcd_font(max(10, row_height // 2), True))
        for index, opponent in enumerate(opponents):
            row = QRect(
                rect.left() + 8,
                rect.top() + title_height + index * row_height,
                rect.width() - 16,
                row_height,
            )
            if opponent == self._opponent_index:
                painter.fillRect(row, QColor(45, 55, 34, 95))
            damage = player["commander_damage"][opponent]
            painter.drawText(row, Qt.AlignVCenter | Qt.AlignLeft, f"P{opponent + 1}")
            painter.drawText(row, Qt.AlignVCenter | Qt.AlignRight, f"{damage:03d}")

    def _draw_setup(self, painter: QPainter, origin: tuple) -> None:
        rect = self._menu_rect(origin)
        self._draw_panel(painter, rect)
        painter.setPen(QColor("#202719"))
        painter.setFont(self._lcd_font(max(10, rect.height() // 10), True))
        if self._mode == "resume":
            painter.drawText(
                QRect(rect.left() + 5, rect.top() + 3, rect.width() - 10, 17),
                Qt.AlignCenter,
                "RESUME GAME?",
            )
            options = ("RESUME", "NEW GAME")
            for index, option in enumerate(options):
                row = QRect(
                    rect.left() + 10,
                    rect.top() + 23 + index * 25,
                    rect.width() - 20,
                    21,
                )
                if index == self._resume_index:
                    painter.fillRect(row, QColor(45, 55, 34, 95))
                painter.drawText(row, Qt.AlignCenter, option)
            return
        painter.drawText(
            QRect(rect.left() + 5, rect.top() + 3, rect.width() - 10, 17),
            Qt.AlignCenter,
            "NEW GAME",
        )
        painter.setFont(self._lcd_font(max(22, rect.height() // 4), True))
        digits = f"{self._setup_value:03d}"
        painter.drawText(
            QRect(rect.left() + 8, rect.top() + 20, rect.width() - 16, 35),
            Qt.AlignCenter,
            digits,
        )
        digit_width = max(12, rect.width() // 5)
        x = rect.center().x() - digit_width * 1.5 + self._setup_digit * digit_width
        painter.setPen(QPen(QColor("#202719"), 2))
        painter.drawLine(x, rect.top() + 56, x + digit_width - 4, rect.top() + 56)
        painter.setFont(self._lcd_font(max(8, rect.height() // 16)))
        painter.drawText(
            QRect(rect.left() + 6, rect.top() + 59, rect.width() - 12, 12),
            Qt.AlignCenter,
            "↑↓ DIGIT  ←→ CHANGE",
        )
        painter.drawText(
            QRect(rect.left() + 6, rect.top() + 72, rect.width() - 12, 12),
            Qt.AlignCenter,
            "OK STARTS GAME",
        )


class MtgSettingsPage(QWidget):
    """Settings page for the default starting life total."""

    def __init__(self, on_back: Callable[[], None], parent=None):
        super().__init__(parent)
        self._on_back = on_back
        self.setProperty("digiTitle", "MTG Defaults")
        self.setFocusPolicy(Qt.StrongFocus)
        self._value = _default_life()
        self._digit = 1
        self.setFocus()

    def on_page_show(self) -> None:
        self.setFocus(Qt.OtherFocusReason)

    def _feedback(self, kind: str) -> None:
        try:
            from esp_handset.buzzer import beep_async

            beep_async(kind)
        except Exception:
            pass

    def on_hardware_back(self) -> bool:
        self._feedback("chirp")
        self._save()
        self._on_back()
        return True

    def _save(self) -> None:
        store.save(_SETTINGS_FILE, {"starting_life": _clamp(self._value)})

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key_Escape, Qt.Key_Backspace):
            self._feedback("chirp")
            self.on_hardware_back()
        elif key == Qt.Key_Up:
            self._feedback("nav")
            self._digit = max(0, self._digit - 1)
        elif key == Qt.Key_Down:
            self._feedback("nav")
            self._digit = min(2, self._digit + 1)
        elif key in (Qt.Key_Left, Qt.Key_Right):
            self._feedback("nav")
            place = 10 ** (2 - self._digit)
            digit = (self._value // place) % 10
            digit = (digit + (-1 if key == Qt.Key_Left else 1)) % 10
            self._value += (digit - (self._value // place) % 10) * place
            self._value = _clamp(self._value)
            self._save()
        event.accept()
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#969a79"))
        painter.setPen(QColor("#202719"))
        painter.setFont(QFont(font_family(), max(14, self.height() // 12), QFont.Bold))
        painter.drawText(
            self.rect().adjusted(8, 16, -8, -self.height() // 2),
            Qt.AlignCenter,
            "MTG STARTING LIFE",
        )
        painter.setFont(QFont(font_family(), max(28, self.height() // 5), QFont.Bold))
        painter.drawText(
            self.rect().adjusted(8, self.height() // 4, -8, -self.height() // 3),
            Qt.AlignCenter,
            f"{self._value:03d}",
        )
        painter.setPen(QPen(QColor("#202719"), 2))
        span = max(18, self.width() // 7)
        x = self.width() // 2 - span * 1.5 + self._digit * span
        painter.drawLine(x, self.height() // 2 + 12, x + span - 4, self.height() // 2 + 12)
        painter.setFont(QFont(font_family(), max(9, self.height() // 22)))
        painter.drawText(
            self.rect().adjusted(8, self.height() // 2 + 25, -8, -12),
            Qt.AlignCenter,
            "↑↓ DIGIT   ←→ CHANGE   BACK SAVE",
        )
        painter.end()


def make_mtg_life_page(on_back: Callable[[], None]) -> QWidget:
    return MtgLifeCounter(on_back)


def make_mtg_settings_page(on_back: Callable[[], None]) -> QWidget:
    return MtgSettingsPage(on_back)
