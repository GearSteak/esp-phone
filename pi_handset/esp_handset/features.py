"""Feature pages that replace scaffolds (alarms, weather, games, media, etc.)."""

from __future__ import annotations

import os
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, date
from pathlib import Path
from typing import Callable, List, Optional

from PyQt5.QtCore import Qt, QTimer, QRectF
from PyQt5.QtGui import QColor, QPainter, QPen, QFont
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)

from esp_handset import store
from esp_handset.pages import page_chrome


# ----- Alarms -----
def make_alarms_page(on_back: Callable[[], None]) -> QWidget:
    from esp_handset.clock_ui import make_alarms_page as _make

    return _make(on_back)


def check_alarms_tick() -> Optional[str]:
    """Return label if an alarm matches current minute (once)."""
    now = datetime.now().strftime("%H:%M")
    key = f"fired_{now}"
    fired = store.load("alarms_fired.json", {})
    if fired.get(key):
        return None
    for a in store.load("alarms.json", []):
        if a.get("enabled", True) and a.get("time") == now:
            fired[key] = True
            # prune old
            store.save("alarms_fired.json", {key: True})
            return a.get("label") or "Alarm"
    return None


# ----- Notifications -----
def make_notifs_page(on_back: Callable[[], None]) -> QWidget:
    """Notification history (SMS / LoRa / alarms / etc. logged via store.push_notif)."""
    body = QWidget()
    lay = QVBoxLayout(body)
    lst = QListWidget()
    clear = QPushButton("Clear all")
    lay.addWidget(lst, 1)
    lay.addWidget(clear)

    def refresh():
        lst.clear()
        for n in store.load("notifs.json", []):
            flag = "" if n.get("read") else "• "
            lst.addItem(f"{flag}{n.get('at','')}  {n.get('title','')}: {n.get('body','')}")

    def do_clear():
        store.save("notifs.json", [])
        refresh()

    clear.clicked.connect(do_clear)
    refresh()
    body.refresh_notifs = refresh  # type: ignore[attr-defined]
    return page_chrome("Notifications", body, on_back)


# ----- Calendar -----
def make_calendar_page(on_back: Callable[[], None]) -> QWidget:
    from esp_handset.calendar_ui import make_calendar_page as _make

    return _make(on_back)


