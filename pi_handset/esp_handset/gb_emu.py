"""Game Boy / GBC ROM picker (receive via Tools → Transfer)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable, List, Optional

from PyQt5.QtCore import Qt, QTimer
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


def _find_launcher() -> str:
    for p in (
        "/usr/local/bin/digivice-gb",
        "/opt/esp-handset/session/digivice-gb.sh",
        str(Path(__file__).resolve().parents[1] / "session" / "digivice-gb.sh"),
        str(Path.home() / "esp-phone" / "pi_handset" / "session" / "digivice-gb.sh"),
    ):
        if os.path.isfile(p):
            return p
    return "/usr/local/bin/digivice-gb"


def _emu_hint() -> str:
    for cmd in ("retroarch", "mgba-sdl", "mgba-qt", "mgba"):
        if any(
            os.path.isfile(os.path.join(d, cmd))
            for d in os.environ.get("PATH", "/usr/bin:/bin").split(":")
        ):
            return f"Emulator: {cmd}"
    return "Need: sudo apt install retroarch libretro-gambatte"


def make_gb_page(
    on_back: Callable[[], None],
    *,
    on_receive: Optional[Callable[[], None]] = None,
) -> QWidget:
    """Games → Game Boy: pick ROM; Receive opens Wi‑Fi Transfer (ROMs)."""
    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(2)
    tip = QLabel(
        "A=Confirm B=Back Start=Home\n"
        "Select=Home+A · Exit=A+B+Home"
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
    play = QPushButton("Play")
    play.setFixedHeight(28)
    play.setStyleSheet("font-weight:800;")
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
        status.setText(f"{_emu_hint()}\n{len(roms)} ROM(s) · Receive = Transfer")
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
        item = lst.currentItem()
        if item is None:
            status.setText("Pick a ROM first")
            return
        path = item.data(Qt.UserRole)
        if not path or not Path(str(path)).is_file():
            status.setText("Invalid ROM")
            return
        rom = str(path)
        DATA.mkdir(parents=True, exist_ok=True)
        try:
            (DATA / "gb-rom").write_text(rom + "\n", encoding="utf-8")
        except OSError:
            pass
        try:
            Path("/run/digivice-gb-rom").write_text(rom + "\n", encoding="utf-8")
        except OSError:
            pass

        launcher = _find_launcher()
        status.setText("Starting Game Boy…")
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":0")
        log_path = DATA / "gb.log"
        try:
            logf = open(log_path, "a", encoding="utf-8")
        except OSError:
            logf = subprocess.DEVNULL
        try:
            subprocess.Popen(
                ["bash", launcher, rom],
                start_new_session=True,
                env=env,
                stdout=logf,
                stderr=logf,
                stdin=subprocess.DEVNULL,
            )
        except Exception as e:
            if logf is not subprocess.DEVNULL:
                try:
                    logf.close()
                except Exception:
                    pass
            status.setText(f"Launch failed: {e}")
            return

        def _quit() -> None:
            try:
                from PyQt5.QtWidgets import QApplication

                app = QApplication.instance()
                if app is not None:
                    app.quit()
            except Exception:
                pass

        # Give digivice-gb time to set mode=gb before we release SPI
        QTimer.singleShot(900, _quit)

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
