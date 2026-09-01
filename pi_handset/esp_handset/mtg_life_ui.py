"""Four-player Magic: The Gathering life counter for the Digivice."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QWidget

from esp_handset import store
from esp_handset.ui_font import font_family

_BACKGROUND = Path(__file__).resolve().parents[1] / "Assets" / "mtg_life_background.png"
_SEGMENT_FONT = Path(__file__).resolve().parents[1] / "Assets" / "SevenSegment.ttf"
_SEGMENT_FAMILY: Optional[str] = None
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


def _segment_family() -> str:
    global _SEGMENT_FAMILY
    if _SEGMENT_FAMILY:
        return _SEGMENT_FAMILY
    if _SEGMENT_FONT.is_file():
        font_id = QFontDatabase.addApplicationFont(str(_SEGMENT_FONT))
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                _SEGMENT_FAMILY = families[0]
                return _SEGMENT_FAMILY
    return font_family()


def _segment_font(pixels: int) -> QFont:
    font = QFont(_segment_family())
    font.setPixelSize(max(8, pixels))
    return font


_LCD_INK = QColor("#202719")
_GHOST_ALPHA = 42
_GHOST_ALPHA_FAINT = 28


def _ghost_color(ink: Optional[QColor] = None, alpha: int = _GHOST_ALPHA) -> QColor:
    color = QColor(ink or _LCD_INK)
    color.setAlpha(alpha)
    return color


def _digit_ghost(width: int = 3) -> str:
    return "0" * max(1, width)


def _text_ghost(text: str) -> str:
    """LCD placeholder — every segment position lit dimly (8 for alnum)."""
    out: List[str] = []
    for ch in text:
        if ch.isdigit():
            out.append("8")
        elif ch.isalpha():
            out.append("8")
        else:
            out.append(ch)
    return "".join(out)


def _draw_ghosted_text(
    painter: QPainter,
    rect: QRect,
    text: str,
    *,
    align: int = Qt.AlignCenter,
    ghost: Optional[str] = None,
    ink: Optional[QColor] = None,
    ghost_alpha: int = _GHOST_ALPHA,
    font_px: Optional[int] = None,
) -> None:
    ink = ink or _LCD_INK
    px = font_px or max(8, rect.height())
    painter.setFont(_segment_font(px))
    ghost_text = ghost if ghost is not None else _text_ghost(text)
    painter.setPen(_ghost_color(ink, ghost_alpha))
    painter.drawText(rect, align, ghost_text)
    painter.setPen(ink)
    painter.drawText(rect, align, text)


def _draw_ghost_only(
    painter: QPainter,
    rect: QRect,
    text: str,
    *,
    align: int = Qt.AlignCenter,
    ghost: Optional[str] = None,
    ink: Optional[QColor] = None,
    ghost_alpha: int = _GHOST_ALPHA_FAINT,
    font_px: Optional[int] = None,
) -> None:
    px = font_px or max(8, rect.height())
    painter.setFont(_segment_font(px))
    painter.setPen(_ghost_color(ink, ghost_alpha))
    painter.drawText(rect, align, ghost if ghost is not None else _text_ghost(text))


def _draw_ghosted_digits(
    painter: QPainter,
    rect: QRect,
    text: str,
    *,
    ghost: str = "000",
    ink: Optional[QColor] = None,
    ghost_alpha: int = _GHOST_ALPHA,
    font_px: Optional[int] = None,
) -> None:
    ink = ink or _LCD_INK
    px = font_px or max(12, rect.height() // 2)
    painter.setFont(_segment_font(px))
    painter.setPen(_ghost_color(ink, ghost_alpha))
    painter.drawText(rect, Qt.AlignCenter, ghost)
    painter.setPen(ink)
    painter.drawText(rect, Qt.AlignCenter, text)


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
        try:
            origin = self._draw_background(painter)
            if self._mode in ("players", "menu", "damage"):
                self._draw_center_lcd_ghost(painter, origin)
            if self._mode in ("resume", "setup"):
                self._draw_center_lcd_ghost(painter, origin)
                self._draw_setup(painter, origin)
            elif self._mode == "players":
                self._draw_players(painter, origin)
            elif self._mode == "menu":
                self._draw_players(painter, origin)
                self._draw_counter_menu(painter, origin)
            elif self._mode == "damage":
                self._draw_players(painter, origin)
                self._draw_damage_menu(painter, origin)
        except Exception as e:
            print(f"[mtg] paint error: {e}", flush=True)
            traceback.print_exc()
            painter.fillRect(self.rect(), QColor("#969a79"))
            painter.setPen(QColor("#202719"))
            painter.setFont(QFont("Sans", 10, QFont.Bold))
            message = str(e).replace("\n", " ")[:100]
            painter.drawText(
                self.rect().adjusted(8, 8, -8, -8),
                Qt.AlignCenter,
                f"MTG DISPLAY ERROR\n{message}",
            )
        painter.end()

    def _lcd_font(self, pixels: int, bold: bool = False) -> QFont:
        font = _segment_font(pixels)
        font.setBold(bold)
        return font

    def _draw_ghosted_text(
        self,
        painter: QPainter,
        rect: QRect,
        text: str,
        *,
        align: int = Qt.AlignCenter,
        ghost: Optional[str] = None,
        ink: Optional[QColor] = None,
        ghost_alpha: int = _GHOST_ALPHA,
        font_px: Optional[int] = None,
    ) -> None:
        _draw_ghosted_text(
            painter,
            rect,
            text,
            align=align,
            ghost=ghost,
            ink=ink,
            ghost_alpha=ghost_alpha,
            font_px=font_px,
        )

    def _draw_ghosted_digits(
        self,
        painter: QPainter,
        rect: QRect,
        text: str,
        *,
        ghost: str = "000",
        ink: Optional[QColor] = None,
        ghost_alpha: int = _GHOST_ALPHA,
        font_px: Optional[int] = None,
    ) -> None:
        _draw_ghosted_digits(
            painter,
            rect,
            text,
            ghost=ghost,
            ink=ink,
            ghost_alpha=ghost_alpha,
            font_px=font_px,
        )

    def _counter_menu_layout(self, rect: QRect) -> tuple:
        title_height = max(14, rect.height() // 6)
        row_height = max(14, (rect.height() - title_height) // 4)
        return title_height, row_height

    def _draw_center_lcd_ghost(self, painter: QPainter, origin: tuple) -> None:
        """Dim full LCD template — menus, hints, digits always etched on screen."""
        rect = self._menu_rect(origin)
        title_h, row_h = self._counter_menu_layout(rect)
        title_font = max(9, rect.height() // 12)
        row_font = max(9, row_h - 2)
        digit_font = max(10, row_h - 2)
        ghost = _GHOST_ALPHA_FAINT

        _draw_ghost_only(
            painter,
            QRect(rect.left() + 6, rect.top() + 2, rect.width() - 12, title_h),
            f"P{self._player + 1} COUNTERS",
            font_px=title_font,
            ghost_alpha=ghost,
        )
        for index, label in enumerate(_COUNTERS):
            row = QRect(
                rect.left() + 8,
                rect.top() + title_h + row_h * index,
                rect.width() - 16,
                row_h,
            )
            _draw_ghost_only(
                painter,
                QRect(row.left(), row.top(), row.width() // 2, row.height()),
                label[:9],
                align=Qt.AlignVCenter | Qt.AlignLeft,
                font_px=row_font,
                ghost_alpha=ghost,
            )
            _draw_ghost_only(
                painter,
                QRect(
                    row.left() + row.width() // 2,
                    row.top(),
                    row.width() // 2 - 4,
                    row.height(),
                ),
                _digit_ghost(3),
                ghost=_digit_ghost(3),
                font_px=digit_font,
                ghost_alpha=ghost,
            )

        dmg_top = rect.top() + title_h + row_h * 4 + 4
        dmg_title_h = max(12, row_h)
        _draw_ghost_only(
            painter,
            QRect(rect.left() + 5, dmg_top, rect.width() - 10, dmg_title_h),
            "COMMANDER DAMAGE",
            font_px=title_font,
            ghost_alpha=ghost,
        )
        for index in range(3):
            row = QRect(
                rect.left() + 8,
                dmg_top + dmg_title_h + index * row_h,
                rect.width() - 16,
                row_h,
            )
            _draw_ghost_only(
                painter,
                QRect(row.left(), row.top(), row.width() // 2, row.height()),
                f"P{index + 1}",
                align=Qt.AlignVCenter | Qt.AlignLeft,
                font_px=row_font,
                ghost_alpha=ghost,
            )
            _draw_ghost_only(
                painter,
                QRect(
                    row.left() + row.width() // 2,
                    row.top(),
                    row.width() // 2 - 4,
                    row.height(),
                ),
                _digit_ghost(3),
                ghost=_digit_ghost(3),
                font_px=digit_font,
                ghost_alpha=ghost,
            )

        hints = (
            "RESUME GAME?",
            "RESUME",
            "NEW GAME",
            "↑↓ DIGIT  ←→ CHANGE",
            "OK STARTS GAME",
        )
        hint_h = max(7, rect.height() // 18)
        hint_y = rect.bottom() - len(hints) * hint_h - 4
        for line in hints:
            _draw_ghost_only(
                painter,
                QRect(rect.left() + 6, hint_y, rect.width() - 12, hint_h),
                line,
                font_px=hint_h,
                ghost_alpha=ghost,
            )
            hint_y += hint_h

    def _draw_players(self, painter: QPainter, origin: tuple) -> None:
        if self._match is None:
            return
        boxes = (
            (48, 74, 224, 177),
            (752, 74, 224, 177),
            (48, 526, 224, 177),
            (752, 526, 224, 177),
        )
        # Ghost all four life slots first (LCD always shows digit positions)
        for box in boxes:
            rect = self._image_rect(origin, box)
            _draw_ghost_only(
                painter,
                rect,
                _digit_ghost(3),
                ghost=_digit_ghost(3),
                font_px=max(18, rect.height() // 2),
                ghost_alpha=_GHOST_ALPHA_FAINT,
            )
        for index, box in enumerate(boxes):
            rect = self._image_rect(origin, box)
            if index == self._player:
                painter.setPen(QPen(QColor("#d7db9d"), max(1, rect.width() // 28)))
                painter.setBrush(QColor(210, 220, 150, 55))
                painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 3, 3)
            life = self._match["players"][index]["life"]
            display = str(life) if life < 0 else f"{life:03d}"
            self._draw_ghosted_digits(
                painter,
                rect,
                display,
                ghost=_digit_ghost(3),
                font_px=max(18, rect.height() // 2),
            )

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
        title_height, row_height = self._counter_menu_layout(rect)
        title = QRect(
            rect.left() + 6, rect.top() + 2, rect.width() - 12, title_height
        )
        self._draw_ghosted_text(
            painter,
            title,
            f"P{self._player + 1} COUNTERS",
            font_px=max(9, rect.height() // 12),
        )
        for index, (label, value) in enumerate(zip(_COUNTERS, values)):
            row = QRect(
                rect.left() + 8,
                rect.top() + title_height + row_height * index,
                rect.width() - 16,
                row_height,
            )
            if index == self._menu_index:
                painter.fillRect(row, QColor(45, 55, 34, 95))
            label_rect = QRect(row.left(), row.top(), row.width() // 2, row.height())
            self._draw_ghosted_text(
                painter,
                label_rect,
                label[:9],
                align=Qt.AlignVCenter | Qt.AlignLeft,
                font_px=max(9, row_height - 2),
            )
            value_rect = QRect(
                row.left() + row.width() // 2,
                row.top(),
                row.width() // 2 - 4,
                row.height(),
            )
            if index == 0 and value < 0:
                display = str(value)
            else:
                display = f"{value:03d}"
            self._draw_ghosted_digits(
                painter,
                value_rect,
                display,
                ghost=_digit_ghost(3),
                font_px=max(10, row_height - 2),
            )

    def _draw_damage_menu(self, painter: QPainter, origin: tuple) -> None:
        rect = self._menu_rect(origin)
        self._draw_panel(painter, rect)
        player = self._player_data()
        opponents = self._opponents()
        title_height = max(16, rect.height() // 5)
        row_height = max(16, (rect.height() - title_height) // 3)
        title = QRect(
            rect.left() + 5, rect.top() + 2, rect.width() - 10, title_height
        )
        self._draw_ghosted_text(
            painter,
            title,
            "COMMANDER DAMAGE",
            font_px=max(9, rect.height() // 11),
        )
        for index, opponent in enumerate(opponents):
            row = QRect(
                rect.left() + 8,
                rect.top() + title_height + index * row_height,
                rect.width() - 16,
                row_height,
            )
            if opponent == self._opponent_index:
                painter.fillRect(row, QColor(45, 55, 34, 95))
            label_rect = QRect(row.left(), row.top(), row.width() // 2, row.height())
            self._draw_ghosted_text(
                painter,
                label_rect,
                f"P{opponent + 1}",
                align=Qt.AlignVCenter | Qt.AlignLeft,
                font_px=max(10, row_height // 2),
            )
            damage = player["commander_damage"][opponent]
            damage_rect = QRect(
                row.left() + row.width() // 2,
                row.top(),
                row.width() // 2 - 4,
                row.height(),
            )
            self._draw_ghosted_digits(
                painter,
                damage_rect,
                f"{damage:03d}",
                ghost=_digit_ghost(3),
                font_px=max(10, row_height // 2),
            )

    def _draw_setup(self, painter: QPainter, origin: tuple) -> None:
        rect = self._menu_rect(origin)
        self._draw_panel(painter, rect)
        ink = _LCD_INK
        if self._mode == "resume":
            title_rect = QRect(rect.left() + 5, rect.top() + 3, rect.width() - 10, 17)
            self._draw_ghosted_text(
                painter,
                title_rect,
                "RESUME GAME?",
                font_px=max(10, rect.height() // 10),
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
                self._draw_ghosted_text(
                    painter,
                    row,
                    option,
                    font_px=max(10, rect.height() // 10),
                )
            return
        title_rect = QRect(rect.left() + 5, rect.top() + 3, rect.width() - 10, 17)
        self._draw_ghosted_text(
            painter,
            title_rect,
            "NEW GAME",
            font_px=max(10, rect.height() // 10),
        )
        digits = f"{self._setup_value:03d}"
        digit_rect = QRect(rect.left() + 8, rect.top() + 20, rect.width() - 16, 35)
        self._draw_ghosted_digits(
            painter,
            digit_rect,
            digits,
            ghost=_digit_ghost(3),
            font_px=max(22, rect.height() // 4),
        )
        digit_width = max(12, rect.width() // 5)
        x = int(
            rect.center().x()
            - digit_width * 1.5
            + self._setup_digit * digit_width
        )
        painter.setPen(QPen(ink, 2))
        painter.drawLine(x, rect.top() + 56, x + digit_width - 4, rect.top() + 56)
        hint1 = QRect(rect.left() + 6, rect.top() + 59, rect.width() - 12, 12)
        hint2 = QRect(rect.left() + 6, rect.top() + 72, rect.width() - 12, 12)
        self._draw_ghosted_text(
            painter,
            hint1,
            "↑↓ DIGIT  ←→ CHANGE",
            font_px=max(8, rect.height() // 16),
        )
        self._draw_ghosted_text(
            painter,
            hint2,
            "OK STARTS GAME",
            font_px=max(8, rect.height() // 16),
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
        ink = QColor("#202719")
        try:
            painter.fillRect(self.rect(), QColor("#969a79"))
            painter.setPen(ink)
            title_rect = self.rect().adjusted(8, 16, -8, -self.height() // 2)
            _draw_ghosted_text(
                painter,
                title_rect,
                "MTG STARTING LIFE",
                ink=ink,
                font_px=max(14, self.height() // 12),
            )
            value_rect = self.rect().adjusted(
                8, self.height() // 4, -8, -self.height() // 3
            )
            digits = f"{self._value:03d}"
            _draw_ghosted_digits(
                painter,
                value_rect,
                digits,
                ghost=_digit_ghost(3),
                ink=ink,
                font_px=max(28, self.height() // 5),
            )
            painter.setPen(QPen(ink, 2))
            span = max(18, self.width() // 7)
            x = int(self.width() // 2 - span * 1.5 + self._digit * span)
            painter.drawLine(
                x,
                self.height() // 2 + 12,
                x + span - 4,
                self.height() // 2 + 12,
            )
            hint_rect = self.rect().adjusted(8, self.height() // 2 + 25, -8, -12)
            _draw_ghosted_text(
                painter,
                hint_rect,
                "↑↓ DIGIT   ←→ CHANGE   BACK SAVE",
                ink=ink,
                font_px=max(9, self.height() // 22),
            )
        except Exception as e:
            print(f"[mtg] settings paint error: {e}", flush=True)
            traceback.print_exc()
            painter.fillRect(self.rect(), QColor("#969a79"))
            painter.setPen(QColor("#202719"))
            painter.setFont(QFont("Sans", 10, QFont.Bold))
            message = str(e).replace("\n", " ")[:100]
            painter.drawText(
                self.rect().adjusted(8, 8, -8, -8),
                Qt.AlignCenter,
                f"MTG SETTINGS ERROR\n{message}",
            )
        painter.end()


def make_mtg_life_page(on_back: Callable[[], None]) -> QWidget:
    return MtgLifeCounter(on_back)


def make_mtg_settings_page(on_back: Callable[[], None]) -> QWidget:
    return MtgSettingsPage(on_back)
