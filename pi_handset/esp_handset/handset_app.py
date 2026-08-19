#!/usr/bin/env python3
"""ESP Digivice handset — Waveshare 2\" LCD (240×320) + hard-button nav.

Cellular / SMS / GPS: SIM7600G-H HAT (AT over USB or GPIO UART).
Nav: Up/Down/Left/Right/Confirm/Back/Home (digi-buttons-inputd).
Typing: CardKB (I2C) and Bluetooth / USB keyboards into focused fields.
LoRa: Heltec USB CDC (optional notify TFT). Exit to Linux Desktop for emulators/apt.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal, QEvent, Qt
from PyQt5.QtWidgets import QApplication, QLabel, QMessageBox, QLineEdit, QTextEdit, QPlainTextEdit


_TEXT_TYPES = (QLineEdit, QTextEdit, QPlainTextEdit)


def _is_typing_key(event) -> bool:
    key = event.key()
    if key in (
        Qt.Key_Backspace,
        Qt.Key_Delete,
        Qt.Key_Tab,
        Qt.Key_Left,
        Qt.Key_Right,
        Qt.Key_Home,
        Qt.Key_End,
    ):
        # Left/Right/Home as typing only when already in a field (handled elsewhere)
        return key in (Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_Tab)
    if key in (
        Qt.Key_Shift,
        Qt.Key_Control,
        Qt.Key_Alt,
        Qt.Key_Meta,
        Qt.Key_AltGr,
        Qt.Key_CapsLock,
        Qt.Key_NumLock,
        Qt.Key_ScrollLock,
    ):
        return False
    text = event.text() or ""
    return bool(text) and text.isprintable()


class _KioskKeyFilter(QObject):
    """Route nav keys to Digivice; let CardKB/BT type into text fields.

    Important: in kiosk mode the HDMI ScaledScreenHost owns X focus, while
    QLineEdits live on the off-screen phone canvas. Returning False from this
    filter delivers the key to the *host*, which never inserts into the field.
    Always sendEvent() typing keys to the real QLineEdit and accept them.
    """

    def __init__(self, shell: object):
        super().__init__(shell)
        self._shell = shell

    def _text_target(self):
        w = QApplication.focusWidget()
        if isinstance(w, _TEXT_TYPES):
            return w
        page = None
        try:
            key = self._shell._nav[-1] if getattr(self._shell, "_nav", None) else None
            pages = getattr(self._shell, "pages", {}) or {}
            if key and key in pages:
                page = pages[key]
        except Exception:
            page = None
        if page is None:
            return None
        try:
            from esp_handset import digi_nav

            cur = digi_nav.digi_current(page)
            if isinstance(cur, _TEXT_TYPES):
                return cur
            for child in page.findChildren(_TEXT_TYPES):
                if child.isVisible() and child.isEnabled():
                    return child
        except Exception:
            pass
        return None

    def _deliver_to_field(self, field, event) -> bool:
        """Fast path: mutate the field directly (no scroll / no event clone lag)."""
        try:
            if not field.hasFocus():
                field.setFocus(Qt.OtherFocusReason)
        except Exception:
            pass

        key = event.key()
        text = event.text() or ""

        if isinstance(field, QLineEdit):
            if key == Qt.Key_Backspace:
                field.backspace()
                return True
            if key == Qt.Key_Delete:
                field.del_()
                return True
            if key == Qt.Key_Left:
                field.cursorBackward(False, 1)
                return True
            if key == Qt.Key_Right:
                field.cursorForward(False, 1)
                return True
            if key == Qt.Key_Home:
                field.home(False)
                return True
            if key == Qt.Key_End:
                field.end(False)
                return True
            if text and text.isprintable():
                field.insert(text)
                return True

        if isinstance(field, (QTextEdit, QPlainTextEdit)):
            if key == Qt.Key_Backspace:
                cursor = field.textCursor()
                cursor.deletePreviousChar()
                field.setTextCursor(cursor)
                return True
            if text and text.isprintable():
                field.insertPlainText(text)
                return True

        # Fallback for odd keys
        try:
            from PyQt5.QtGui import QKeyEvent

            clone = QKeyEvent(
                QEvent.KeyPress,
                event.key(),
                event.modifiers(),
                event.text(),
                event.isAutoRepeat(),
                event.count(),
            )
            QApplication.sendEvent(field, clone)
        except Exception:
            QApplication.sendEvent(field, event)
        return True

    def _emu_board(self):
        try:
            nav_key = (
                self._shell._nav[-1] if getattr(self._shell, "_nav", None) else ""
            )
            page = (getattr(self._shell, "pages", {}) or {}).get(nav_key)
            if page is None:
                return None
            board = getattr(page, "emu_board", None) or getattr(page, "gb_board", None)
            if board is None:
                return None
            if getattr(board, "capturing_pad", False) or getattr(board, "playing", False):
                return board
        except Exception:
            return None
        return None

    def eventFilter(self, obj, event):  # noqa: N802
        et = event.type()
        board = None
        if et in (QEvent.KeyPress, QEvent.KeyRelease):
            board = self._emu_board()
        if et == QEvent.KeyRelease:
            if board is not None:
                board.keyReleaseEvent(event)
                return True
            return False
        if et != QEvent.KeyPress:
            return False
        key = event.key()
        # Exit keys always — even if focus is weird
        if key in (Qt.Key_F12, Qt.Key_F10) or (
            key == Qt.Key_Q and event.modifiers() & Qt.ControlModifier
        ):
            self._shell.keyPressEvent(event)
            return True
        if (
            key == Qt.Key_D
            and event.modifiers() & Qt.ControlModifier
            and event.modifiers() & Qt.ShiftModifier
        ):
            self._shell.keyPressEvent(event)
            return True

        # In-UI emulator owns the Digivice pad (Confirm=A, Back=B, Home=Start).
        if board is not None:
            board.keyPressEvent(event)
            return True

        w = QApplication.focusWidget()

        # Already typing into a field (Confirm on QLineEdit) — keep keys there
        if isinstance(w, _TEXT_TYPES):
            if key in (Qt.Key_Escape, Qt.Key_Home):
                try:
                    w.clearFocus()
                except Exception:
                    pass
                self._shell.keyPressEvent(event)
                return True
            # Left/Right/Backspace/letters must go to the field, not the host
            return self._deliver_to_field(w, event)

        # In-UI arcade: let the board keep focus for pad keys
        if w is not None and (w.__class__.__module__ or "").endswith("games_ui"):
            if key in (Qt.Key_Escape, Qt.Key_Home):
                self._shell.keyPressEvent(event)
                return True
            return False

        # Not in a text field: CardKB/BT printable → focus digi-highlighted field
        if _is_typing_key(event):
            target = self._text_target()
            if target is not None:
                return self._deliver_to_field(target, event)
            return False

        if key not in {
            Qt.Key_Left,
            Qt.Key_Right,
            Qt.Key_Up,
            Qt.Key_Down,
            Qt.Key_Return,
            Qt.Key_Enter,
            Qt.Key_Escape,
            Qt.Key_Home,
        }:
            return False
        self._shell.keyPressEvent(event)
        return True


# Installed as /opt/esp-handset/handset_app.py next to package esp_handset/
# OR run from repo as pi_handset/esp_handset/handset_app.py
_HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.isdir(os.path.join(_HERE, "esp_handset")):
    sys.path.insert(0, _HERE)
else:
    sys.path.insert(0, os.path.dirname(_HERE))

from esp_handset.bridge import EspBridge  # noqa: E402
from esp_handset.sim7600 import Sim7600  # noqa: E402
from esp_handset import apps as handset_apps  # noqa: E402
from esp_handset import pages  # noqa: E402
from esp_handset import features  # noqa: E402
from esp_handset import games_ui  # noqa: E402
from esp_handset import emu_ui  # noqa: E402
from esp_handset import wifi_transfer  # noqa: E402
from esp_handset import ollama_chat  # noqa: E402
from esp_handset import store  # noqa: E402
from esp_handset import display_geom as geom  # noqa: E402
from esp_handset.shell import (  # noqa: E402
    APPS_APPS,
    ACCOUNTS_APPS,
    CALLS_APPS,
    CLOCK_APPS,
    DEBUG_APPS,
    GAMES_APPS,
    MEDIA_APPS,
    SETTINGS_APPS,
    SMS_APPS,
    SYSTEM_APPS,
    DISPLAY_APPS,
    TOOLS_APPS,
    PhoneShell,
)
from esp_handset import accounts_ui  # noqa: E402
from esp_handset import call_ui  # noqa: E402
from esp_handset.call_ui import CallController  # noqa: E402

DATA = Path.home() / ".esp-handset"


class BridgeSignals(QObject):
    line = pyqtSignal(str)
    sms = pyqtSignal(str, str)
    modem_ready = pyqtSignal(object)


def build_app(bridge: Optional[EspBridge], modem: Optional[Sim7600]) -> PhoneShell:
    shell = PhoneShell()
    DATA.mkdir(parents=True, exist_ok=True)
    signals = BridgeSignals()
    # Mutable so Settings → Network → Reconnect can attach a late modem
    modem_box: dict = {"m": modem}

    def get_modem() -> Optional[Sim7600]:
        return modem_box.get("m")

    def set_modem(m: Optional[Sim7600]) -> None:
        old = modem_box.get("m")
        modem_box["m"] = m
        if m is not None and m is not old:
            try:
                m.on_sms(lambda n, t: signals.sms.emit(n, t))
            except Exception:
                pass
        _apply_modem_signal_provider()

    def _apply_modem_signal_provider() -> None:
        if modem_box.get("m") is None:
            shell.set_modem_signal_provider(lambda: None)
            return

        def _csq_line():
            cur = modem_box.get("m")
            if cur is None:
                return None
            try:
                return cur.signal()
            except Exception:
                return None

        shell.set_modem_signal_provider(_csq_line)

    signals.modem_ready.connect(set_modem)

    def status(msg: str) -> None:
        shell.set_status_right(msg)

    def back() -> None:
        shell.back()

    def open_page(key: str) -> None:
        shell.go(key)

    def on_linux() -> None:
        # No Yes/No dialog — hard buttons + grabKeyboard cannot answer MessageBox
        handset_apps.exit_to_desktop()

    def on_linux_now() -> None:
        """F12 / Escape×3 / Settings→Linux: leave immediately."""
        handset_apps.exit_to_desktop()

    shell.on_linux_desktop = on_linux  # type: ignore[attr-defined]
    shell.on_linux_desktop_now = on_linux_now  # type: ignore[attr-defined]
    # Digivice toasts always; Heltec notify panel is optional extra
    store.set_toast_handler(lambda t, b, k: shell.show_toast(t, b, k))
    if bridge:
        store.set_esp_notif_handler(
            lambda t, b, k: bridge.notif(t, b, k)  # type: ignore[union-attr]
        )

    # Radial submenus (main → folder → app)
    shell.register_page(
        "folder_apps",
        shell.build_folder_keyed("folder_apps", "Apps", APPS_APPS),
    )
    shell.register_page(
        "folder_calls",
        shell.build_folder_keyed("folder_calls", "Calls", CALLS_APPS),
    )
    shell.register_page(
        "folder_sms",
        shell.build_folder_keyed("folder_sms", "SMS", SMS_APPS),
    )
    shell.register_page(
        "folder_time",
        shell.build_folder_keyed("folder_time", "Time", CLOCK_APPS),
    )
    shell.register_page(
        "folder_tools",
        shell.build_folder_keyed("folder_tools", "Tools", TOOLS_APPS),
    )
    shell.register_page(
        "folder_settings",
        shell.build_folder_keyed("folder_settings", "Settings", SETTINGS_APPS),
    )
    shell.register_page(
        "folder_media",
        shell.build_folder_keyed("folder_media", "Media", MEDIA_APPS),
    )
    shell.register_page(
        "folder_games",
        shell.build_folder_keyed("folder_games", "Games", GAMES_APPS),
    )

    # Wired pages
    calls = CallController(shell, on_status=status)
    shell._call_controller = calls  # type: ignore[attr-defined]

    def open_call_log() -> None:
        page = shell.pages.get("call_log")
        ref = getattr(page, "refresh_call_log", None) if page else None
        if callable(ref):
            ref()
        shell.go("call_log")

    shell.register_page(
        "phone",
        call_ui.make_phone_page(
            back,
            status,
            on_call_log=open_call_log,
            start_call=calls.start_outbound,
            hangup_call=calls.hangup,
        ),
    )
    sms_page = pages.make_sms_page(modem, back, status, get_modem=get_modem)
    shell.register_page("messages", sms_page)

    from PyQt5.QtWidgets import QLineEdit, QPushButton, QVBoxLayout, QWidget

    def open_dial(number: str) -> None:
        shell.go("phone")
        page = shell.pages.get("phone")
        if page is None:
            return
        setter = getattr(page, "set_dial_number", None)
        if callable(setter):
            setter(number)
            return
        for child in page.findChildren(QLineEdit):
            if child.objectName() == "dialDisplay":
                child.setText(number)
                break
        else:
            for child in page.findChildren(QLineEdit):
                child.setText(number)
                break

    def open_sms_to(number: str) -> None:
        shell.go("messages")
        opener = getattr(sms_page, "open_sms_thread", None)
        if callable(opener):
            opener(number)

    lora_page = pages.make_lora_page(bridge, back, status)
    shell.register_page("lora", lora_page)

    def open_lora_to(peer: str) -> None:
        shell.go("lora")
        opener = getattr(lora_page, "open_lora_thread", None)
        if callable(opener):
            opener(peer)

    def open_email_to(addr: str) -> None:
        shell.go("email")
        # Prefill compose "To" if the email page exposes one
        page = shell.pages.get("email")
        if page is None:
            return
        for name in ("compose_to", "prefill_to"):
            fn = getattr(page, name, None)
            if callable(fn):
                fn(str(addr or ""))
                return
        for child in page.findChildren(QLineEdit):
            ph = (child.placeholderText() or "").lower()
            if "to" in ph or "email" in ph or not child.text():
                child.setText(addr)
                break

    shell.register_page(
        "contacts",
        pages.make_contacts_page(
            back,
            open_dial,
            open_sms=open_sms_to,
            open_lora=open_lora_to,
            open_email=open_email_to,
        ),
    )
    shell.register_page(
        "call_log",
        call_ui.make_call_log_page(back, on_redial=calls.start_outbound),
    )
    shell.register_page("camera", pages.make_camera_page(back, status))
    shell.register_page("gallery", pages.make_gallery_page(back, status))
    shell.register_page("gps", pages.make_gps_page(modem, back, status, get_modem=get_modem))
    shell.register_page("notes", pages.make_notes_page(back))
    shell.register_page("todos", pages.make_todos_page(back))
    from esp_handset.clock_ui import make_alarms_page, make_timer_page

    shell.register_page("clock", make_alarms_page(back))
    shell.register_page("clock_face", make_alarms_page(back))  # legacy key
    shell.register_page("timer", make_timer_page(back))
    shell.register_page("calc", pages.make_calc_page(back))
    shell.register_page("ai", ollama_chat.make_ollama_page(back))
    shell.register_page(
        "settings",
        pages.make_settings_hub(back, open_page, on_linux),
    )
    shell.register_page(
        "set_network",
        pages.make_network_page(
            modem, back, status, get_modem=get_modem, set_modem=set_modem
        ),
    )
    shell.register_page("set_about", pages.make_about_page(modem, back))
    shell.register_page("set_update", pages.make_update_page(back))
    shell.register_page("set_mouse", pages.make_mouse_page(back))
    shell.register_page(
        "set_debug",
        shell.build_folder_keyed("set_debug", "Debug", DEBUG_APPS),
    )
    shell.register_page(
        "set_system",
        shell.build_folder_keyed("set_system", "System", SYSTEM_APPS),
    )
    shell.register_page(
        "set_display",
        shell.build_folder_keyed("set_display", "Display", DISPLAY_APPS),
    )
    shell.register_page("dbg_sound", pages.make_debug_page(back))
    shell.register_page(
        "dbg_notifs",
        pages.make_debug_notifs_page(
            back,
            show_toast=lambda t, b, k: shell.show_toast(t, b, k),
            show_incoming=lambda *a, **kw: shell.show_incoming_call(*a, **kw),
        ),
    )
    # Old Sounds menu key → sound debug
    shell.pages["set_sounds"] = shell.pages["dbg_sound"]
    shell.register_page("set_power", pages.make_power_page(back))
    shell.register_page("help", pages.make_help_page(back))
    shell.register_page(
        "set_appearance", pages.make_appearance_page(shell, back)
    )
    shell.register_page("set_orientation", pages.make_orientation_page(back))

    def browser_open():
        try:
            status("Opening browser…")
            handset_apps.open_browser()
        except Exception as e:
            print(f"[handset] browser: {e}", flush=True)
            shell.go("browser_stub")

    shell.on_browser = browser_open  # type: ignore[attr-defined]
    shell.register_page(
        "browser_stub",
        pages.stub_page(
            "Browser",
            "No browser found.\nFrom Linux Desktop:\n  sudo apt install midori\n"
            "Then try Browser again from home.",
            back,
        ),
    )

    # Previously scaffolded — now implemented
    shell.register_page("calendar", features.make_calendar_page(back))
    shell.register_page("alarms", features.make_alarms_page(back))
    notifs_page = features.make_notifs_page(back)
    shell.register_page("notifs", notifs_page)
    shell.register_page("email", features.make_email_page(back))
    shell.register_page("convert", features.make_convert_page(back))
    shell.register_page("weather", features.make_weather_page(back, modem))
    steps_page = features.make_steps_page(back)
    shell.register_page("steps", steps_page)
    try:
        from esp_handset.steps_pi import start_monitor

        # Start after display claimed GPIO — delay avoids setmode races
        from PyQt5.QtCore import QTimer

        QTimer.singleShot(1500, lambda: start_monitor())
    except Exception as e:
        print(f"[handset] steps monitor: {e}", flush=True)
    shell.register_page(
        "share_gps", features.make_share_gps_page(modem, back, status)
    )
    shell.register_page("recorder", features.make_recorder_page(back, status))
    shell.register_page(
        "music",
        features.make_file_media_page(
            "Music", store.MUSIC, ("*.mp3", "*.ogg", "*.flac", "*.wav", "*.m4a"), back
        ),
    )
    shell.register_page(
        "videos",
        features.make_file_media_page(
            "Videos", store.VIDEOS, ("*.mp4", "*.mkv", "*.webm", "*.avi", "*.mjpeg"), back
        ),
    )
    shell.register_page("ebooks", features.make_ebook_page(back))
    shell.register_page(
        "audiobooks",
        features.make_file_media_page(
            "Audiobooks",
            store.AUDIOBOOKS,
            ("*.mp3", "*.ogg", "*.m4a", "*.flac"),
            back,
        ),
    )
    transfer_page = wifi_transfer.make_wifi_transfer_page(back)
    shell.register_page("wifi_transfer", transfer_page)

    def open_rom_transfer(system_key: str = "roms") -> None:
        page = shell.pages.get("wifi_transfer")
        setter = getattr(page, "set_transfer_dest", None)
        dest = "roms"
        sys = emu_ui.SYSTEMS.get(system_key)
        if sys is not None:
            dest = f"rom_{sys.folder}"
        if dest not in wifi_transfer.DESTINATIONS:
            dest = "roms"
        if callable(setter):
            setter(dest)
        shell.go("wifi_transfer")

    for _ek, _esys in emu_ui.SYSTEMS.items():
        shell.register_page(
            _ek,
            emu_ui.make_emu_page(
                _esys, back, on_receive=lambda k=_ek: open_rom_transfer(k)
            ),
        )
    shell.register_page("snake", games_ui.make_snake(back))
    shell.register_page("pong", games_ui.make_pong(back))
    shell.register_page("tetris", games_ui.make_tetris(back))
    shell.register_page("solitaire", games_ui.make_solitaire(back))
    shell.register_page("uno", games_ui.make_uno(back))
    from esp_handset.shadowdark_ui import make_shadowdark_page

    shell.register_page("shadowdark", make_shadowdark_page(back))
    shell.register_page("set_security", features.make_security_page(back))
    shell.register_page(
        "set_accounts",
        shell.build_folder_keyed("set_accounts", "Accounts", ACCOUNTS_APPS),
    )
    shell.register_page("acct_sip", accounts_ui.make_sip_account_page(back))
    shell.register_page("acct_email", accounts_ui.make_email_account_page(back))
    shell.register_page("acct_ai", accounts_ui.make_ai_account_page(back))
    shell.register_page("stub", pages.stub_page("App", "Unknown app key.", back))

    # Bridge events
    def on_line(_kind: str, line: str) -> None:
        signals.line.emit(line)

    def on_bridge_line(line: str) -> None:
        if line.startswith("STEPS"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                total = store.apply_esp_steps(int(parts[1]))
                ref = getattr(steps_page, "refresh_steps", None)
                if callable(ref):
                    ref()
                status(f"Steps {total}")
            return
        if line.startswith("LORA RX") or line.startswith("ACK LORA") or line.startswith(
            "ERR LORA"
        ):
            if line.startswith("LORA RX"):
                ingest = getattr(lora_page, "ingest_lora_rx", None)
                if callable(ingest):
                    ingest(line)
                store.push_notif("LoRa", line[7:].strip()[:80], "lora")
                ref = getattr(notifs_page, "refresh_notifs", None)
                if callable(ref):
                    ref()
            else:
                refresh = getattr(lora_page, "refresh_lora", None)
                if callable(refresh):
                    refresh()
            status(line[:48])
        elif line.startswith("STATUS") or line.startswith("READY"):
            if "steps=" in line:
                try:
                    tok = [t for t in line.split() if t.startswith("steps=")][0]
                    store.apply_esp_steps(int(tok.split("=", 1)[1]))
                    ref = getattr(steps_page, "refresh_steps", None)
                    if callable(ref):
                        ref()
                except Exception:
                    pass
            if "SIM7600" not in (shell.signal_lab.text() or ""):
                status(line[:40])

    def on_sms(num: str, text: str) -> None:
        threads = pages._load_sms_threads()
        threads.setdefault(num, []).append(
            {
                "dir": "in",
                "text": text,
                "at": datetime.now().isoformat(),
                "read": False,
            }
        )
        pages._save_sms_threads(threads)
        refresh = getattr(sms_page, "refresh_sms", None)
        if callable(refresh):
            refresh()
        store.push_notif("SMS", f"{num}: {text[:60]}", "sms")
        ref = getattr(notifs_page, "refresh_notifs", None)
        if callable(ref):
            ref()
        status(f"SMS {num}")

    signals.line.connect(on_bridge_line)
    signals.sms.connect(on_sms)

    if bridge:
        bridge.on_event(on_line)
        try:
            bridge.request_status()
        except Exception as e:
            status(f"ESP: {e}")
    else:
        status("No ESP · modem OK to test")

    if get_modem():
        m0 = get_modem()
        assert m0 is not None
        m0.on_sms(lambda n, t: signals.sms.emit(n, t))

    _apply_modem_signal_provider()

    shell._modem_wake_signal = signals.modem_ready  # type: ignore[attr-defined]
    shell.get_modem = get_modem  # type: ignore[attr-defined]

    from PyQt5.QtCore import QTimer

    def _alarm_poll():
        try:
            from esp_handset.clock_ui import check_timer_tick, play_alert

            label = features.check_alarms_tick()
            if label:
                store.push_notif("Alarm", label, "alarm")
                ref = getattr(notifs_page, "refresh_notifs", None)
                if callable(ref):
                    ref()
                status(f"Alarm: {label}")
                play_alert()
            done = check_timer_tick()
            if done:
                store.push_notif("Timer", done, "timer")
                ref = getattr(notifs_page, "refresh_notifs", None)
                if callable(ref):
                    ref()
                status(done)
                play_alert()
            from esp_handset.shadowdark_ui import check_torch_tick

            torch = check_torch_tick()
            if torch:
                store.push_notif("Shadowdark", torch, "torch")
                ref = getattr(notifs_page, "refresh_notifs", None)
                if callable(ref):
                    ref()
                status(torch)
                play_alert()
        except Exception as e:
            print(f"[handset] alarm poll: {e}", flush=True)

    atimer = QTimer(shell)
    atimer.timeout.connect(_alarm_poll)
    atimer.start(2_000)

    return shell


def main() -> int:
    # Kill HiDPI / dual-screen scale that crops 240×320 into a corner of 1080p
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
    os.environ.setdefault("QT_SCALE_FACTOR", "1")
    os.environ.setdefault("QT_SCREEN_SCALE_FACTORS", "1")
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
    try:
        from PyQt5.QtCore import Qt as _Qt

        QApplication.setAttribute(_Qt.AA_DisableHighDpiScaling, True)
    except Exception:
        pass

    app = QApplication(sys.argv)
    # Digivice is hard-button UI — never show a mouse pointer over the phone
    try:
        from PyQt5.QtCore import Qt as _QtCur

        app.setOverrideCursor(_QtCur.BlankCursor)
    except Exception:
        pass
    store.ensure()
    bridge: Optional[EspBridge] = None
    want_update = False

    # Cute splash + update check ONLY (no modem/SPI here — that froze the panel)
    skip_splash = os.environ.get("ESP_HANDSET_SKIP_BOOT_SPLASH", "").strip() in (
        "1",
        "true",
        "yes",
    )
    if not skip_splash:
        try:
            from esp_handset.boot_splash import run_boot_splash

            _check, want_update = run_boot_splash(app)
            print(
                f"[handset] boot check: {_check.status} {_check.detail!r} "
                f"want_update={want_update}",
                flush=True,
            )
        except Exception as e:
            print(f"[handset] boot splash failed ({e}) — continuing", flush=True)

    print("[handset] waking radios…", flush=True)
    try:
        bridge = EspBridge()
        bridge.open()
    except Exception as e:
        print(f"[handset] LoRa ESP offline ({e})", flush=True)
        bridge = None

    win = build_app(bridge, None)
    app.installEventFilter(_KioskKeyFilter(win))
    # SIP daemon in a background thread — never block / freeze Digivice UI
    try:
        from PyQt5.QtCore import QTimer
        from esp_handset import sip_call

        QTimer.singleShot(1200, sip_call.ensure_async)
    except Exception as e:
        print(f"[handset] SIP boot hook failed ({e})", flush=True)
    # CardKB: read I2C in-process (instant typing). Prefer over cardkb-inputd/xdotool.
    try:
        from esp_handset.cardkb_qt import start_cardkb

        win._cardkb = start_cardkb(win)  # type: ignore[attr-defined]
        if win._cardkb is None:
            print("[handset] CardKB in-process off/unavailable", flush=True)
    except Exception as e:
        print(f"[handset] CardKB in-process failed ({e})", flush=True)
        try:
            import subprocess

            subprocess.run(
                ["sudo", "-n", "systemctl", "start", "cardkb-inputd"],
                timeout=3,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
    # Skip PIN unlock in kiosk by default (set ESP_HANDSET_SKIP_PIN=0 to require)
    if os.environ.get("ESP_HANDSET_SKIP_PIN", "1").strip() not in ("1", "true", "yes"):
        if not features.verify_pin_dialog(win):
            print("[handset] PIN cancelled — exit", flush=True)
            if bridge:
                bridge.close()
            m = getattr(win, "get_modem", lambda: None)()
            if m:
                m.close()
            return 1
    print("[handset] showing UI…", flush=True)
    kiosk = os.environ.get("ESP_HANDSET_KIOSK", "").strip() in ("1", "true", "yes")
    if kiosk:
        geom.apply_kiosk(win)
        # Do NOT raise the phone canvas above fullscreen hosts — that caused
        # the floating 240×320 "small portion" on HDMI.
        try:
            win.lower()
        except Exception:
            pass
        ctl = getattr(win, "_kiosk_controller", None) or getattr(
            win, "_multi_presenter", None
        )
        if ctl is not None and hasattr(ctl, "_raise_hosts"):
            try:
                ctl._raise_hosts()
            except Exception:
                pass
    else:
        win.resize(geom.W, geom.H)
        win.show()
        win.raise_()
        win.activateWindow()
        win.setFocus()
    if want_update:
        try:
            from PyQt5.QtCore import QTimer

            QTimer.singleShot(400, lambda: win.go("set_update"))
            store.push_notif(
                "Update",
                "New Digivice build available — install from Update",
                "update",
            )
        except Exception:
            pass
    # Modem can take 10–25s after USB power — never block the UI for it.
    try:
        import threading

        wake_sig = getattr(win, "_modem_wake_signal", None)

        def _modem_bg() -> None:
            try:
                m = Sim7600()
                m.open(retries=12, retry_s=2.5)
                print(f"[handset] SIM7600 on {m.port}", flush=True)
                if wake_sig is not None:
                    wake_sig.emit(m)
            except Exception as e:
                print(f"[handset] SIM7600 offline ({e})", flush=True)

        threading.Thread(target=_modem_bg, name="modem-wake", daemon=True).start()
    except Exception as e:
        print(f"[handset] modem wake thread failed ({e})", flush=True)
    print("[handset] event loop starting", flush=True)
    code = app.exec_()
    if hasattr(win, "_spi_mirror") and win._spi_mirror:
        try:
            win._spi_mirror.stop()
        except Exception:
            pass
    if hasattr(win, "_multi_presenter") and win._multi_presenter:
        try:
            win._multi_presenter.stop()
        except Exception:
            pass
    try:
        win.releaseKeyboard()
    except Exception:
        pass
    if bridge:
        bridge.close()
    m = getattr(win, "get_modem", lambda: None)()
    if m:
        m.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
