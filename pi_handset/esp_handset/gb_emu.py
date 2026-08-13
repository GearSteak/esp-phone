"""Game Boy / GBC ROM picker (external emu disabled — SPI handoff unsafe)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from esp_handset.pages import page_chrome

DATA = Path.home() / ".esp-handset"
ROM_DIR = DATA / "roms" / "gb"
ROM_DIRS = [
    ROM_DIR,
    Path.home() / "roms" / "gb",
    Path.home() / "ROMs" / "gb",
    Path("/opt/esp-handset/roms/gb"),
]


def _ensure_rom_dir() -> Path:
    ROM_DIR.mkdir(parents=True, exist_ok=True)
    return ROM_DIR


def _list_roms() -> List[Path]:
    found: List[Path] = []
    seen = set()
    _ensure_rom_dir()
    for d in ROM_DIRS:
        if not d.is_dir():
            continue
        try:
            for p in sorted(d.iterdir(), key=lambda x: x.name.casefold()):
                if p.suffix.lower() in (".gb", ".gbc", ".sgb"):
                    key = str(p.resolve()) if p.exists() else str(p)
                    if key in seen:
                        continue
                    seen.add(key)
                    found.append(p)
        except OSError:
            continue
    return found


def make_gb_page(
    on_back: Callable[[], None],
    *,
    on_receive: Optional[Callable[[], None]] = None,
) -> QWidget:
    """Games → Game Boy: list/Transfer only until in-UI emu exists."""
    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(2)
    tip = QLabel(
        "External emu disabled — blanked SPI.\n"
        "Receive ROMs via Transfer; Play later."
    )
    tip.setWordWrap(True)
    tip.setStyleSheet("color:#9ab;font-size:9px;")
    status = QLabel("")
    status.setWordWrap(True)
    status.setStyleSheet("color:#cde;font-size:10px;")
    lst = QListWidget()
    lst.setStyleSheet(
        "QListWidget { background: transparent; border: none; }"
        "QListWidget::item { padding: 4px; min-height: 22px; }"
        "QListWidget::item:selected { background:#FFE600; color:#000; }"
    )
    play = QPushButton("Play (disabled)")
    play.setFixedHeight(28)
    play.setStyleSheet("font-weight:800;")
    play.setEnabled(False)
    recv = QPushButton("Receive ROMs (Wi‑Fi)")
    recv.setFixedHeight(26)
    refresh = QPushButton("Reload")
    refresh.setFixedHeight(24)
    lay.addWidget(tip)
    lay.addWidget(status)
    lay.addWidget(lst, 1)
    lay.addWidget(play)
    lay.addWidget(recv)
    lay.addWidget(refresh)

    def refresh_list() -> None:
        lst.clear()
        roms = _list_roms()
        status.setText(f"Play off (SPI) · Transfer OK\n{len(roms)} ROM(s)")
        if not roms:
            empty = QListWidgetItem("No ROMs yet\n→ Receive ROMs (Wi‑Fi)")
            empty.setFlags(Qt.NoItemFlags)
            lst.addItem(empty)
            return
        for p in roms:
            item = QListWidgetItem(p.name)
            item.setData(Qt.UserRole, str(p))
            lst.addItem(item)
        lst.setCurrentRow(0)

    def launch() -> None:
        status.setText(
            "Play disabled — SPI handoff broke the screen.\n"
            "ROMs still list/Transfer OK."
        )

    def do_receive() -> None:
        if on_receive is not None:
            on_receive()
        else:
            status.setText("Open Tools → Transfer · GB ROMs")

    lst.itemActivated.connect(lambda _i: launch())
    play.clicked.connect(launch)
    refresh.clicked.connect(refresh_list)
    recv.clicked.connect(do_receive)

    chrome = page_chrome("Game Boy", body, on_back, scroll=False)
    refresh_list()
    return chrome
