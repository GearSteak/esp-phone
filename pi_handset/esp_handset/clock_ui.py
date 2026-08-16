"""Clock hub — alarms & kitchen timer first; wall clock stays quiet."""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable, List, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from esp_handset import store
from esp_handset.pages import page_chrome

_TIMER_STORE = "kitchen_timer.json"


def _btn(text: str, *, primary: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setFocusPolicy(Qt.StrongFocus)
    b.setCursor(Qt.PointingHandCursor)
    if primary:
        b.setStyleSheet(
            "QPushButton { font-size: 11px; font-weight: 700; padding: 4px 8px;"
            " background:#2a6a4a; border:1px solid #3a8a5a; border-radius:4px; }"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
    else:
        b.setStyleSheet(
            "QPushButton { font-size: 11px; font-weight: 600; padding: 4px 8px;"
            " background:#1a2430; border:1px solid #2a3a4a; border-radius:4px; }"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
    return b


def _seg(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setFocusPolicy(Qt.StrongFocus)
    b.setCheckable(True)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(22)
    b.setStyleSheet(
        "QPushButton { font-size: 11px; font-weight: 700; padding: 2px 10px;"
        " background:transparent; border:none; color:#7a8a9a; border-radius:3px; }"
        "QPushButton:checked { color:#e8eef5; background:#243040; }"
        'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
    )
    return b


def _load_timer() -> dict:
    return store.load(
        _TIMER_STORE,
        {"end_ms": 0, "remain_ms": 0, "running": False},
    )


def _save_timer(data: dict) -> None:
    store.save(_TIMER_STORE, data)


def timer_remaining_ms(now_ms: Optional[float] = None) -> int:
    """Live remaining ms for kitchen timer (0 if idle/done)."""
    t = _load_timer()
    if not t.get("running"):
        return max(0, int(t.get("remain_ms") or 0))
    end = float(t.get("end_ms") or 0)
    if end <= 0:
        return 0
    now = now_ms if now_ms is not None else time.time() * 1000.0
    return max(0, int(end - now))


def check_timer_tick() -> Optional[str]:
    """If a running timer just hit zero, clear it and return a label once."""
    t = _load_timer()
    if not t.get("running"):
        return None
    remain = timer_remaining_ms()
    if remain > 0:
        return None
    # Done — clear so we only fire once
    _save_timer({"end_ms": 0, "remain_ms": 0, "running": False})
    fired = store.load("timer_fired.json", {})
    key = datetime.now().strftime("%Y%m%d%H%M%S")
    if fired.get("last") == key[:12]:  # same minute debounce
        return None
    store.save("timer_fired.json", {"last": key[:12]})
    return "Timer done"


def play_alert() -> None:
    def _run() -> None:
        try:
            from esp_handset.audio_out import play_test_tone

            play_test_tone(seconds=1.8)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


def make_clock_hub(
    on_back: Callable[[], None],
    *,
    start_tool: str = "alarms",
) -> QWidget:
    """Unified Clock app: Alarms ↔ Timer (time lives in the status bar)."""
    del on_back
    body = QWidget()
    root = QVBoxLayout(body)
    root.setContentsMargins(2, 0, 2, 0)
    root.setSpacing(3)

    # Tool flip — no wall-clock here (status bar already has time/date)
    flip = QHBoxLayout()
    flip.setSpacing(4)
    tab_alarms = _seg("Alarms")
    tab_timer = _seg("Timer")
    flip.addWidget(tab_alarms)
    flip.addWidget(tab_timer)
    flip.addStretch(1)
    next_lab = QLabel("")
    next_lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    next_lab.setStyleSheet("font-size: 9px; color:#6a8a7a;")
    flip.addWidget(next_lab)
    root.addLayout(flip)

    stack = QStackedWidget()
    root.addWidget(stack, 1)

    # ----- Alarms pane -----
    alarms_w = QWidget()
    a_lay = QVBoxLayout(alarms_w)
    a_lay.setContentsMargins(0, 0, 0, 0)
    a_lay.setSpacing(3)

    lst = QListWidget()
    lst.setFocusPolicy(Qt.StrongFocus)
    lst.setStyleSheet(
        "QListWidget { background:#121820; border:1px solid #1e2a38; border-radius:4px;"
        " font-size:12px; outline:none; }"
        "QListWidget::item { padding:5px 6px; border-bottom:1px solid #1a2430; }"
        "QListWidget::item:selected { background:#243848; color:#e8eef5; }"
        'QListWidget[digiFocus="1"] { border:2px solid #FFE600; }'
    )
    a_lay.addWidget(lst, 1)

    a_row = QHBoxLayout()
    a_row.setSpacing(4)
    add_btn = _btn("＋ Add", primary=True)
    tog_btn = _btn("On/Off")
    del_btn = _btn("Del")
    a_row.addWidget(add_btn)
    a_row.addWidget(tog_btn)
    a_row.addWidget(del_btn)
    a_lay.addLayout(a_row)

    # Compact editor (hidden until Add)
    editor = QFrame()
    editor.setStyleSheet(
        "QFrame { background:#182028; border:1px solid #2a3a4a; border-radius:4px; }"
    )
    e_lay = QVBoxLayout(editor)
    e_lay.setContentsMargins(6, 4, 6, 4)
    e_lay.setSpacing(3)
    e_title = QLabel("New alarm")
    e_title.setStyleSheet("font-size:10px; color:#9ab; font-weight:700;")
    e_lay.addWidget(e_title)
    time_row = QHBoxLayout()
    hh = QSpinBox()
    hh.setRange(0, 23)
    hh.setWrapping(True)
    hh.setFixedWidth(48)
    hh.setStyleSheet("font-size:14px; font-weight:700;")
    mm = QSpinBox()
    mm.setRange(0, 59)
    mm.setWrapping(True)
    mm.setFixedWidth(48)
    mm.setStyleSheet("font-size:14px; font-weight:700;")
    colon = QLabel(":")
    colon.setStyleSheet("font-size:16px; font-weight:700;")
    time_row.addWidget(hh)
    time_row.addWidget(colon)
    time_row.addWidget(mm)
    time_row.addStretch(1)
    e_lay.addLayout(time_row)
    label_in = QLineEdit()
    label_in.setPlaceholderText("Label (optional)")
    label_in.setStyleSheet("font-size:11px; padding:3px;")
    e_lay.addWidget(label_in)
    e_btns = QHBoxLayout()
    save_btn = _btn("Save", primary=True)
    cancel_btn = _btn("Cancel")
    e_btns.addWidget(save_btn)
    e_btns.addWidget(cancel_btn)
    e_lay.addLayout(e_btns)
    editor.hide()
    a_lay.addWidget(editor)

    stack.addWidget(alarms_w)

    # ----- Timer pane -----
    timer_w = QWidget()
    t_lay = QVBoxLayout(timer_w)
    t_lay.setContentsMargins(0, 2, 0, 0)
    t_lay.setSpacing(4)

    remain_lab = QLabel("00:00")
    remain_lab.setAlignment(Qt.AlignCenter)
    remain_lab.setStyleSheet(
        "font-size: 42px; font-weight: 700; font-family: monospace;"
        " color:#e8eef5; letter-spacing:2px;"
    )
    t_lay.addWidget(remain_lab)

    status_lab = QLabel("Ready")
    status_lab.setAlignment(Qt.AlignCenter)
    status_lab.setStyleSheet("font-size:10px; color:#6a7a8a;")
    t_lay.addWidget(status_lab)

    presets = QHBoxLayout()
    presets.setSpacing(4)
    preset_btns: List[QPushButton] = []
    for mins in (1, 5, 10, 15):
        pb = _btn(f"{mins}m")
        presets.addWidget(pb)
        preset_btns.append(pb)
    t_lay.addLayout(presets)

    adj = QHBoxLayout()
    adj.setSpacing(4)
    minus = _btn("−1")
    plus = _btn("+1")
    adj.addWidget(minus)
    adj.addStretch(1)
    adj.addWidget(plus)
    t_lay.addLayout(adj)

    run_row = QHBoxLayout()
    run_row.setSpacing(4)
    start_btn = _btn("Start", primary=True)
    reset_btn = _btn("Reset")
    run_row.addWidget(start_btn, 2)
    run_row.addWidget(reset_btn, 1)
    t_lay.addLayout(run_row)
    t_lay.addStretch(1)

    stack.addWidget(timer_w)

    # ----- Logic -----
    state = {"tool": 0, "edit": False}  # 0=alarms 1=timer

    def _fmt_ms(ms: int) -> str:
        s = max(0, ms // 1000)
        m, sec = divmod(s, 60)
        if m >= 60:
            h, m = divmod(m, 60)
            return f"{h}:{m:02d}:{sec:02d}"
        return f"{m:02d}:{sec:02d}"

    def _alarms() -> List[dict]:
        return list(store.load("alarms.json", []))

    def _next_alarm_hint() -> str:
        now = datetime.now()
        now_m = now.hour * 60 + now.minute
        best = None
        best_d = 10_000
        for a in _alarms():
            if not a.get("enabled", True):
                continue
            parts = str(a.get("time", "")).split(":")
            if len(parts) != 2:
                continue
            try:
                hm = int(parts[0]) * 60 + int(parts[1])
            except ValueError:
                continue
            d = (hm - now_m) % (24 * 60)
            if d < best_d:
                best_d = d
                best = a
        if best is None:
            return ""
        return f"next {best.get('time')}"

    def refresh_alarms() -> None:
        lst.clear()
        for a in _alarms():
            on = bool(a.get("enabled", True))
            pill = "ON" if on else "off"
            label = (a.get("label") or "Alarm").strip()
            t = a.get("time", "??:??")
            item = QListWidgetItem(f"{t}   {label}   · {pill}")
            from PyQt5.QtGui import QColor

            item.setForeground(QColor("#e8eef5" if on else "#6a7a8a"))
            lst.addItem(item)
        next_lab.setText(_next_alarm_hint())

    def show_editor(show: bool) -> None:
        state["edit"] = show
        editor.setVisible(show)
        lst.setVisible(not show)
        add_btn.setVisible(not show)
        tog_btn.setVisible(not show)
        del_btn.setVisible(not show)
        if show:
            now = datetime.now()
            hh.setValue((now.hour + 1) % 24)
            mm.setValue(0)
            label_in.clear()
            hh.setFocus(Qt.OtherFocusReason)

    def do_save_alarm() -> None:
        t = f"{hh.value():02d}:{mm.value():02d}"
        items = _alarms()
        items.append(
            {
                "time": t,
                "label": label_in.text().strip() or "Alarm",
                "enabled": True,
            }
        )
        store.save("alarms.json", items)
        show_editor(False)
        refresh_alarms()

    def do_toggle() -> None:
        row = lst.currentRow()
        items = _alarms()
        if 0 <= row < len(items):
            items[row]["enabled"] = not items[row].get("enabled", True)
            store.save("alarms.json", items)
            refresh_alarms()
            lst.setCurrentRow(row)

    def do_del() -> None:
        row = lst.currentRow()
        items = _alarms()
        if 0 <= row < len(items):
            items.pop(row)
            store.save("alarms.json", items)
            refresh_alarms()

    def set_remain_ms(ms: int, *, running: bool = False) -> None:
        ms = max(0, int(ms))
        if running and ms > 0:
            _save_timer(
                {
                    "end_ms": time.time() * 1000.0 + ms,
                    "remain_ms": ms,
                    "running": True,
                }
            )
        else:
            _save_timer({"end_ms": 0, "remain_ms": ms, "running": False})
        paint_timer()

    def paint_timer() -> None:
        t = _load_timer()
        rem = timer_remaining_ms()
        remain_lab.setText(_fmt_ms(rem if t.get("running") else int(t.get("remain_ms") or 0)))
        if t.get("running"):
            status_lab.setText("Running")
            status_lab.setStyleSheet("font-size:10px; color:#5aaa7a;")
            start_btn.setText("Pause")
            remain_lab.setStyleSheet(
                "font-size: 42px; font-weight: 700; font-family: monospace;"
                " color:#e8eef5; letter-spacing:2px;"
            )
        elif rem == 0 and int(t.get("remain_ms") or 0) == 0:
            status_lab.setText("Ready · pick a preset")
            status_lab.setStyleSheet("font-size:10px; color:#6a7a8a;")
            start_btn.setText("Start")
        else:
            status_lab.setText("Paused")
            status_lab.setStyleSheet("font-size:10px; color:#c9a227;")
            start_btn.setText("Resume")

    def set_preset(mins: int) -> None:
        set_remain_ms(mins * 60 * 1000, running=False)

    def adjust(delta_min: int) -> None:
        t = _load_timer()
        if t.get("running"):
            rem = timer_remaining_ms()
            set_remain_ms(rem + delta_min * 60 * 1000, running=True)
        else:
            rem = int(t.get("remain_ms") or 0)
            set_remain_ms(rem + delta_min * 60 * 1000, running=False)

    def toggle_run() -> None:
        t = _load_timer()
        if t.get("running"):
            rem = timer_remaining_ms()
            set_remain_ms(rem, running=False)
        else:
            rem = int(t.get("remain_ms") or 0)
            if rem <= 0:
                rem = 5 * 60 * 1000  # default 5m if empty
            set_remain_ms(rem, running=True)

    def do_reset() -> None:
        set_remain_ms(0, running=False)

    def show_tool(idx: int) -> None:
        state["tool"] = idx
        stack.setCurrentIndex(idx)
        tab_alarms.setChecked(idx == 0)
        tab_timer.setChecked(idx == 1)
        if idx == 0:
            refresh_alarms()
        else:
            paint_timer()

    def flip_tool(delta: int) -> None:
        show_tool((state["tool"] + delta) % 2)

    tab_alarms.clicked.connect(lambda: show_tool(0))
    tab_timer.clicked.connect(lambda: show_tool(1))
    add_btn.clicked.connect(lambda: show_editor(True))
    cancel_btn.clicked.connect(lambda: show_editor(False))
    save_btn.clicked.connect(do_save_alarm)
    tog_btn.clicked.connect(do_toggle)
    del_btn.clicked.connect(do_del)
    lst.itemActivated.connect(lambda _=None: do_toggle())

    for i, mins in enumerate((1, 5, 10, 15)):
        preset_btns[i].clicked.connect(lambda _=False, m=mins: set_preset(m))
    minus.clicked.connect(lambda: adjust(-1))
    plus.clicked.connect(lambda: adjust(1))
    start_btn.clicked.connect(toggle_run)
    reset_btn.clicked.connect(do_reset)

    def tick_ui() -> None:
        if state["tool"] == 0 and not state["edit"]:
            next_lab.setText(_next_alarm_hint())
        elif state["tool"] == 1:
            next_lab.setText("")
            paint_timer()
        else:
            next_lab.setText("")

    clock_timer = QTimer(body)
    clock_timer.setInterval(250)
    clock_timer.timeout.connect(tick_ui)
    clock_timer.start()

    body.clock_show_tool = show_tool  # type: ignore[attr-defined]
    body.refresh_clock_hub = tick_ui  # type: ignore[attr-defined]

    start_idx = 0 if start_tool != "timer" else 1
    show_tool(start_idx)
    refresh_alarms()
    paint_timer()
    tick_ui()

    page = page_chrome("Clock", body, None, scroll=False)
    page.clock_body = body  # type: ignore[attr-defined]

    # ←→ on the Alarms/Timer tabs flips tools; elsewhere L/R moves focus
    def digi_seek(delta: int) -> bool:
        flip_tool(1 if delta > 0 else -1)
        return True

    def digi_seek_active() -> bool:
        from esp_handset import digi_nav

        cur = digi_nav.digi_current(page)
        return cur is tab_alarms or cur is tab_timer

    page.digi_seek = digi_seek  # type: ignore[attr-defined]
    page.digi_seek_active = digi_seek_active  # type: ignore[attr-defined]
    return page


# Keep a thin alias for old "alarms" page key
def make_alarms_page(on_back: Callable[[], None]) -> QWidget:
    return make_clock_hub(on_back, start_tool="alarms")


def make_timer_page(on_back: Callable[[], None]) -> QWidget:
    return make_clock_hub(on_back, start_tool="timer")
