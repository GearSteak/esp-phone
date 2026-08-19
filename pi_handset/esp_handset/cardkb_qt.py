"""In-process CardKB (I2C 0x5F) → Digivice keys / field typing.

Bypasses xdotool. cardkb-inputd stays running (uinput for Linux desktop)
but pauses I2C while /run/digivice/cardkb.pause exists.
"""
from __future__ import annotations

import atexit
import os
import time
from pathlib import Path
from typing import Any, Optional

from PyQt5.QtCore import QObject, QTimer, Qt, QEvent
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import QApplication, QLineEdit, QTextEdit, QPlainTextEdit

ADDR = 0x5F
_PAUSE = Path("/run/digivice/cardkb.pause")
_PAUSE_LEGACY = Path("/tmp/digivice-cardkb.pause")
_TEXT_TYPES = (QLineEdit, QTextEdit, QPlainTextEdit)

# CardKB arrow scancodes (M5 Stack CardKB)
_ARROW = {
    0xB4: Qt.Key_Left,
    0xB5: Qt.Key_Up,
    0xB6: Qt.Key_Down,
    0xB7: Qt.Key_Right,
}


def _pause_desktop_reader() -> None:
    try:
        _PAUSE.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(_PAUSE.parent, 0o0777)
        except OSError:
            pass
        _PAUSE.write_text("1\n", encoding="utf-8")
        try:
            os.chmod(_PAUSE, 0o0666)
        except OSError:
            pass
    except OSError:
        try:
            _PAUSE_LEGACY.write_text("1\n", encoding="utf-8")
        except OSError:
            pass


def _unpause_desktop_reader() -> None:
    for p in (_PAUSE, _PAUSE_LEGACY):
        try:
            p.unlink()
        except OSError:
            pass


def _open_bus(bus_id: int = 1) -> Any:
    try:
        import smbus2 as smbus  # type: ignore
    except ImportError:
        import smbus  # type: ignore
    return smbus.SMBus(bus_id)


def _read_byte(bus: Any) -> int:
    try:
        from smbus2 import i2c_msg  # type: ignore

        msg = i2c_msg.read(ADDR, 1)
        bus.i2c_rdwr(msg)
        data = list(msg)
        return int(data[0]) if data else 0
    except Exception:
        return int(bus.read_byte(ADDR)) & 0xFF


