"""Game Boy / GBC ROM picker — launches digivice-gb then quits Digivice."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable, List

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
ROM_DIRS = [
    DATA / "roms" / "gb",
    Path.home() / "roms" / "gb",
    Path.home() / "ROMs" / "gb",
    Path("/opt/esp-handset/roms/gb"),
]


def _list_roms() -> List[Path]:
    found: List[Path] = []
    seen = set()
    for d in ROM_DIRS:
        try:
            d.mkdir(parents=True, exist_ok=True)
            readme = d / "README.txt"
            if not readme.is_file():
                readme.write_text(
                    "Drop your .gb / .gbc ROMs here.\n"
                    "Digivice → Games → Game Boy\n",
                    encoding="utf-8",
                )
        except OSError:
            pass
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


def make_gb_page(on_back: Callable[[], None]) -> QWidget:
    """Games → Game Boy: pick a ROM, quit Digivice, run emu, return."""
    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(3)

    tip = QLabel(
        "A=Confirm  B=Back  Start=Home\n"
        "Select=Home+Confirm\n"
        "Exit=Confirm+Back+Home"
    )
    tip.setWordWrap(True)
    tip.setStyleSheet("color:#9ab;font-size:9px;")
    status = QLabel("")
    status.setWordWrap(True)
    status.setStyleSheet("color:#cde;font-size:10px;")
    lst = QListWidget()
    lst.setStyleSheet(
        "QListWidget { background: transparent; border: none; }"
        "QListWidget::item { padding: 6px; min-height: 26px; }"
        "QListWidget::item:selected { background:#FFE600; color:#000; }"
    )
    refresh = QPushButton("Reload ROMs")
    refresh.setMinimumHeight(28)
    play = QPushButton("Play")
    play.setMinimumHeight(32)
    play.setStyleSheet("font-weight:800;")

    lay.addWidget(tip)
    lay.addWidget(status)
    lay.addWidget(lst, 1)
    lay.addWidget(play)
    lay.addWidget(refresh)

    def refresh_list() -> None:
        lst.clear()
        roms = _list_roms()
        status.setText(
            f"{_emu_hint()}\nFolder: ~/.esp-handset/roms/gb/\n"
            f"{len(roms)} ROM(s)"
        )
        if not roms:
            empty = QListWidgetItem("No .gb / .gbc found\nCopy ROMs into roms/gb")
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
        try:
            subprocess.Popen(
                ["bash", launcher, rom],
                start_new_session=True,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except Exception as e:
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

        # Let launcher start, then leave Digivice so buttons can enter gb mode
        QTimer.singleShot(600, _quit)

    lst.itemActivated.connect(lambda _i: launch())
    play.clicked.connect(launch)
    refresh.clicked.connect(refresh_list)
    refresh_list()
    return page_chrome("Game Boy", body, on_back, scroll=False)
