"""Google Calendar–style month + agenda for Digivice (dark Material)."""

from __future__ import annotations

import calendar as pycal
from datetime import date, timedelta
from typing import Callable, Dict, List, Tuple

from PyQt5.QtCore import Qt, QRectF
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

# Google Calendar–ish dark palette
_BG = "#202124"
_SURFACE = "#303134"
_TEXT = "#e8eaed"
_MUTED = "#9aa0a6"
_BLUE = "#8ab4f8"
_BLUE_DIM = "#394457"
_EVENT_COLORS = ("#7986cb", "#33b679", "#8e24aa", "#e67c73", "#f6bf26", "#039be5")


def _btn(text: str, *, primary: bool = False, fab: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setFocusPolicy(Qt.StrongFocus)
    b.setCursor(Qt.PointingHandCursor)
    if fab:
        b.setFixedSize(36, 36)
        b.setStyleSheet(
            "QPushButton { font-size: 18px; font-weight: 700; color:#202124;"
            " background:#8ab4f8; border:none; border-radius:18px; }"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
    elif primary:
        b.setStyleSheet(
            "QPushButton { font-size: 11px; font-weight: 700; padding: 4px 10px;"
            " color:#202124; background:#8ab4f8; border:none; border-radius:14px; }"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
    else:
        b.setStyleSheet(
            "QPushButton { font-size: 11px; font-weight: 600; padding: 4px 10px;"
            " color:#e8eaed; background:#3c4043; border:none; border-radius:14px; }"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
    return b


def _color_for(title: str) -> str:
    return _EVENT_COLORS[sum(ord(c) for c in (title or "")) % len(_EVENT_COLORS)]


class GCalMonth(QWidget):
    """Month grid: Sunday-first, today blue disc, selected ring, event dots."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._year = date.today().year
        self._month = date.today().month
        self._selected = date.today()
        self._by_day: Dict[int, List[dict]] = {}
        self.setMinimumHeight(168)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setProperty("digiPad", True)
        self.setStyleSheet(f"background:{_BG};")

    def set_month(self, year: int, month: int) -> None:
        self._year = year
        self._month = month
        last = pycal.monthrange(year, month)[1]
        d = min(self._selected.day, last)
        self._selected = date(year, month, d)
        self.update()

    def set_selected(self, d: date) -> None:
        self._selected = d
        self._year, self._month = d.year, d.month
        self.update()

    def selected(self) -> date:
        return self._selected

    def set_events_for_month(self, by_day: Dict[int, List[dict]]) -> None:
        self._by_day = dict(by_day)
        self.update()

    def shift_day(self, delta: int) -> None:
        self.set_selected(self._selected + timedelta(days=delta))

    def paintEvent(self, _event) -> None:  # noqa: N802
        try:
            self._paint()
        except Exception:
            pass

    def _paint(self) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = max(1, self.width()), max(1, self.height())
        p.fillRect(self.rect(), QColor(_BG))

        # Weekday headers (Google US: Sun first)
        p.setFont(QFont("DejaVu Sans", 7, QFont.Bold))
        p.setPen(QColor(_MUTED))
        labels = ("S", "M", "T", "W", "T", "F", "S")
        cell_w = w / 7.0
        head_h = 14
        for i, lab in enumerate(labels):
            p.drawText(int(i * cell_w), 0, int(cell_w), head_h, Qt.AlignCenter, lab)

        cal = pycal.Calendar(firstweekday=6)  # Sunday
        weeks = cal.monthdayscalendar(self._year, self._month)
        rows = max(len(weeks), 1)
        cell_h = max(22.0, (h - head_h) / rows)
        today = date.today()

        for r, week in enumerate(weeks):
            for c, day in enumerate(week):
                if day == 0:
                    continue
                x = c * cell_w
                y = head_h + r * cell_h
                d = date(self._year, self._month, day)
                sel = d == self._selected
                is_today = d == today
                evs = self._by_day.get(day, [])

                cx = x + cell_w / 2
                cy = y + min(10.0, cell_h * 0.35)
                disc_r = min(9.0, max(6.0, cell_w * 0.42))

                # Today / selected disc (Google style)
                if is_today or sel:
                    disc = QRectF(cx - disc_r, cy - disc_r, disc_r * 2, disc_r * 2)
                    if is_today and sel:
                        p.setBrush(QColor(_BLUE))
                        p.setPen(Qt.NoPen)
                        p.drawEllipse(disc)
                        p.setPen(QColor("#202124"))
                    elif is_today:
                        p.setBrush(QColor(_BLUE))
                        p.setPen(Qt.NoPen)
                        p.drawEllipse(disc)
                        p.setPen(QColor("#202124"))
                    else:
                        p.setBrush(Qt.NoBrush)
                        p.setPen(QPen(QColor(_BLUE), 1.5))
                        p.drawEllipse(disc)
                        p.setPen(QColor(_TEXT))
                else:
                    p.setPen(QColor(_TEXT))

                p.setFont(QFont("DejaVu Sans", 7 if cell_w < 22 else 8, QFont.DemiBold))
                p.drawText(
                    int(x),
                    int(y),
                    int(cell_w),
                    int(min(20.0, cell_h * 0.55)),
                    Qt.AlignHCenter | Qt.AlignVCenter,
                    str(day),
                )

                # Event dots under the number
                if evs:
                    dot_y = y + min(cell_h - 6, max(18.0, cell_h * 0.7))
                    n = min(3, len(evs))
                    total = n * 5 + (n - 1) * 2
                    start = cx - total / 2
                    for i in range(n):
                        col = QColor(_color_for(str(evs[i].get("title", ""))))
                        p.setBrush(col)
                        p.setPen(Qt.NoPen)
                        p.drawEllipse(QRectF(start + i * 7, dot_y, 4, 4))


def make_calendar_page(on_back: Callable[[], None]) -> QWidget:
    del on_back
    body = QWidget()
    body.setStyleSheet(f"background:{_BG}; color:{_TEXT};")
    root = QVBoxLayout(body)
    root.setContentsMargins(4, 2, 4, 2)
    root.setSpacing(3)

    # Month chrome
    head = QHBoxLayout()
    head.setSpacing(2)
    prev_btn = _btn("‹")
    prev_btn.setFixedWidth(30)
    next_btn = _btn("›")
    next_btn.setFixedWidth(30)
    month_lab = QLabel("")
    month_lab.setAlignment(Qt.AlignCenter)
    month_lab.setStyleSheet(
        f"font-size:14px; font-weight:700; color:{_TEXT}; letter-spacing:0.3px;"
    )
    head.addWidget(prev_btn)
    head.addWidget(month_lab, 1)
    head.addWidget(next_btn)
    root.addLayout(head)

    grid = GCalMonth()
    from PyQt5.QtWidgets import QScrollArea

    # Month (left) + events sideboard (right) — events never cover the dates
    split = QHBoxLayout()
    split.setSpacing(4)

    grid_scroll = QScrollArea()
    grid_scroll.setWidgetResizable(False)
    grid_scroll.setFrameShape(QFrame.NoFrame)
    grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    grid_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    grid_scroll.setStyleSheet(
        "QScrollArea { background: transparent; border: none; }"
        "QScrollBar:vertical { width: 8px; background: #202124; }"
        "QScrollBar::handle:vertical { background: #5a6570; min-height: 24px; border-radius: 3px; }"
    )
    grid.setFixedWidth(124)
    grid.setMinimumHeight(120)
    grid_scroll.setWidget(grid)

    def _fit_grid() -> None:
        # Never force taller than the viewport — that pushes the bottom bar off-screen
        h = max(120, grid_scroll.viewport().height())
        if grid.height() != h:
            grid.setFixedHeight(h)

    def _on_scroll_resize(ev) -> None:  # noqa: ANN001
        QScrollArea.resizeEvent(grid_scroll, ev)
        _fit_grid()

    grid_scroll.resizeEvent = _on_scroll_resize  # type: ignore[method-assign]
    split.addWidget(grid_scroll, 1)

    right = QWidget()
    right.setFixedWidth(108)
    right_lay = QVBoxLayout(right)
    right_lay.setContentsMargins(0, 0, 0, 0)
    right_lay.setSpacing(0)

    side = QFrame()
    side.setStyleSheet(
        f"QFrame {{ background:{_SURFACE}; border-radius:8px; }}"
    )
    side_lay = QVBoxLayout(side)
    side_lay.setContentsMargins(4, 4, 4, 4)
    side_lay.setSpacing(2)

    agenda_head = QLabel("")
    agenda_head.setWordWrap(True)
    agenda_head.setStyleSheet(
        f"font-size:10px; font-weight:700; color:{_BLUE}; padding:0 1px 2px 1px;"
    )
    side_lay.addWidget(agenda_head)

    lst = QListWidget()
    lst.setFocusPolicy(Qt.StrongFocus)
    lst.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    lst.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    lst.setTextElideMode(Qt.ElideRight)
    lst.setWordWrap(True)
    lst.setStyleSheet(
        f"QListWidget {{ background:transparent; border:none;"
        f" font-size:10px; outline:none; color:{_TEXT}; }}"
        "QListWidget::item { padding:5px 4px; border-bottom:1px solid #3c4043; }"
        f"QListWidget::item:selected {{ background:{_BLUE_DIM}; color:{_TEXT}; }}"
        'QListWidget[digiFocus="1"] { border:2px solid #FFE600; border-radius:6px; }'
        "QScrollBar:horizontal { height: 0px; }"
        "QScrollBar:vertical { width: 8px; background: #202124; }"
        "QScrollBar::handle:vertical { background: #5a6570; min-height: 20px; border-radius: 3px; }"
    )
    side_lay.addWidget(lst, 1)
    right_lay.addWidget(side, 1)

    editor = QFrame()
    editor.setStyleSheet(
        f"QFrame {{ background:{_SURFACE}; border-radius:8px; }}"
    )
    e_lay = QVBoxLayout(editor)
    e_lay.setContentsMargins(6, 6, 6, 6)
    e_lay.setSpacing(4)
    title_in = QLineEdit()
    title_in.setPlaceholderText("Add title")
    title_in.setStyleSheet(
        f"font-size:11px; padding:5px; background:#3c4043; color:{_TEXT};"
        " border:none; border-radius:6px;"
    )
    e_lay.addWidget(title_in)
    e_row = QHBoxLayout()
    e_row.setSpacing(4)
    save_btn = _btn("Save", primary=True)
    cancel_btn = _btn("Cancel")
    e_row.addWidget(save_btn)
    e_row.addWidget(cancel_btn)
    e_lay.addLayout(e_row)
    e_lay.addStretch(1)
    editor.hide()
    right_lay.addWidget(editor, 1)

    split.addWidget(right, 0)
    root.addLayout(split, 1)

    # Bottom bar: day step + actions (Google-ish)
    bar = QHBoxLayout()
    bar.setSpacing(4)
    day_prev = _btn("←")
    day_prev.setFixedWidth(30)
    day_next = _btn("→")
    day_next.setFixedWidth(30)
    today_btn = _btn("Today")
    del_btn = _btn("Del")
    sync_btn = _btn("Sync")
    add_btn = _btn("＋", fab=True)
    bar.addWidget(day_prev)
    bar.addWidget(day_next)
    bar.addWidget(today_btn)
    bar.addWidget(del_btn)
    bar.addWidget(sync_btn)
    bar.addStretch(1)
    bar.addWidget(add_btn)
    root.addLayout(bar)

    state = {"edit": False}

    def _events() -> List[dict]:
        return list(store.load("calendar.json", []))

    def _iso(d: date) -> str:
        return d.isoformat()

    def _month_events() -> Dict[int, List[dict]]:
        y, m = grid._year, grid._month
        out: Dict[int, List[dict]] = {}
        for e in _events():
            raw = str(e.get("date", ""))
            try:
                ed = date.fromisoformat(raw[:10])
            except ValueError:
                continue
            if ed.year == y and ed.month == m:
                out.setdefault(ed.day, []).append(e)
        return out

    def refresh() -> None:
        d = grid.selected()
        month_lab.setText(d.strftime("%B %Y"))
        agenda_head.setText(d.strftime("%a, %b ") + str(d.day))
        key = _iso(d)
        lst.clear()
        found = False
        for e in sorted(
            _events(), key=lambda x: (x.get("title") or "").lower()
        ):
            if str(e.get("date", ""))[:10] != key:
                continue
            title = e.get("title") or "Event"
            item = QListWidgetItem(str(title))
            item.setData(Qt.UserRole, e)
            item.setForeground(QColor(_color_for(title)))
            lst.addItem(item)
            found = True
        if not found:
            empty = QListWidgetItem("No events")
            empty.setForeground(QColor(_MUTED))
            empty.setFlags(Qt.NoItemFlags)
            lst.addItem(empty)
        grid.set_events_for_month(_month_events())

    def show_editor(show: bool) -> None:
        state["edit"] = show
        editor.setVisible(show)
        side.setVisible(not show)
        for w in (day_prev, day_next, today_btn, del_btn, sync_btn, add_btn):
            w.setVisible(not show)
        if show:
            title_in.clear()
            title_in.setFocus(Qt.OtherFocusReason)

    def do_save() -> None:
        title = title_in.text().strip() or "Event"
        events = _events()
        events.append({"date": _iso(grid.selected()), "title": title})
        store.save("calendar.json", events)
        show_editor(False)
        refresh()

    def do_del() -> None:
        item = lst.currentItem()
        if item is None:
            return
        target = item.data(Qt.UserRole)
        if not isinstance(target, dict):
            return
        store.save("calendar.json", [e for e in _events() if e != target])
        refresh()

    def shift_month(delta: int) -> None:
        y, m = grid._year, grid._month + delta
        while m < 1:
            m += 12
            y -= 1
        while m > 12:
            m -= 12
            y += 1
        grid.set_month(y, m)
        refresh()

    def nudge(delta: int) -> None:
        grid.shift_day(delta)
        refresh()

    def do_sync() -> None:
        """Pull Google Calendar via secret iCal URL (IMAP login is not enough)."""
        url = str(store.load("calendar_ical_url", "") or "").strip()
        if not url:
            agenda_head.setText(
                "Set iCal URL in ~/.esp-handset/calendar_ical_url"
            )
            return
        try:
            import urllib.request
            from icalendar import Calendar  # type: ignore
        except Exception:
            agenda_head.setText("Need: pip install icalendar")
            return
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                raw = resp.read()
            cal = Calendar.from_ical(raw)
            events = []
            for comp in cal.walk():
                if comp.name != "VEVENT":
                    continue
                dt = comp.get("dtstart")
                summary = str(comp.get("summary") or "Event")
                if dt is None:
                    continue
                val = dt.dt
                if hasattr(val, "date"):
                    d = val.date() if hasattr(val, "hour") else val
                else:
                    continue
                events.append({"date": d.isoformat(), "title": summary, "src": "ical"})
            # Keep local-only events (no src) + replace prior ical
            local = [e for e in _events() if e.get("src") != "ical"]
            store.save("calendar.json", local + events)
            agenda_head.setText(f"Synced {len(events)} Google events")
            refresh()
        except Exception as e:
            agenda_head.setText(f"Sync failed: {str(e)[:40]}")

    prev_btn.clicked.connect(lambda: shift_month(-1))
    next_btn.clicked.connect(lambda: shift_month(1))
    day_prev.clicked.connect(lambda: nudge(-1))
    day_next.clicked.connect(lambda: nudge(1))
    today_btn.clicked.connect(
        lambda: (grid.set_selected(date.today()), refresh())
    )
    add_btn.clicked.connect(lambda: show_editor(True))
    cancel_btn.clicked.connect(lambda: show_editor(False))
    save_btn.clicked.connect(do_save)
    del_btn.clicked.connect(do_del)
    sync_btn.clicked.connect(do_sync)

    page = page_chrome("Calendar", body, None, scroll=False)

    # Stick on the month grid: L/R change day, Up scrolls/week-back.
    # Down returns False so focus can leave the grid → events list → bottom buttons.
    def grid_move_h(delta: int) -> bool:
        nudge(delta)
        return True

    def grid_move_v(delta: int) -> bool:
        if delta > 0:
            return False
        bar = grid_scroll.verticalScrollBar()
        if bar.maximum() > bar.minimum():
            step = max(18, bar.singleStep() * 2)
            bar.setValue(bar.value() + int(delta) * step)
            return True
        nudge(-7)
        return True

    grid.move_h = grid_move_h  # type: ignore[attr-defined]
    grid.move_v = grid_move_v  # type: ignore[attr-defined]
    # Do NOT set page digi_pad_active / digi_move_* — those trapped focus on the grid
    # and made Today / Del / Sync / ＋ unreachable.
    page.digi_seek = lambda _d: False  # type: ignore[attr-defined]
    page.digi_seek_active = lambda: False  # type: ignore[attr-defined]
    refresh()
    return page
