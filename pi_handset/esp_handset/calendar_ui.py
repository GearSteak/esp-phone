"""Calendar — calm month glance + day events for Digivice."""

from __future__ import annotations

import calendar as pycal
from datetime import date, timedelta
from typing import Callable, List

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from esp_handset import store
from esp_handset.pages import page_chrome


def _btn(text: str, *, primary: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setFocusPolicy(Qt.StrongFocus)
    b.setCursor(Qt.PointingHandCursor)
    if primary:
        b.setStyleSheet(
            "QPushButton { font-size: 11px; font-weight: 700; padding: 3px 8px;"
            " background:#2a6a4a; border:1px solid #3a8a5a; border-radius:4px; }"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
    else:
        b.setStyleSheet(
            "QPushButton { font-size: 11px; font-weight: 600; padding: 3px 8px;"
            " background:#1a2430; border:1px solid #2a3a4a; border-radius:4px; }"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
    return b


class MonthGrid(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._year = date.today().year
        self._month = date.today().month
        self._selected = date.today()
        self._event_days: set = set()
        self.setFixedHeight(112)
        self.setFocusPolicy(Qt.NoFocus)

    def set_month(self, year: int, month: int) -> None:
        self._year = year
        self._month = month
        d = min(self._selected.day, pycal.monthrange(year, month)[1])
        self._selected = date(year, month, d)
        self.update()

    def set_selected(self, d: date) -> None:
        self._selected = d
        self._year = d.year
        self._month = d.month
        self.update()

    def selected(self) -> date:
        return self._selected

    def set_event_days(self, days: set) -> None:
        self._event_days = set(days)
        self.update()

    def shift_day(self, delta: int) -> None:
        self.set_selected(self._selected + timedelta(days=delta))

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#121820"))

        p.setFont(QFont("DejaVu Sans", 7, QFont.Bold))
        p.setPen(QColor("#5a6a7a"))
        labels = ("M", "T", "W", "T", "F", "S", "S")
        cell_w = w / 7.0
        head_h = 12
        for i, lab in enumerate(labels):
            p.drawText(int(i * cell_w), 0, int(cell_w), head_h, Qt.AlignCenter, lab)

        weeks = pycal.Calendar(firstweekday=0).monthdayscalendar(
            self._year, self._month
        )
        rows = max(len(weeks), 1)
        cell_h = max(14, (h - head_h) / rows)
        today = date.today()

        for r, week in enumerate(weeks):
            for c, day in enumerate(week):
                if day == 0:
                    continue
                x = int(c * cell_w)
                y = int(head_h + r * cell_h)
                cw, ch = int(cell_w), int(cell_h)
                d = date(self._year, self._month, day)
                sel = d == self._selected
                is_today = d == today
                has = day in self._event_days

                if sel:
                    p.setBrush(QColor("#FFE600"))
                    p.setPen(QPen(QColor("#000000"), 1))
                    p.drawRoundedRect(x + 1, y + 1, cw - 3, ch - 3, 3, 3)
                    p.setPen(QColor("#000000"))
                elif is_today:
                    p.setBrush(QColor("#243848"))
                    p.setPen(QPen(QColor("#5a8aaa"), 1))
                    p.drawRoundedRect(x + 1, y + 1, cw - 3, ch - 3, 3, 3)
                    p.setPen(QColor("#e8eef5"))
                else:
                    p.setPen(QColor("#c8d0d8"))

                p.setFont(QFont("DejaVu Sans", 8, QFont.Bold if sel else QFont.Normal))
                p.drawText(x, y, cw, ch - 4, Qt.AlignCenter, str(day))
                if has:
                    p.setBrush(QColor("#000000" if sel else "#5aaa7a"))
                    p.setPen(Qt.NoPen)
                    p.drawEllipse(x + cw // 2 - 2, y + ch - 7, 4, 4)


def make_calendar_page(on_back: Callable[[], None]) -> QWidget:
    del on_back
    body = QWidget()
    root = QVBoxLayout(body)
    root.setContentsMargins(2, 0, 2, 0)
    root.setSpacing(2)

    head = QHBoxLayout()
    head.setSpacing(4)
    prev_btn = _btn("‹")
    prev_btn.setFixedWidth(28)
    next_btn = _btn("›")
    next_btn.setFixedWidth(28)
    month_lab = QLabel("")
    month_lab.setAlignment(Qt.AlignCenter)
    month_lab.setStyleSheet("font-size:12px; font-weight:700; color:#e8eef5;")
    head.addWidget(prev_btn)
    head.addWidget(month_lab, 1)
    head.addWidget(next_btn)
    root.addLayout(head)

    grid = MonthGrid()
    root.addWidget(grid)

    day_nav = QHBoxLayout()
    day_nav.setSpacing(4)
    day_prev = _btn("←")
    day_prev.setFixedWidth(28)
    day_next = _btn("→")
    day_next.setFixedWidth(28)
    day_lab = QLabel("")
    day_lab.setAlignment(Qt.AlignCenter)
    day_lab.setStyleSheet("font-size:10px; color:#8a9aaa; font-weight:600;")
    day_nav.addWidget(day_prev)
    day_nav.addWidget(day_lab, 1)
    day_nav.addWidget(day_next)
    root.addLayout(day_nav)

    lst = QListWidget()
    lst.setFocusPolicy(Qt.StrongFocus)
    lst.setStyleSheet(
        "QListWidget { background:#121820; border:1px solid #1e2a38; border-radius:4px;"
        " font-size:11px; outline:none; }"
        "QListWidget::item { padding:4px 6px; border-bottom:1px solid #1a2430; }"
        "QListWidget::item:selected { background:#243848; color:#e8eef5; }"
        'QListWidget[digiFocus="1"] { border:2px solid #FFE600; }'
    )
    root.addWidget(lst, 1)

    editor = QFrame()
    editor.setStyleSheet(
        "QFrame { background:#182028; border:1px solid #2a3a4a; border-radius:4px; }"
    )
    e_lay = QVBoxLayout(editor)
    e_lay.setContentsMargins(5, 3, 5, 3)
    e_lay.setSpacing(2)
    title_in = QLineEdit()
    title_in.setPlaceholderText("Event title")
    title_in.setStyleSheet("font-size:11px; padding:3px;")
    e_lay.addWidget(title_in)
    e_row = QHBoxLayout()
    save_btn = _btn("Save", primary=True)
    cancel_btn = _btn("Cancel")
    e_row.addWidget(save_btn)
    e_row.addWidget(cancel_btn)
    e_lay.addLayout(e_row)
    editor.hide()
    root.addWidget(editor)

    row = QHBoxLayout()
    row.setSpacing(4)
    add_btn = _btn("＋ Add", primary=True)
    del_btn = _btn("Del")
    today_btn = _btn("Today")
    row.addWidget(add_btn)
    row.addWidget(del_btn)
    row.addWidget(today_btn)
    root.addLayout(row)

    state = {"edit": False}

    def _events() -> List[dict]:
        return list(store.load("calendar.json", []))

    def _iso(d: date) -> str:
        return d.isoformat()

    def _refresh_labels() -> None:
        d = grid.selected()
        month_lab.setText(d.strftime("%b %Y"))
        day_lab.setText(d.strftime("%a") + f" {d.day}")

    def _event_days_in_month() -> set:
        y, m = grid._year, grid._month
        days = set()
        for e in _events():
            raw = str(e.get("date", ""))
            try:
                ed = date.fromisoformat(raw[:10])
            except ValueError:
                continue
            if ed.year == y and ed.month == m:
                days.add(ed.day)
        return days

    def refresh_list() -> None:
        d = grid.selected()
        key = _iso(d)
        lst.clear()
        found = False
        for e in sorted(_events(), key=lambda x: (x.get("title") or "").lower()):
            if str(e.get("date", ""))[:10] == key:
                item = QListWidgetItem(e.get("title") or "Event")
                item.setData(Qt.UserRole, e)
                lst.addItem(item)
                found = True
        if not found:
            empty = QListWidgetItem("No events")
            empty.setForeground(QColor("#5a6a7a"))
            empty.setFlags(Qt.NoItemFlags)
            lst.addItem(empty)
        grid.set_event_days(_event_days_in_month())
        _refresh_labels()

    def show_editor(show: bool) -> None:
        state["edit"] = show
        editor.setVisible(show)
        lst.setVisible(not show)
        add_btn.setVisible(not show)
        del_btn.setVisible(not show)
        today_btn.setVisible(not show)
        if show:
            title_in.clear()
            title_in.setFocus(Qt.OtherFocusReason)

    def do_save() -> None:
        title = title_in.text().strip() or "Event"
        events = _events()
        events.append({"date": _iso(grid.selected()), "title": title})
        store.save("calendar.json", events)
        show_editor(False)
        refresh_list()

    def do_del() -> None:
        item = lst.currentItem()
        if item is None:
            return
        target = item.data(Qt.UserRole)
        if not isinstance(target, dict):
            return
        store.save("calendar.json", [e for e in _events() if e != target])
        refresh_list()

    def shift_month(delta: int) -> None:
        y, m = grid._year, grid._month + delta
        while m < 1:
            m += 12
            y -= 1
        while m > 12:
            m -= 12
            y += 1
        grid.set_month(y, m)
        refresh_list()

    prev_btn.clicked.connect(lambda: shift_month(-1))
    next_btn.clicked.connect(lambda: shift_month(1))
    day_prev.clicked.connect(lambda: (grid.shift_day(-1), refresh_list()))
    day_next.clicked.connect(lambda: (grid.shift_day(1), refresh_list()))
    add_btn.clicked.connect(lambda: show_editor(True))
    cancel_btn.clicked.connect(lambda: show_editor(False))
    save_btn.clicked.connect(do_save)
    del_btn.clicked.connect(do_del)
    today_btn.clicked.connect(lambda: (grid.set_selected(date.today()), refresh_list()))

    refresh_list()
    return page_chrome("Calendar", body, None, scroll=False)
