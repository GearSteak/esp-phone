"""In-app file browser — no Linux desktop, no QFileDialog."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from esp_handset import store
from esp_handset.pages import page_chrome

_IMG = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
_TXT = {".txt", ".md", ".text", ".json", ".csv", ".log", ".py", ".ini", ".cfg", ".toml"}


def _roots() -> List[Path]:
    store.ensure()
    home = Path.home()
    out: List[Path] = []
    for p in (
        home,
        store.BOOKS,
        store.DATA,
        home / "Documents",
        home / "Downloads",
        Path("/media"),
        Path("/mnt"),
        Path("/home"),
    ):
        try:
            if p.exists() and p.is_dir() and p not in out:
                out.append(p)
        except OSError:
            continue
    return out or [home]


def _pdf_page(path: Path, page: int) -> tuple[int, str]:
    """Return (page_count, text). 1-based page."""
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            return 0, "Need python3-pypdf to read PDFs on device.\nCopy a .txt export here, or pip install pypdf."
    try:
        r = PdfReader(str(path))
        n = len(r.pages)
        i = max(0, min(n - 1, page - 1))
        txt = r.pages[i].extract_text() or "(no text on this page)"
        return n, txt
    except Exception as e:
        return 0, str(e)


def make_files_page(on_back: Callable[[], None], start: Optional[Path] = None) -> QWidget:
    body = QWidget()
    body.setStyleSheet("background:#000; color:#fff;")
    stack = QStackedWidget()
    root = QVBoxLayout(body)
    root.setContentsMargins(0, 0, 0, 0)
    root.addWidget(stack, 1)

    browse = QWidget()
    bl = QVBoxLayout(browse)
    bl.setContentsMargins(4, 2, 4, 2)
    bl.setSpacing(3)
    path_lab = QLabel("")
    path_lab.setWordWrap(True)
    path_lab.setStyleSheet("font-size:9px; color:#ccc;")
    lst = QListWidget()
    lst.setFocusPolicy(Qt.StrongFocus)
    lst.setStyleSheet(
        "QListWidget { background:#000; color:#fff; border:1px solid #444; font-size:12px; }"
        "QListWidget::item:selected { background:#fff; color:#000; }"
        'QListWidget[digiFocus="1"] { border:2px solid #fff; }'
    )
    hint = QLabel("Confirm open · Back parent")
    hint.setStyleSheet("font-size:9px; color:#888;")
    bl.addWidget(path_lab)
    bl.addWidget(lst, 1)
    bl.addWidget(hint)

    reader = QWidget()
    rl = QVBoxLayout(reader)
    rl.setContentsMargins(4, 2, 4, 2)
    rl.setSpacing(3)
    r_head = QLabel("")
    r_head.setWordWrap(True)
    r_head.setStyleSheet("font-size:9px; color:#ccc;")
    img = QLabel()
    img.setAlignment(Qt.AlignCenter)
    img.hide()
    text = QTextEdit()
    text.setReadOnly(True)
    text.setStyleSheet(
        "QTextEdit { background:#000; color:#fff; border:none; font-size:11px; }"
    )
    nav = QHBoxLayout()
    prev_b = QPushButton("← Pg")
    next_b = QPushButton("Pg →")
    close_b = QPushButton("Close")
    for b in (prev_b, next_b, close_b):
        b.setFocusPolicy(Qt.StrongFocus)
        b.setMinimumHeight(26)
        b.setStyleSheet(
            "QPushButton { background:#111; color:#fff; border:1px solid #666; }"
            'QPushButton[digiFocus="1"] { border:2px solid #fff; }'
        )
    nav.addWidget(prev_b)
    nav.addWidget(next_b)
    nav.addWidget(close_b)
    rl.addWidget(r_head)
    rl.addWidget(img, 1)
    rl.addWidget(text, 1)
    rl.addLayout(nav)

    stack.addWidget(browse)
    stack.addWidget(reader)

    state = {"dir": start if start and start.exists() else Path.home(), "file": None, "page": 1, "pages": 1}

    def fill_list() -> None:
        d = state["dir"]
        path_lab.setText(str(d))
        lst.clear()
        items: List[tuple[str, str]] = []
        if d.parent != d:
            items.append(("..", ".."))
        try:
            kids = sorted(d.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError as e:
            lst.addItem(f"(can't read: {e})")
            return
        for p in kids:
            if p.name.startswith("."):
                continue
            mark = "/" if p.is_dir() else ""
            items.append((p.name + mark, p.name))
        if len(items) <= (1 if items and items[0][0] == ".." else 0):
            lst.addItem("(empty)")
            if items:
                it = QListWidgetItem(items[0][0])
                it.setData(Qt.UserRole, items[0][1])
                lst.insertItem(0, it)
                lst.setCurrentRow(0)
            return
        for label, name in items:
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, name)
            lst.addItem(it)
        lst.setCurrentRow(0)

    def show_file(path: Path) -> None:
        state["file"] = path
        state["page"] = 1
        suf = path.suffix.lower()
        r_head.setText(path.name)
        img.hide()
        text.show()
        prev_b.setEnabled(False)
        next_b.setEnabled(False)
        if suf in _IMG:
            pm = QPixmap(str(path))
            if not pm.isNull():
                img.setPixmap(pm.scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                img.show()
                text.hide()
                text.setPlainText("")
            else:
                text.setPlainText("Can't display image")
        elif suf == ".pdf":
            n, body = _pdf_page(path, 1)
            state["pages"] = max(1, n)
            r_head.setText(f"{path.name}  1/{state['pages']}")
            text.setPlainText(body)
            prev_b.setEnabled(True)
            next_b.setEnabled(True)
        elif suf in _TXT or path.stat().st_size < 400_000:
            try:
                text.setPlainText(path.read_text(encoding="utf-8", errors="replace")[:80_000])
            except Exception as e:
                text.setPlainText(str(e))
        else:
            text.setPlainText(f"{path.name}\n{path.stat().st_size} bytes\nCan't preview this type.")
        stack.setCurrentWidget(reader)

    def turn(delta: int) -> None:
        path = state["file"]
        if path is None or path.suffix.lower() != ".pdf":
            return
        state["page"] = max(1, min(state["pages"], state["page"] + delta))
        n, body = _pdf_page(path, state["page"])
        state["pages"] = max(state["pages"], n)
        r_head.setText(f"{path.name}  {state['page']}/{state['pages']}")
        text.setPlainText(body)

    def activate() -> None:
        it = lst.currentItem()
        if it is None:
            return
        name = it.data(Qt.UserRole)
        if name is None:
            return
        if name == "..":
            state["dir"] = state["dir"].parent
            fill_list()
            return
        path = state["dir"] / str(name)
        if path.is_dir():
            state["dir"] = path
            fill_list()
            return
        if path.is_file():
            show_file(path)

    def close_reader() -> None:
        stack.setCurrentWidget(browse)
        lst.setFocus(Qt.OtherFocusReason)

    lst.itemActivated.connect(lambda _=None: activate())
    prev_b.clicked.connect(lambda: turn(-1))
    next_b.clicked.connect(lambda: turn(1))
    close_b.clicked.connect(close_reader)
    fill_list()

    chrome = page_chrome("Files", body, on_back, scroll=False)

    def on_hardware_back() -> bool:
        if stack.currentWidget() is reader:
            close_reader()
            return True
        d = state["dir"]
        if d.parent != d and d not in _roots():
            state["dir"] = d.parent
            fill_list()
            return True
        return False

    def open_path(p: str) -> None:
        path = Path(p)
        if path.is_file():
            state["dir"] = path.parent
            fill_list()
            show_file(path)
        elif path.is_dir():
            state["dir"] = path
            fill_list()
            stack.setCurrentWidget(browse)

    chrome.on_hardware_back = on_hardware_back  # type: ignore[attr-defined]
    chrome.open_path = open_path  # type: ignore[attr-defined]
    return chrome
