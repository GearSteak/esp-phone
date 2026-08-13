"""Game Boy / GBC — in-UI emulator (PyBoy). Digivice keeps SPI; no RetroArch handoff."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QSize
from PyQt5.QtGui import QImage, QPixmap, QKeyEvent
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
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

# Digivice pad + RetroArch-ish keyboard (x/z) + CardKB
_BTN_MAP = {
    Qt.Key_Up: "up",
    Qt.Key_Down: "down",
    Qt.Key_Left: "left",
    Qt.Key_Right: "right",
    Qt.Key_Return: "a",
    Qt.Key_Enter: "a",
    Qt.Key_X: "a",
    Qt.Key_Space: "a",
    Qt.Key_Z: "b",
    Qt.Key_Tab: "b",  # Digivice Select
    Qt.Key_Shift: "select",
    Qt.Key_S: "start",
    Qt.Key_1: "start",
    Qt.Key_2: "select",
}


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


def _pyboy_available() -> tuple:
    """Return (ok, message)."""
    try:
        import pyboy  # noqa: F401

        return True, f"PyBoy {getattr(pyboy, '__version__', '?')}"
    except ImportError:
        return False, "Need: sudo pip3 install --break-system-packages pyboy"


class _EmuWorker(QThread):
    """Run PyBoy off the UI thread; emit RGB888 frames."""

    frame = pyqtSignal(object)  # QImage
    failed = pyqtSignal(str)
    stopped = pyqtSignal()

    def __init__(self, rom: Path, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._rom = rom
        self._stop = False
        self._held: Set[str] = set()
        self._pending_press: Set[str] = set()
        self._pending_release: Set[str] = set()
        self._lock_cmds: List[tuple] = []

    def request_stop(self) -> None:
        self._stop = True

    def button_down(self, name: str) -> None:
        self._pending_press.add(name)
        self._pending_release.discard(name)

    def button_up(self, name: str) -> None:
        self._pending_release.add(name)
        self._pending_press.discard(name)

    def button_tap(self, name: str) -> None:
        """One-frame press (for soft Start/Select)."""
        self._lock_cmds.append(("tap", name))

    def run(self) -> None:
        try:
            from pyboy import PyBoy
        except ImportError as e:
            self.failed.emit(f"PyBoy missing: {e}")
            self.stopped.emit()
            return

        boy = None
        try:
            kwargs = {"window": "null"}
            # Quieter / cheaper on Pi Zero 2 W when supported
            for k, v in (
                ("sound_emulated", False),
                ("sound", False),
            ):
                try:
                    boy = PyBoy(str(self._rom), **kwargs, **{k: v})
                    break
                except TypeError:
                    boy = None
            if boy is None:
                boy = PyBoy(str(self._rom), window="null")
            try:
                boy.set_emulation_speed(1)
            except Exception:
                pass

            # Skip boot logo a bit faster when possible
            target_s = 1.0 / 55.0
            last_emit = 0.0
            emit_every = 1.0 / 30.0  # ~30 FPS to Digivice is enough

            while not self._stop:
                t0 = time.perf_counter()

                for name in list(self._pending_press):
                    self._pending_press.discard(name)
                    if name not in self._held:
                        try:
                            boy.button_press(name)
                        except Exception:
                            try:
                                boy.button(name)
                            except Exception:
                                pass
                        self._held.add(name)

                for name in list(self._pending_release):
                    self._pending_release.discard(name)
                    if name in self._held:
                        try:
                            boy.button_release(name)
                        except Exception:
                            pass
                        self._held.discard(name)

                while self._lock_cmds:
                    op, name = self._lock_cmds.pop(0)
                    if op == "tap":
                        try:
                            boy.button(name)
                        except Exception:
                            try:
                                boy.button_press(name)
                                boy.tick(1, True)
                                boy.button_release(name)
                            except Exception:
                                pass

                # Advance ~1 frame; render=True so screen buffer updates
                try:
                    alive = boy.tick(1, True)
                except TypeError:
                    alive = boy.tick()
                if alive is False:
                    break

                now = time.perf_counter()
                if now - last_emit >= emit_every:
                    last_emit = now
                    img = self._frame_qimage(boy)
                    if img is not None:
                        self.frame.emit(img)

                elapsed = time.perf_counter() - t0
                sleep_s = target_s - elapsed
                if sleep_s > 0.001:
                    time.sleep(min(sleep_s, 0.02))

        except Exception as e:
            self.failed.emit(str(e)[:120])
        finally:
            try:
                if boy is not None:
                    boy.stop(save=True)
            except Exception:
                try:
                    if boy is not None:
                        boy.stop()
                except Exception:
                    pass
            self.stopped.emit()

    @staticmethod
    def _frame_qimage(boy) -> Optional[QImage]:
        try:
            import numpy as np

            arr = boy.screen.ndarray
            if arr is not None:
                h, w = int(arr.shape[0]), int(arr.shape[1])
                rgb = np.ascontiguousarray(arr[:, :, :3])
                qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
                return qimg.copy()
        except Exception:
            pass
        try:
            pil = boy.screen.image
            if pil is None:
                return None
            rgb = pil.convert("RGB")
            data = rgb.tobytes()
            w, h = rgb.size
            return QImage(data, w, h, 3 * w, QImage.Format_RGB888).copy()
        except Exception:
            return None


class GbPlayView(QWidget):
    """Fullscreen-ish GB screen; receives Digivice pad keys while visible."""

    digi_gamepad = True

    def __init__(self, on_quit: Callable[[], None]):
        super().__init__()
        self._on_quit = on_quit
        self._worker: Optional[_EmuWorker] = None
        self._held_qt: Dict[int, str] = {}
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setObjectName("gbPlayView")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self.screen = QLabel("…")
        self.screen.setAlignment(Qt.AlignCenter)
        self.screen.setMinimumHeight(144)
        self.screen.setStyleSheet("background:#0a0a0a; color:#9ab;")
        self.screen.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        tip = QLabel("Confirm=A · Select=B · S=Start · Back=quit")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#9ab;font-size:9px;")
        tip.setAlignment(Qt.AlignCenter)

        row = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_start.setFixedHeight(24)
        self.btn_sel = QPushButton("Select")
        self.btn_sel.setFixedHeight(24)
        self.btn_quit = QPushButton("Quit")
        self.btn_quit.setFixedHeight(24)
        row.addWidget(self.btn_start)
        row.addWidget(self.btn_sel)
        row.addWidget(self.btn_quit)

        lay.addWidget(self.screen, 1)
        lay.addWidget(tip)
        lay.addLayout(row)

        self.btn_start.clicked.connect(lambda: self._tap("start"))
        self.btn_sel.clicked.connect(lambda: self._tap("select"))
        self.btn_quit.clicked.connect(self.stop)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(240, 220)

    @property
    def playing(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def start_rom(self, rom: Path) -> None:
        self.stop()
        self.screen.setText(f"Loading\n{rom.name}")
        w = _EmuWorker(rom, self)
        w.frame.connect(self._on_frame)
        w.failed.connect(self._on_fail)
        self._worker = w
        w.start()
        self.setFocus(Qt.OtherFocusReason)

    def stop(self) -> None:
        w = self._worker
        self._worker = None
        self._held_qt.clear()
        if w is not None:
            try:
                w.frame.disconnect()
            except Exception:
                pass
            try:
                w.failed.disconnect()
            except Exception:
                pass
            w.request_stop()
            if not w.wait(1500):
                w.terminate()
                w.wait(500)
        self.screen.setPixmap(QPixmap())
        self.screen.setText("Stopped")

    def _tap(self, name: str) -> None:
        if self._worker is not None:
            self._worker.button_tap(name)

    def _on_frame(self, qimg: QImage) -> None:
        if qimg is None or qimg.isNull():
            return
        pix = QPixmap.fromImage(qimg)
        self.screen.setPixmap(
            pix.scaled(
                self.screen.size(),
                Qt.KeepAspectRatio,
                Qt.FastTransformation,
            )
        )

    def _on_fail(self, msg: str) -> None:
        self.screen.setText(msg)

    def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802
        if e.isAutoRepeat():
            return
        name = _BTN_MAP.get(e.key())
        if name and self._worker is not None:
            self._held_qt[e.key()] = name
            self._worker.button_down(name)
            e.accept()
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e: QKeyEvent) -> None:  # noqa: N802
        if e.isAutoRepeat():
            return
        name = self._held_qt.pop(e.key(), None) or _BTN_MAP.get(e.key())
        if name and self._worker is not None:
            self._worker.button_up(name)
            e.accept()
            return
        super().keyReleaseEvent(e)

    def hideEvent(self, e) -> None:  # noqa: N802
        self.stop()
        super().hideEvent(e)


def make_gb_page(
    on_back: Callable[[], None],
    *,
    on_receive: Optional[Callable[[], None]] = None,
) -> QWidget:
    """Games → Game Boy: ROM list + in-UI PyBoy (SPI stays with Digivice)."""
    body = QWidget()
    outer = QVBoxLayout(body)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    stack = QStackedWidget()
    outer.addWidget(stack)

    # ----- list -----
    list_page = QWidget()
    lay = QVBoxLayout(list_page)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(2)

    ok_py, py_msg = _pyboy_available()
    tip = QLabel(
        "In Digivice (no RetroArch).\n"
        f"{py_msg}\n"
        "Confirm=A · Select=B · S=Start"
        if ok_py
        else f"{py_msg}\nROMs: Transfer still works."
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
    play.setEnabled(ok_py)
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

    play_view = GbPlayView(on_quit=lambda: None)

    def show_list() -> None:
        play_view.stop()
        stack.setCurrentWidget(list_page)
        refresh_list()

    def show_play() -> None:
        stack.setCurrentWidget(play_view)
        play_view.setFocus(Qt.OtherFocusReason)

    play_view._on_quit = show_list  # type: ignore[method-assign]

    def refresh_list() -> None:
        lst.clear()
        roms = _list_roms()
        ok, msg = _pyboy_available()
        play.setEnabled(ok and bool(roms))
        status.setText(f"{msg}\n{len(roms)} ROM(s) · in-UI play")
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
        ok, msg = _pyboy_available()
        if not ok:
            status.setText(msg)
            return
        item = lst.currentItem()
        if item is None:
            status.setText("Pick a ROM")
            return
        path = item.data(Qt.UserRole)
        if not path:
            status.setText("Pick a ROM")
            return
        rom = Path(str(path))
        if not rom.is_file():
            status.setText("ROM missing")
            return
        show_play()
        play_view.start_rom(rom)

    def do_receive() -> None:
        if on_receive is not None:
            on_receive()
        else:
            status.setText("Open Tools → Transfer · GB ROMs")

    def chrome_back() -> None:
        if stack.currentWidget() is play_view:
            show_list()
            return
        on_back()

    def on_hardware_back() -> bool:
        if stack.currentWidget() is play_view:
            show_list()
            return True
        return False

    lst.itemActivated.connect(lambda _i: launch())
    play.clicked.connect(launch)
    refresh.clicked.connect(refresh_list)
    recv.clicked.connect(do_receive)

    stack.addWidget(list_page)
    stack.addWidget(play_view)
    stack.setCurrentWidget(list_page)

    chrome = page_chrome("Game Boy", body, chrome_back, scroll=False)
    chrome.on_hardware_back = on_hardware_back  # type: ignore[attr-defined]
    chrome.gb_board = play_view  # type: ignore[attr-defined]
    refresh_list()
    return chrome
