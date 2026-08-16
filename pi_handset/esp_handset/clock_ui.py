"""Alarms + kitchen timer pages (separate; Time folder picks one)."""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable, List, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
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


def _load_timer() -> dict:
    return store.load(
        _TIMER_STORE,
        {"end_ms": 0, "remain_ms": 0, "running": False},
    )


def _save_timer(data: dict) -> None:
    store.save(_TIMER_STORE, data)


def timer_remaining_ms(now_ms: Optional[float] = None) -> int:
    t = _load_timer()
    if not t.get("running"):
        return max(0, int(t.get("remain_ms") or 0))
    end = float(t.get("end_ms") or 0)
    if end <= 0:
        return 0
    now = now_ms if now_ms is not None else time.time() * 1000.0
    return max(0, int(end - now))


def check_timer_tick() -> Optional[str]:
    t = _load_timer()
    if not t.get("running"):
        return None
    remain = timer_remaining_ms()
    if remain > 0:
        return None
    _save_timer({"end_ms": 0, "remain_ms": 0, "running": False})
    fired = store.load("timer_fired.json", {})
    key = datetime.now().strftime("%Y%m%d%H%M%S")
    if fired.get("last") == key[:12]:
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


def _next_alarm_hint() -> str:
    now = datetime.now()
    now_m = now.hour * 60 + now.minute
    best = None
    best_d = 10_000
    for a in store.load("alarms.json", []):
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


def make_alarms_page(on_back: Callable[[], None]) -> QWidget:
    """Alarms only — flip lives in the Time radial menu."""
    del on_back
    body = QWidget()
    root = QVBoxLayout(body)
    root.setContentsMargins(2, 0, 2, 0)
    root.setSpacing(3)

    head = QHBoxLayout()
    tip = QLabel("Alarms")
    tip.setStyleSheet("font-size:10px; font-weight:700; color:#8a9aaa;")
    next_lab = QLabel("")
    next_lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    next_lab.setStyleSheet("font-size:9px; color:#6a8a7a;")
    head.addWidget(tip)
    head.addStretch(1)
    head.addWidget(next_lab)
    root.addLayout(head)

    lst = QListWidget()
    lst.setFocusPolicy(Qt.StrongFocus)
    lst.setStyleSheet(
        "QListWidget { background:#121820; border:1px solid #1e2a38; border-radius:4px;"
        " font-size:12px; outline:none; }"
        "QListWidget::item { padding:5px 6px; border-bottom:1px solid #1a2430; }"
        "QListWidget::item:selected { background:#243848; color:#e8eef5; }"
        'QListWidget[digiFocus="1"] { border:2px solid #FFE600; }'
    )
    root.addWidget(lst, 1)

    a_row = QHBoxLayout()
    a_row.setSpacing(4)
    add_btn = _btn("＋ Add", primary=True)
    tog_btn = _btn("On/Off")
    del_btn = _btn("Del")
    a_row.addWidget(add_btn)
    a_row.addWidget(tog_btn)
    a_row.addWidget(del_btn)
    root.addLayout(a_row)

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
    root.addWidget(editor)

    state = {"edit": False}

    def _alarms() -> List[dict]:
        return list(store.load("alarms.json", []))

    def refresh() -> None:
        lst.clear()
        for a in _alarms():
            on = bool(a.get("enabled", True))
            pill = "ON" if on else "off"
            label = (a.get("label") or "Alarm").strip()
            t = a.get("time", "??:??")
            item = QListWidgetItem(f"{t}   {label}   · {pill}")
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

    def do_save() -> None:
        items = _alarms()
        items.append(
            {
                "time": f"{hh.value():02d}:{mm.value():02d}",
                "label": label_in.text().strip() or "Alarm",
                "enabled": True,
            }
        )
        store.save("alarms.json", items)
        show_editor(False)
        refresh()

    def do_toggle() -> None:
        row = lst.currentRow()
        items = _alarms()
        if 0 <= row < len(items):
            items[row]["enabled"] = not items[row].get("enabled", True)
            store.save("alarms.json", items)
            refresh()
            lst.setCurrentRow(row)

    def do_del() -> None:
        row = lst.currentRow()
        items = _alarms()
        if 0 <= row < len(items):
            items.pop(row)
            store.save("alarms.json", items)
            refresh()

    add_btn.clicked.connect(lambda: show_editor(True))
    cancel_btn.clicked.connect(lambda: show_editor(False))
    save_btn.clicked.connect(do_save)
    tog_btn.clicked.connect(do_toggle)
    del_btn.clicked.connect(do_del)
    lst.itemActivated.connect(lambda _=None: do_toggle())

    tick = QTimer(body)
    tick.setInterval(30_000)
    tick.timeout.connect(lambda: next_lab.setText(_next_alarm_hint()))
    tick.start()
    refresh()
    return page_chrome("Alarms", body, None, scroll=False)