class CardKbPoller(QObject):
    """Poll CardKB on the UI thread timer — low latency, no subprocess."""

    def __init__(self, shell, bus_id: int = 1, parent=None):
        super().__init__(parent or shell)
        self._shell = shell
        self._bus_id = bus_id
        self._bus: Optional[Any] = None
        self._fail = 0
        self._ok_logged = False
        self._timer = QTimer(self)
        self._timer.setInterval(25)  # 40 Hz
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        try:
            if self._bus is not None:
                self._bus.close()
        except Exception:
            pass
        self._bus = None
        _unpause_desktop_reader()

    def _ensure_bus(self) -> bool:
        if self._bus is not None:
            return True
        try:
            self._bus = _open_bus(self._bus_id)
            return True
        except Exception as e:
            self._fail += 1
            if self._fail <= 2 or self._fail % 40 == 0:
                print(f"[cardkb] open i2c-{self._bus_id}: {e}", flush=True)
            return False

    def _text_field(self):
        w = QApplication.focusWidget()
        if isinstance(w, _TEXT_TYPES):
            return w
        try:
            from esp_handset import digi_nav

            key = self._shell._nav[-1] if getattr(self._shell, "_nav", None) else None
            page = (getattr(self._shell, "pages", {}) or {}).get(key) if key else None
            if page is None:
                return None
            cur = digi_nav.digi_current(page)
            if isinstance(cur, _TEXT_TYPES) and cur.hasFocus():
                return cur
        except Exception:
            pass
        return None

    def _insert(self, field, ch: str) -> None:
        if isinstance(field, QLineEdit):
            field.insert(ch)
        elif isinstance(field, (QTextEdit, QPlainTextEdit)):
            field.insertPlainText(ch)

    def _nav_key(self, qt_key: int, text: str = "") -> None:
        ev = QKeyEvent(QEvent.KeyPress, qt_key, Qt.NoModifier, text)
        # Prefer shell key path (digi nav / overlays)
        try:
            self._shell.keyPressEvent(ev)
        except Exception:
            QApplication.sendEvent(self._shell, ev)

    def _handle(self, raw: int) -> None:
        field = self._text_field()

        if raw in _ARROW:
            # In a focused field, Left/Right move the caret; Up/Down leave to nav
            qt_key = _ARROW[raw]
            if field is not None and isinstance(field, QLineEdit):
                if qt_key == Qt.Key_Left:
                    field.cursorBackward(False, 1)
                    return
                if qt_key == Qt.Key_Right:
                    field.cursorForward(False, 1)
                    return
            self._nav_key(qt_key)
            return

        if raw in (0x0D, 0x0A):
            # Enter = Confirm (activate / leave typing via shell)
            self._nav_key(Qt.Key_Return, "\n")
            return
        if raw == 0x1B or raw in (0x60,):  # Esc or `
            self._nav_key(Qt.Key_Escape)
            return
        if raw in (0x08, 0x7F):
            if field is not None and isinstance(field, QLineEdit):
                field.backspace()
                return
            self._nav_key(Qt.Key_Backspace, "\b")
            return
        if raw == 0x09:
            self._nav_key(Qt.Key_Tab, "\t")
            return
        if raw == 0x20:
            if field is not None:
                self._insert(field, " ")
                return
            self._nav_key(Qt.Key_Space, " ")
            return
        if 32 <= raw < 127:
            ch = chr(raw)
            if field is not None:
                self._insert(field, ch)
                return
            # Not in a field — if digi highlight is a line edit, focus+type
            try:
                from esp_handset import digi_nav

                key = self._shell._nav[-1] if getattr(self._shell, "_nav", None) else None
                page = (getattr(self._shell, "pages", {}) or {}).get(key) if key else None
                if page is not None:
                    cur = digi_nav.digi_current(page)
                    if isinstance(cur, QLineEdit):
                        cur.setFocus(Qt.OtherFocusReason)
                        digi_nav._highlight(cur, True)
                        cur.insert(ch)
                        return
            except Exception:
                pass
            # else ignore printable (don't spam nav)
            return

    def _tick(self) -> None:
        if not self._ensure_bus():
            return
        assert self._bus is not None
        try:
            raw = _read_byte(self._bus)
            self._fail = 0
        except OSError as e:
            self._fail += 1
            if self._fail <= 3:
                print(f"[cardkb] I2C read: {e}", flush=True)
            try:
                self._bus.close()
            except Exception:
                pass
            self._bus = None
            return
        except Exception as e:
            print(f"[cardkb] read bug: {e!r}", flush=True)
            self._bus = None
            return

        if raw == 0:
            return

        if not self._ok_logged:
            print(f"[cardkb] in-process OK on i2c-{self._bus_id} @ 0x{ADDR:02X}", flush=True)
            self._ok_logged = True

        try:
            self._handle(raw)
        except Exception as e:
            print(f"[cardkb] handle 0x{raw:02X}: {e!r}", flush=True)

        # Drain repeats sitting in the CardKB buffer
        for _ in range(3):
            try:
                if _read_byte(self._bus) == 0:
                    break
            except Exception:
                break


def start_cardkb(shell) -> Optional[CardKbPoller]:
    if os.environ.get("ESP_HANDSET_CARDKB", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return None
    bus = int(os.environ.get("ESP_HANDSET_CARDKB_BUS", "1") or "1")
    _pause_desktop_reader()
    time.sleep(0.5)
    poller = CardKbPoller(shell, bus_id=bus)
    # Probe once — if we cannot open I2C, don't claim the bus
    if not poller._ensure_bus():
        print(
            "[cardkb] cannot open I2C — is user in group 'i2c'? "
            "sudo usermod -aG i2c $USER && reboot",
            flush=True,
        )
        _unpause_desktop_reader()
        return None
    atexit.register(_unpause_desktop_reader)
    poller.start()
    print("[cardkb] in-process poller started", flush=True)
    return poller
