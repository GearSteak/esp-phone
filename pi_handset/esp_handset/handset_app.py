#!/usr/bin/env python3
"""ESP Digivice handset — Waveshare 2\" LCD (240×320) + hard-button nav.

Cellular / SMS / GPS: SIM7600G-H HAT (AT over USB).
Nav: Up/Down/Left/Right/Confirm/Back/Home (digi-buttons-inputd). Typing: OSK.
LoRa: Heltec USB CDC (optional notify TFT). Exit to Linux Desktop for emulators/apt.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal, QEvent, Qt
from PyQt5.QtWidgets import QApplication, QLabel, QMessageBox, QLineEdit, QTextEdit, QPlainTextEdit


class _KioskKeyFilter(QObject):
    """Route nav keys to Digivice when focus is not in a text field.

    USB keyboards often land focus on labels/status chrome under X11/Wayland.
    Exit keys always reach the shell so Digivice can be left.
    """

    def __init__(self, shell: object):
        super().__init__(shell)
        self._shell = shell

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() != QEvent.KeyPress:
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
        w = QApplication.focusWidget()
        if isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit)):
            # Triple-Back (Esc) still leaves Digivice
            if key == Qt.Key_Escape:
                self._shell.keyPressEvent(event)
                return True
            return False
        nav = {
            Qt.Key_Left,
            Qt.Key_Right,
            Qt.Key_Up,
            Qt.Key_Down,
            Qt.Key_Return,
            Qt.Key_Enter,
            Qt.Key_Escape,
            Qt.Key_Home,
            Qt.Key_F2,
        }
        if key not in nav:
            return False
        # Games keep their own handlers via focused game widget
        if w is not None and w.__class__.__module__.endswith("games_ui"):
            return False
        self._shell.keyPressEvent(event)
        return True


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from esp_handset.bridge import EspBridge  # noqa: E402
from esp_handset.sim7600 import Sim7600  # noqa: E402
from esp_handset import apps as handset_apps  # noqa: E402
from esp_handset import pages  # noqa: E402
from esp_handset import features  # noqa: E402
from esp_handset import games_ui  # noqa: E402
from esp_handset import ollama_chat  # noqa: E402
from esp_handset import store  # noqa: E402
from esp_handset import display_geom as geom  # noqa: E402
from esp_handset.shell import (  # noqa: E402
    CALLS_APPS,
    CLOCK_APPS,
    GAMES_APPS,
    MEDIA_APPS,
    SETTINGS_APPS,
    SMS_APPS,
    TOOLS_APPS,
    PhoneShell,
)

DATA = Path.home() / ".esp-handset"


class BridgeSignals(QObject):
    line = pyqtSignal(str)
    sms = pyqtSignal(str, str)


def build_app(bridge: Optional[EspBridge], modem: Optional[Sim7600]) -> PhoneShell:
    shell = PhoneShell()
    DATA.mkdir(parents=True, exist_ok=True)

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
    # Digivice: no on-screen toast banners — ESP ST7735 shows alerts
    if bridge:
        store.set_esp_notif_handler(
            lambda t, b, k: bridge.notif(t, b, k)  # type: ignore[union-attr]
        )
    else:
        store.set_toast_handler(lambda t, b, k: shell.show_toast(t, b, k))

    # Radial submenus (main → folder → app)
    shell.register_page(
        "folder_calls",
        shell.build_folder_keyed("folder_calls", "Calls", CALLS_APPS),
    )
    shell.register_page(
        "folder_sms",
        shell.build_folder_keyed("folder_sms", "SMS", SMS_APPS),
    )
    shell.register_page(
        "folder_clock",
        shell.build_folder_keyed("folder_clock", "Clock", CLOCK_APPS),
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
    shell.register_page(
        "phone",
        pages.make_phone_page(back, status, on_call_log=lambda: shell.go("call_log")),
    )
    sms_page = pages.make_sms_page(modem, back, status)
    shell.register_page("messages", sms_page)

    from PyQt5.QtWidgets import QLineEdit, QPushButton, QVBoxLayout, QWidget

    def open_dial(number: str) -> None:
        shell.go("phone")
        for child in shell.pages["phone"].findChildren(QLineEdit):
            child.setText(number)
            break

    shell.register_page("contacts", pages.make_contacts_page(back, open_dial))
    shell.register_page("call_log", pages.make_call_log_page(back))
    shell.register_page("camera", pages.make_camera_page(back, status))
    shell.register_page("gallery", pages.make_camera_page(back, status))
    lora_page = pages.make_lora_page(bridge, back, status)
    shell.register_page("lora", lora_page)
    shell.register_page("gps", pages.make_gps_page(modem, back, status))
    shell.register_page("notes", pages.make_notes_page(back))
    shell.register_page("todos", pages.make_todos_page(back))
    shell.register_page("clock_face", pages.make_clock_page(back))
    shell.register_page("calc", pages.make_calc_page(back))
    shell.register_page("ai", ollama_chat.make_ollama_page(back))
    shell.register_page(
        "settings",
        pages.make_settings_hub(back, open_page, on_linux),
    )
    shell.register_page("set_network", pages.make_network_page(modem, back, status))
    shell.register_page("set_about", pages.make_about_page(modem, back))
    shell.register_page("help", pages.make_help_page(back))
    shell.register_page(
        "set_appearance", pages.make_appearance_page(shell, back)
    )

    def browser_open():
        try:
            handset_apps.open_browser()
            status("Browser…")
        except Exception:
            shell.go("browser_stub")

    shell.register_page(
        "browser_stub",
        pages.stub_page(
            "Browser",
            "Install a light browser from Linux Desktop:\n  sudo apt install midori\n"
            "Then reopen Browser from home.",
            back,
        ),
    )

    def launch_page(title: str, blurb: str, action):
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.addWidget(QLabel(blurb))
        btn = QPushButton(f"Open {title}")
        btn.clicked.connect(action)
        lay.addWidget(btn)
        lay.addStretch(1)
        return pages.page_chrome(title, body, back)

    shell.register_page(
        "browser",
        launch_page(
            "Browser",
            "Lightweight web (midori/epiphany if installed).",
            browser_open,
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
    steps_page = features.make_steps_page(back, bridge)
    shell.register_page("steps", steps_page)
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
    shell.register_page("snake", games_ui.make_snake(back))
    shell.register_page("pong", games_ui.make_pong(back))
    shell.register_page("tetris", games_ui.make_tetris(back))
    shell.register_page("solitaire", games_ui.make_solitaire(back))
    shell.register_page("uno", games_ui.make_uno(back))
    shell.register_page("set_security", features.make_security_page(back))
    shell.register_page("set_accounts", features.make_accounts_page(back))
    shell.register_page("set_sounds", features.make_sounds_page(back))
    shell.register_page("stub", pages.stub_page("App", "Unknown app key.", back))

    # Bridge events
    signals = BridgeSignals()

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
            log = getattr(lora_page, "lora_log", None)
            if log is not None:
                log.append(line)
            status(line[:48])
            if line.startswith("LORA RX"):
                store.push_notif("LoRa", line[7:].strip()[:80], "lora")
                ref = getattr(notifs_page, "refresh_notifs", None)
                if callable(ref):
                    ref()
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
            if "SIM7600" not in shell.signal_lab.text():
                status(line[:40])

    def on_sms(num: str, text: str) -> None:
        threads = pages._load_json(pages.SMS_LOG, {})
        threads.setdefault(num, []).append(text)
        pages._save_json(pages.SMS_LOG, threads)
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

    if modem:
        modem.on_sms(lambda n, t: signals.sms.emit(n, t))
        try:
            status(modem.signal() or "SIM7600")
        except Exception:
            status("SIM7600")

    from PyQt5.QtCore import QTimer

    def _alarm_poll():
        label = features.check_alarms_tick()
        if label:
            store.push_notif("Alarm", label, "alarm")
            ref = getattr(notifs_page, "refresh_notifs", None)
            if callable(ref):
                ref()
            status(f"Alarm: {label}")
            # Toast already shown via push_notif; no modal dialog

    atimer = QTimer(shell)
    atimer.timeout.connect(_alarm_poll)
    atimer.start(15_000)

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
    store.ensure()
    bridge: Optional[EspBridge] = None
    modem: Optional[Sim7600] = None
    try:
        bridge = EspBridge()
        bridge.open()
    except Exception as e:
        print(f"[handset] LoRa ESP offline ({e})", flush=True)
        bridge = None
    try:
        modem = Sim7600()
        modem.open()
    except Exception as e:
        print(f"[handset] SIM7600 offline ({e})", flush=True)
        modem = None

    win = build_app(bridge, modem)
    app.installEventFilter(_KioskKeyFilter(win))
    # Skip PIN unlock in kiosk by default (set ESP_HANDSET_SKIP_PIN=0 to require)
    if os.environ.get("ESP_HANDSET_SKIP_PIN", "1").strip() not in ("1", "true", "yes"):
        if not features.verify_pin_dialog(win):
            print("[handset] PIN cancelled — exit", flush=True)
            if bridge:
                bridge.close()
            if modem:
                modem.close()
            return 1
    print("[handset] showing UI…", flush=True)
    kiosk = os.environ.get("ESP_HANDSET_KIOSK", "").strip() in ("1", "true", "yes")
    if kiosk:
        # Fullscreen Digivice on SPI/Unknown panel (not multi-host paint)
        geom.apply_kiosk(win)
    else:
        win.resize(geom.W, geom.H)
        win.show()
    win.raise_()
    win.activateWindow()
    win.setFocus()
    # Never grabKeyboard — blocks USB keyboard / recovery
    print("[handset] event loop starting (panel fullscreen)", flush=True)
    code = app.exec_()
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
    if modem:
        modem.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
