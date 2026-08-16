"""Shared Digivice media chrome — calm dark lists for tiny screens."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from esp_handset.pages import page_chrome

_BG = "#0e1620"
_SURFACE = "#16202c"
_BORDER = "#243040"
_TEXT = "#e8eef5"
_MUTED = "#7a8a9a"
_ACCENT = "#5ec4a8"
_ACCENT_DIM = "#1a3a32"


def media_btn(text: str, *, primary: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setFocusPolicy(Qt.StrongFocus)
    b.setCursor(Qt.PointingHandCursor)
    b.setMinimumHeight(30)
    if primary:
        b.setStyleSheet(
            f"QPushButton {{ font-size:11px; font-weight:700; padding:4px 10px;"
            f" color:#0a1218; background:{_ACCENT}; border:none; border-radius:8px; }}"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
    else:
        b.setStyleSheet(
            f"QPushButton {{ font-size:11px; font-weight:600; padding:4px 10px;"
            f" color:{_TEXT}; background:#1e2a38; border:1px solid {_BORDER};"
            f" border-radius:8px; }}"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
    return b


def media_list() -> QListWidget:
    lst = QListWidget()
    lst.setFocusPolicy(Qt.StrongFocus)
    lst.setStyleSheet(
        f"QListWidget {{ background:{_SURFACE}; border:1px solid {_BORDER};"
        f" border-radius:8px; font-size:12px; outline:none; color:{_TEXT}; }}"
        f"QListWidget::item {{ padding:8px 10px; border-bottom:1px solid {_BORDER}; }}"
        f"QListWidget::item:selected {{ background:{_ACCENT_DIM}; color:{_TEXT}; }}"
        'QListWidget[digiFocus="1"] { border:2px solid #FFE600; }'
    )
    return lst


def media_header(glyph: str, title: str, subtitle: str = "") -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(2, 0, 2, 2)
    lay.setSpacing(8)
    g = QLabel(glyph)
    g.setStyleSheet(
        f"font-size:22px; color:{_ACCENT}; min-width:28px;"
    )
    g.setAlignment(Qt.AlignCenter)
    col = QVBoxLayout()
    col.setSpacing(0)
    t = QLabel(title)
    t.setStyleSheet(f"font-size:13px; font-weight:700; color:{_TEXT};")
    col.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setStyleSheet(f"font-size:9px; color:{_MUTED};")
        s.setWordWrap(True)
        col.addWidget(s)
    lay.addWidget(g)
    lay.addLayout(col, 1)
    return w


def media_empty(message: str) -> QLabel:
    lab = QLabel(message)
    lab.setAlignment(Qt.AlignCenter)
    lab.setWordWrap(True)
    lab.setStyleSheet(
        f"color:{_MUTED}; font-size:11px; padding:16px;"
        f" background:{_SURFACE}; border-radius:8px; border:1px dashed {_BORDER};"
    )
    return lab


def style_media_body(body: QWidget) -> None:
    body.setStyleSheet(f"background:{_BG}; color:{_TEXT};")


def _pretty_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def make_library_page(
    *,
    title: str,
    glyph: str,
    folder: Path,
    patterns: Tuple[str, ...],
    on_back: Callable[[], None],
    kind_label: str = "files",
    open_cmd: Optional[List[str]] = None,
    open_label: str = "Play",
) -> QWidget:
    """Polished file library for Music / Videos / Audiobooks."""
    from shutil import which
    import subprocess

    del on_back
    body = QWidget()
    style_media_body(body)
    root = QVBoxLayout(body)
    root.setContentsMargins(4, 2, 4, 2)
    root.setSpacing(4)

    head = media_header(glyph, title, str(folder).replace(str(Path.home()), "~"))
    root.addWidget(head)

    count_lab = QLabel("")
    count_lab.setStyleSheet(f"font-size:9px; color:{_MUTED}; padding-left:2px;")
    root.addWidget(count_lab)

    lst = media_list()
    lst.setWordWrap(True)
    lst.setUniformItemSizes(False)
    lst.setSpacing(2)
    empty = media_empty(f"No {kind_label} yet.\nDrop files into\n{folder.name}/")
    empty.hide()
    root.addWidget(lst, 1)
    root.addWidget(empty)

    row = QHBoxLayout()
    row.setSpacing(4)
    open_btn = media_btn(open_label, primary=True)
    refresh_btn = media_btn("Refresh")
    row.addWidget(open_btn, 2)
    row.addWidget(refresh_btn, 1)
    root.addLayout(row)

    paths: List[Path] = []

    def do_refresh() -> None:
        folder.mkdir(parents=True, exist_ok=True)
        paths.clear()
        for pat in patterns:
            paths.extend(folder.glob(pat))
        uniq = sorted(set(paths), key=lambda x: x.name.lower())
        paths[:] = uniq
        lst.clear()
        for p in uniq:
            try:
                sz = _pretty_size(p.stat().st_size)
            except OSError:
                sz = ""
            item = QListWidgetItem(f"{p.name}")
            if sz:
                item.setToolTip(sz)
            # secondary feel via muted suffix in text
            item.setText(f"{p.stem}\n{p.suffix.lstrip('.').upper()}  ·  {sz}")
            lst.addItem(item)
        count_lab.setText(f"{len(uniq)} {kind_label}")
        if not uniq:
            lst.hide()
            empty.show()
        else:
            empty.hide()
            lst.show()

    def do_open() -> None:
        row_i = lst.currentRow()
        if not (0 <= row_i < len(paths)):
            return
        path = paths[row_i]
        if open_cmd:
            subprocess.Popen(
                open_cmd + [str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        for bin_ in ("xdg-open", "mpv", "vlc", "ffplay"):
            if which(bin_):
                subprocess.Popen(
                    [bin_, str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return

    open_btn.clicked.connect(do_open)
    refresh_btn.clicked.connect(do_refresh)
    lst.itemActivated.connect(lambda _=None: do_open())
    do_refresh()
    return page_chrome(title, body, None, scroll=False)