def make_timer_page(on_back: Callable[[], None]) -> QWidget:
    """Kitchen timer only."""
    del on_back
    body = QWidget()
    root = QVBoxLayout(body)
    root.setContentsMargins(2, 2, 2, 0)
    root.setSpacing(4)

    remain_lab = QLabel("00:00")
    remain_lab.setAlignment(Qt.AlignCenter)
    remain_lab.setStyleSheet(
        "font-size: 42px; font-weight: 700; font-family: monospace;"
        " color:#e8eef5; letter-spacing:2px;"
    )
    root.addWidget(remain_lab)

    status_lab = QLabel("Ready")
    status_lab.setAlignment(Qt.AlignCenter)
    status_lab.setStyleSheet("font-size:10px; color:#6a7a8a;")
    root.addWidget(status_lab)

    presets = QHBoxLayout()
    presets.setSpacing(4)
    preset_btns: List[QPushButton] = []
    for mins in (1, 5, 10, 15):
        pb = _btn(f"{mins}m")
        presets.addWidget(pb)
        preset_btns.append(pb)
    root.addLayout(presets)

    adj = QHBoxLayout()
    adj.setSpacing(4)
    minus = _btn("−1")
    plus = _btn("+1")
    adj.addWidget(minus)
    adj.addStretch(1)
    adj.addWidget(plus)
    root.addLayout(adj)

    run_row = QHBoxLayout()
    run_row.setSpacing(4)
    start_btn = _btn("Start", primary=True)
    reset_btn = _btn("Reset")
    run_row.addWidget(start_btn, 2)
    run_row.addWidget(reset_btn, 1)
    root.addLayout(run_row)
    root.addStretch(1)

    def _fmt_ms(ms: int) -> str:
        s = max(0, ms // 1000)
        m, sec = divmod(s, 60)
        if m >= 60:
            h, m = divmod(m, 60)
            return f"{h}:{m:02d}:{sec:02d}"
        return f"{m:02d}:{sec:02d}"

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
        paint()

    def paint() -> None:
        t = _load_timer()
        rem = timer_remaining_ms()
        remain_lab.setText(
            _fmt_ms(rem if t.get("running") else int(t.get("remain_ms") or 0))
        )
        if t.get("running"):
            status_lab.setText("Running")
            status_lab.setStyleSheet("font-size:10px; color:#5aaa7a;")
            start_btn.setText("Pause")
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
            set_remain_ms(timer_remaining_ms() + delta_min * 60 * 1000, running=True)
        else:
            set_remain_ms(int(t.get("remain_ms") or 0) + delta_min * 60 * 1000)

    def toggle_run() -> None:
        t = _load_timer()
        if t.get("running"):
            set_remain_ms(timer_remaining_ms(), running=False)
        else:
            rem = int(t.get("remain_ms") or 0)
            if rem <= 0:
                rem = 5 * 60 * 1000
            set_remain_ms(rem, running=True)

    for i, mins in enumerate((1, 5, 10, 15)):
        preset_btns[i].clicked.connect(lambda _=False, m=mins: set_preset(m))
    minus.clicked.connect(lambda: adjust(-1))
    plus.clicked.connect(lambda: adjust(1))
    start_btn.clicked.connect(toggle_run)
    reset_btn.clicked.connect(lambda: set_remain_ms(0, running=False))

    tick = QTimer(body)
    tick.setInterval(250)
    tick.timeout.connect(paint)
    tick.start()
    paint()
    return page_chrome("Timer", body, None, scroll=False)


# Back-compat aliases
def make_clock_hub(on_back: Callable[[], None], *, start_tool: str = "alarms") -> QWidget:
    if start_tool == "timer":
        return make_timer_page(on_back)
    return make_alarms_page(on_back)