# ----- Security PIN -----
def make_security_page(on_back: Callable[[], None]) -> QWidget:
    body = QWidget()
    body.setStyleSheet("background:#0e1620; color:#e8eef5;")
    lay = QVBoxLayout(body)
    lay.setContentsMargins(6, 4, 6, 6)
    lay.setSpacing(6)
    title = QLabel("Security")
    title.setStyleSheet("font-size:15px; font-weight:700;")
    lay.addWidget(title)
    sec = store.load("security.json", {"pin": "", "lock_timeout_min": 0})
    status = QLabel("PIN is on" if sec.get("pin") else "PIN is off")
    status.setStyleSheet(
        "font-size:12px; font-weight:700; padding:8px;"
        " background:#16202c; border-radius:8px;"
    )
    pin = QLineEdit()
    pin.setEchoMode(QLineEdit.Password)
    pin.setPlaceholderText("New PIN (4+ digits)")
    pin.setMinimumHeight(32)
    pin.setStyleSheet(
        "font-size:12px; padding:8px; background:#16202c; color:#e8eef5;"
        " border:1px solid #243040; border-radius:8px;"
    )
    save = QPushButton("Set PIN")
    clear = QPushButton("Clear PIN")
    for b in (save, clear):
        b.setMinimumHeight(32)
        b.setStyleSheet(
            "QPushButton { font-size:12px; font-weight:700; padding:6px;"
            " background:#1e2a38; color:#e8eef5; border:1px solid #243040;"
            " border-radius:10px; }"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
    save.setStyleSheet(
        "QPushButton { font-size:12px; font-weight:700; color:#0a1218;"
        " background:#5ec4a8; border:none; border-radius:10px; }"
        'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
    )
    lay.addWidget(status)
    lay.addWidget(pin)
    lay.addWidget(save)
    lay.addWidget(clear)
    lay.addStretch(1)

    def do_save():
        p = pin.text().strip()
        if len(p) < 4 or not p.isdigit():
            status.setText("Need 4+ digits")
            return
        store.save("security.json", {"pin": p, "lock_timeout_min": 0})
        status.setText("PIN is on")
        pin.clear()
        store.push_notif("Security", "PIN updated", "security")

    def do_clear():
        store.save("security.json", {"pin": "", "lock_timeout_min": 0})
        status.setText("PIN is off")
        pin.clear()

    save.clicked.connect(do_save)
    clear.clicked.connect(do_clear)
    return page_chrome("Security", body, on_back, scroll=False)


def verify_pin_dialog(parent) -> bool:
    sec = store.load("security.json", {"pin": ""})
    expected = sec.get("pin") or ""
    if not expected:
        return True
    for _ in range(3):
        text, ok = QInputDialog.getText(
            parent, "Unlock", "Enter PIN:", QLineEdit.Password
        )
        if not ok:
            return False
        if text == expected:
            return True
        QMessageBox.warning(parent, "PIN", "Incorrect")
    return False


# ----- Converter -----
def make_convert_page(on_back: Callable[[], None]) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    kind = QComboBox()
    kind.addItems(
        [
            "C → F",
            "F → C",
            "km → mi",
            "mi → km",
            "kg → lb",
            "lb → kg",
            "m → ft",
            "ft → m",
        ]
    )
    inp = QLineEdit("0")
    out = QLabel("= 0")
    out.setStyleSheet("font-size:22px;font-weight:700;")
    go = QPushButton("Convert")
    lay.addWidget(kind)
    lay.addWidget(inp)
    lay.addWidget(go)
    lay.addWidget(out)
    lay.addStretch(1)

    def do():
        try:
            v = float(inp.text())
        except ValueError:
            out.setText("= ?")
            return
        k = kind.currentText()
        if k == "C → F":
            r = v * 9 / 5 + 32
        elif k == "F → C":
            r = (v - 32) * 5 / 9
        elif k == "km → mi":
            r = v * 0.621371
        elif k == "mi → km":
            r = v / 0.621371
        elif k == "kg → lb":
            r = v * 2.20462
        elif k == "lb → kg":
            r = v / 2.20462
        elif k == "m → ft":
            r = v * 3.28084
        else:
            r = v / 3.28084
        out.setText(f"= {r:.4g}")

    go.clicked.connect(do)
    return page_chrome("Converter", body, on_back)


# ----- Weather (Open-Meteo) — GPS / Wi-Fi / IP auto-locate -----
def make_weather_page(on_back: Callable[[], None], modem=None) -> QWidget:
    from esp_handset.weather_ui import make_weather_page as _make

    return _make(on_back, modem)


# ----- Steps (Pi SW-520D / tilt switch) -----
def make_steps_page(on_back: Callable[[], None], bridge=None) -> QWidget:
    del bridge  # Heltec gone — steps are local GPIO only
    from esp_handset.media_ui import media_btn, style_media_body

    _BG = "#0e1620"
    _TEXT = "#e8eef5"
    _MUTED = "#b8c4d4"
    _ACCENT = "#5ec4a8"

    body = QWidget()
    style_media_body(body)
    lay = QVBoxLayout(body)
    lay.setContentsMargins(8, 6, 8, 6)
    lay.setSpacing(6)

    title = QLabel("Steps today")
    title.setAlignment(Qt.AlignCenter)
    title.setStyleSheet(
        f"font-size:14px; font-weight:700; color:{_MUTED};"
    )

    big = QLabel("0")
    big.setAlignment(Qt.AlignCenter)
    big.setMinimumHeight(56)
    big.setStyleSheet(
        f"font-size:52px; font-weight:800; color:{_ACCENT};"
        f" background:{_BG}; padding:4px 0;"
    )

    status = QLabel("")
    status.setWordWrap(True)
    status.setAlignment(Qt.AlignCenter)
    status.setMinimumHeight(36)
    status.setStyleSheet(
        f"color:{_TEXT}; font-size:12px; font-weight:600;"
        f" background:#16202c; border:1px solid #243040;"
        f" border-radius:8px; padding:6px;"
    )

    row = QHBoxLayout()
    row.setSpacing(6)
    refresh = media_btn("Refresh")
    bump = media_btn("+1 test", primary=True)
    row.addWidget(refresh)
    row.addWidget(bump)

    row2 = QHBoxLayout()
    row2.setSpacing(6)
    reset = media_btn("Reset today")
    probe = media_btn("Probe")
    row2.addWidget(reset)
    row2.addWidget(probe)

    lay.addWidget(title)
    lay.addWidget(big)
    lay.addWidget(status)
    lay.addLayout(row)
    lay.addLayout(row2)
    lay.addStretch(1)

    def show_local() -> None:
        st = store.steps_state()
        big.setText(str(int(st.get("count") or 0)))
        try:
            from esp_handset.steps_pi import start_monitor, user_status

            start_monitor()
            status.setText(user_status())
        except Exception as e:
            status.setText(str(e)[:72])

    def do_refresh() -> None:
        show_local()

    def do_bump() -> None:
        store.add_steps(1)
        show_local()

    def do_reset() -> None:
        store.reset_steps_today()
        show_local()

    def do_probe() -> None:
        """Force a re-init and show live level (for wiring checks)."""
        try:
            from esp_handset import steps_pi
            from esp_handset.hw_pins import STEPS_BCM

            steps_pi._monitor = None  # type: ignore[attr-defined]
            mon = steps_pi.start_monitor()
            if mon is None:
                status.setText(f"No sensor (BCM {STEPS_BCM})")
            else:
                show_local()
                status.setText(steps_pi.monitor_status() + " · shake now")
        except Exception as e:
            status.setText(str(e)[:72])

    refresh.clicked.connect(do_refresh)
    bump.clicked.connect(do_bump)
    reset.clicked.connect(do_reset)
    probe.clicked.connect(do_probe)
    show_local()
    tick = QTimer(body)
    tick.timeout.connect(show_local)
    tick.start(1500)
    page = page_chrome("Steps", body, on_back, scroll=False)
    page.refresh_steps = show_local  # type: ignore[attr-defined]
    return page


# ----- Share GPS -----
def make_share_gps_page(modem, on_back: Callable[[], None], on_status) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    to = QLineEdit()
    to.setPlaceholderText("SMS number")
    info = QLabel("Enable GPS then Share")
    info.setWordWrap(True)
    share = QPushButton("Share via SMS")
    poll = QPushButton("Refresh GPS")
    lay.addWidget(info)
    lay.addWidget(to)
    lay.addWidget(poll)
    lay.addWidget(share)
    lay.addStretch(1)
    fix = {"text": ""}

    def do_poll():
        if not modem:
            info.setText("SIM7600 not connected")
            return
        try:
            modem.gps_on()
            fix = modem.gps_fix()
            if fix.get("ok"):
                fix["text"] = fix.get("raw") or ""
                info.setText(fix.get("detail") or fix.get("summary") or "")
            elif fix.get("searching"):
                fix["text"] = fix.get("raw") or ""
                info.setText("Searching…\n" + (fix.get("detail") or ""))
            else:
                g = modem.gps_info() or "no fix"
                fix["text"] = g
                info.setText(g)
        except Exception as e:
            info.setText(str(e).strip() or "GPS error")

    def do_share():
        num = to.text().strip()
        if not num or not modem:
            QMessageBox.warning(body, "Share", "Need number + modem")
            return
        # Try parse CGPSINFO: lat,N,lon,E,...
        raw = fix["text"]
        link = f"GPS: {raw}"
        if "+CGPSINFO:" in raw:
            parts = raw.split(":", 1)[-1].strip().split(",")
            if len(parts) >= 4 and parts[0] and parts[2]:
                # crude ddmm.mmmm → rough maps query
                link = (
                    "https://maps.google.com/?q="
                    + urllib.parse.quote(f"{parts[0]}{parts[1]},{parts[2]}{parts[3]}")
                )
        try:
            ok = modem.send_sms(num, link[:160])
        except Exception as e:
            QMessageBox.warning(body, "Share", str(e))
            return
        if ok:
            on_status("Location SMS sent")
            store.push_notif("GPS", f"Shared to {num}", "gps")
        else:
            QMessageBox.warning(body, "Share", "SMS failed")

    poll.clicked.connect(do_poll)
    share.clicked.connect(do_share)
    return page_chrome("Share GPS", body, on_back)


# ----- Voice notes -----
def make_recorder_page(on_back: Callable[[], None], on_status) -> QWidget:
    from esp_handset.media_ui import (
        media_btn,
        media_empty,
        media_header,
        media_list,
        style_media_body,
    )

    body = QWidget()
    style_media_body(body)
    lay = QVBoxLayout(body)
    lay.setContentsMargins(4, 2, 4, 2)
    lay.setSpacing(4)
    lay.addWidget(
        media_header("◉", "Voice")
    )
    lst = media_list()
    empty = media_empty("No voice notes yet.\nRecord a quick clip below.")
    empty.hide()
    lay.addWidget(lst, 1)
    lay.addWidget(empty)
    row = QHBoxLayout()
    row.setSpacing(4)
    rec = media_btn("● Record 5s", primary=True)
    play = media_btn("▶ Play")
    row.addWidget(rec, 2)
    row.addWidget(play, 1)
    lay.addLayout(row)

    def refresh():
        store.ensure()
        lst.clear()
        files = [
            p
            for p in sorted(store.VOICE.glob("*"), reverse=True)
            if p.suffix.lower() in (".wav", ".mp3", ".ogg")
        ]
        for p in files:
            lst.addItem(p.name)
        if not files:
            lst.hide()
            empty.show()
        else:
            empty.hide()
            lst.show()

    def do_rec():
        store.ensure()
        out = store.VOICE / f"note_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        cmd = None
        if _which("arecord"):
            cmd = ["arecord", "-d", "5", "-f", "cd", str(out)]
        elif _which("ffmpeg"):
            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "alsa",
                "-i",
                "default",
                "-t",
                "5",
                str(out),
            ]
        if not cmd:
            QMessageBox.warning(body, "Record", "Install arecord or ffmpeg")
            return
        on_status("Recording…")
        try:
            subprocess.run(cmd, check=False, capture_output=True, timeout=15)
        except Exception as e:
            QMessageBox.warning(body, "Record", str(e))
            return
        refresh()
        on_status(f"Saved {out.name}")

    def do_play():
        items = lst.selectedItems()
        if not items:
            return
        path = store.VOICE / items[0].text()
        for bin_ in ("mpv", "ffplay", "aplay", "vlc"):
            if _which(bin_):
                subprocess.Popen(
                    [bin_, str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
        QMessageBox.warning(body, "Play", "No player (mpv/ffplay/aplay)")

    rec.clicked.connect(do_rec)
    play.clicked.connect(do_play)
    refresh()
    return page_chrome("Voice", body, on_back, scroll=False)


def _which(name: str) -> Optional[str]:
    from shutil import which

    return which(name)


# ----- File media browsers -----
def make_file_media_page(
    title: str,
    folder: Path,
    patterns: tuple,
    on_back: Callable[[], None],
    open_cmd: Optional[List[str]] = None,
) -> QWidget:
    from esp_handset.media_ui import make_library_page

    glyphs = {
        "Music": "♪",
        "Videos": "▶",
        "Audiobooks": "♬",
    }
    kinds = {
        "Music": "tracks",
        "Videos": "videos",
        "Audiobooks": "books",
    }
    opens = {
        "Music": "Play",
        "Videos": "Play",
        "Audiobooks": "Play",
    }
    return make_library_page(
        title=title,
        glyph=glyphs.get(title, "▤"),
        folder=folder,
        patterns=tuple(patterns),
        on_back=on_back,
        kind_label=kinds.get(title, "files"),
        open_cmd=open_cmd,
        open_label=opens.get(title, "Open"),
    )


def make_ebook_page(on_back: Callable[[], None]) -> QWidget:
    from esp_handset.media_ui import (
        media_btn,
        media_empty,
        media_header,
        media_list,
        style_media_body,
        _MUTED,
        _SURFACE,
        _TEXT,
        _BORDER,
    )

    body = QWidget()
    style_media_body(body)
    lay = QVBoxLayout(body)
    lay.setContentsMargins(4, 2, 4, 2)
    lay.setSpacing(4)
    lay.addWidget(media_header("▤", "Ebooks"))

    lst = media_list()
    lst.setMaximumHeight(72)
    empty = media_empty("No text books yet.\nPut .txt / .md in Books/")
    empty.hide()
    text = QTextEdit()
    text.setReadOnly(True)
    text.setStyleSheet(
        f"QTextEdit {{ background:{_SURFACE}; color:{_TEXT}; border:1px solid {_BORDER};"
        f" border-radius:8px; font-size:12px; padding:6px; }}"
    )
    open_btn = media_btn("Read", primary=True)
    lay.addWidget(lst)
    lay.addWidget(empty)
    lay.addWidget(open_btn)
    lay.addWidget(text, 1)

    def refresh():
        store.ensure()
        lst.clear()
        files = [
            p
            for p in sorted(store.BOOKS.glob("*.*"))
            if p.suffix.lower() in (".txt", ".md", ".text")
        ]
        for p in files:
            lst.addItem(p.name)
        if not files:
            lst.hide()
            empty.show()
        else:
            empty.hide()
            lst.show()

    def do_read():
        items = lst.selectedItems()
        if not items:
            return
        path = store.BOOKS / items[0].text()
        try:
            text.setPlainText(path.read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            text.setPlainText(str(e))

    open_btn.clicked.connect(do_read)
    lst.itemActivated.connect(lambda _=None: do_read())
    refresh()
    return page_chrome("Ebooks", body, on_back, scroll=False)


# ----- Accounts / Email -----


def make_sounds_page(on_back: Callable[[], None]) -> QWidget:
    """Deprecated — Audio lives under Settings → Audio (set_debug)."""
    from esp_handset.pages import make_debug_page

    return make_debug_page(on_back)


def make_accounts_page(on_back: Callable[[], None]) -> QWidget:
    from esp_handset.accounts_ui import make_sip_account_page

    return make_sip_account_page(on_back)


def make_email_page(on_back: Callable[[], None]) -> QWidget:
    from esp_handset.email_ui import make_email_page as _make

    return _make(on_back)
