"""Shadowdark table helper — dice (incl. adv/dis) and a 1-hour torch timer."""
from __future__ import annotations

import random
import time
from typing import Callable, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from esp_handset import store
from esp_handset.pages import page_chrome

_TORCH = "shadowdark_torch.json"
_HOUR = 3600.0

_DICE = (
    ("d4", 4, False),
    ("d6", 6, False),
    ("d8", 8, False),
    ("d10", 10, False),
    ("d12", 12, False),
    ("d20", 20, False),
    ("d100", 100, False),
    ("Adv", 20, "adv"),
    ("Dis", 20, "dis"),
)


def _torch_state() -> dict:
    data = store.load(_TORCH, {}) or {}
    if not isinstance(data, dict):
        return {"end": 0.0, "warned": True}
    return {
        "end": float(data.get("end") or 0),
        "warned": bool(data.get("warned", True)),
    }


def _save_torch(end: float, warned: bool) -> None:
    store.save(_TORCH, {"end": float(end), "warned": bool(warned)})


def check_torch_tick() -> Optional[str]:
    """Notify once when a lit torch burns out (even if you left the page)."""
    st = _torch_state()
    end = st["end"]
    if end <= 0 or st["warned"]:
        return None
    if time.time() < end:
        return None
    _save_torch(0.0, True)
    return "Your torch burns out"


def make_shadowdark_page(on_back: Callable[[], None]) -> QWidget:
    body = QWidget()
    body.setStyleSheet("background:#140c08; color:#f0e6d0;")
    root = QVBoxLayout(body)
    root.setContentsMargins(4, 2, 4, 4)
    root.setSpacing(4)

    result = QLabel("—")
    result.setAlignment(Qt.AlignCenter)
    result.setStyleSheet("font-size:42px; font-weight:800; color:#ffcc66;")
    detail = QLabel("Confirm a die · torch is real-time")
    detail.setWordWrap(True)
    detail.setAlignment(Qt.AlignCenter)
    detail.setStyleSheet("font-size:10px; color:#c4a574;")
    root.addWidget(result)
    root.addWidget(detail)

    grid = QGridLayout()
    grid.setSpacing(4)
    dice_btns = []
    for i, (lab, _sides, _mode) in enumerate(_DICE):
        b = QPushButton(lab)
        b.setFocusPolicy(Qt.StrongFocus)
        b.setMinimumHeight(28)
        b.setStyleSheet(
            "QPushButton { font-size:11px; font-weight:700; color:#f0e6d0;"
            " background:#2a1810; border:1px solid #6a4030; border-radius:8px; }"
            'QPushButton[digiFocus="1"] { border:2px solid #ffcc66; }'
        )
        dice_btns.append(b)
        grid.addWidget(b, i // 3, i % 3)
    root.addLayout(grid)

    torch_lab = QLabel("Torch out")
    torch_lab.setAlignment(Qt.AlignCenter)
    torch_lab.setStyleSheet("font-size:16px; font-weight:700; color:#ff8844;")
    root.addWidget(torch_lab)
    trow = QHBoxLayout()
    light = QPushButton("Light 1h")
    snuff = QPushButton("Out")
    for b in (light, snuff):
        b.setFocusPolicy(Qt.StrongFocus)
        b.setMinimumHeight(30)
        b.setStyleSheet(
            "QPushButton { font-size:11px; font-weight:700; color:#140c08;"
            " background:#ffcc66; border:none; border-radius:8px; }"
            'QPushButton[digiFocus="1"] { border:2px solid #fff; }'
        )
    snuff.setStyleSheet(
        "QPushButton { font-size:11px; font-weight:700; color:#f0e6d0;"
        " background:#5a2018; border:1px solid #8a4030; border-radius:8px; }"
        'QPushButton[digiFocus="1"] { border:2px solid #ffcc66; }'
    )
    trow.addWidget(light, 1)
    trow.addWidget(snuff, 0)
    root.addLayout(trow)
    root.addStretch(1)

    def roll(idx: int) -> None:
        lab, sides, mode = _DICE[idx]
        if mode == "adv":
            a, b = random.randint(1, 20), random.randint(1, 20)
            keep = max(a, b)
            result.setText(str(keep))
            detail.setText(f"Advantage  {a} · {b}  keep {keep}")
            return
        if mode == "dis":
            a, b = random.randint(1, 20), random.randint(1, 20)
            keep = min(a, b)
            result.setText(str(keep))
            detail.setText(f"Disadvantage  {a} · {b}  keep {keep}")
            return
        n = random.randint(1, sides)
        result.setText(str(n))
        crit = ""
        if sides == 20 and n == 20:
            crit = "  · critical"
        elif sides == 20 and n == 1:
            crit = "  · failure"
        detail.setText(f"{lab} → {n}{crit}")

    def paint_torch() -> None:
        st = _torch_state()
        end = st["end"]
        left = int(end - time.time()) if end > 0 else 0
        if left <= 0:
            torch_lab.setText("Torch out")
            torch_lab.setStyleSheet("font-size:16px; font-weight:700; color:#886655;")
            return
        mm, ss = divmod(left, 60)
        hh, mm = divmod(mm, 60)
        if hh:
            torch_lab.setText(f"Torch {hh}:{mm:02d}:{ss:02d}")
        else:
            torch_lab.setText(f"Torch {mm}:{ss:02d}")
        torch_lab.setStyleSheet("font-size:16px; font-weight:700; color:#ff8844;")

    def do_light() -> None:
        _save_torch(time.time() + _HOUR, False)
        detail.setText("Torch lit — 1 hour real time")
        paint_torch()

    def do_snuff() -> None:
        _save_torch(0.0, True)
        detail.setText("Torch extinguished")
        paint_torch()

    for i, b in enumerate(dice_btns):
        b.clicked.connect(lambda _=False, k=i: roll(k))
    light.clicked.connect(do_light)
    snuff.clicked.connect(do_snuff)

    tick = QTimer(body)
    tick.setInterval(500)
    tick.timeout.connect(paint_torch)
    tick.start()
    paint_torch()

    chrome = page_chrome("Shadowdark", body, on_back, scroll=False)

    def on_page_show() -> None:
        paint_torch()

    chrome.on_page_show = on_page_show  # type: ignore[attr-defined]
    return chrome
