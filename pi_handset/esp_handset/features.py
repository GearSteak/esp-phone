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
    QTimeEdit,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)

from esp_handset import store
from esp_handset.pages import page_chrome, CONFIG


# ----- Alarms -----
def make_alarms_page(on_back: Callable[[], None]) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    lst = QListWidget()
    time_edit = QTimeEdit()
    time_edit.setDisplayFormat("HH:mm")
    label_in = QLineEdit()
    label_in.setPlaceholderText("Label")
    row = QHBoxLayout()
    add = QPushButton("Add alarm")
    rem = QPushButton("Remove selected")
    row.addWidget(add)
    row.addWidget(rem)
    lay.addWidget(lst, 1)
    lay.addWidget(QLabel("Time"))
    lay.addWidget(time_edit)
    lay.addWidget(label_in)
    lay.addLayout(row)
    tip = QLabel("In-app check while handset is open (full systemd timers later).")
    tip.setWordWrap(True)
    tip.setStyleSheet("color:#9ab;font-size:11px;")
    lay.addWidget(tip)

    def refresh():
        lst.clear()
        for a in store.load("alarms.json", []):
            on = "ON" if a.get("enabled", True) else "off"
            lst.addItem(f"{a.get('time','??:??')}  {a.get('label','')}  [{on}]")

    def do_add():
        t = time_edit.time().toString("HH:mm")
        items = store.load("alarms.json", [])
        items.append(
            {"time": t, "label": label_in.text().strip() or "Alarm", "enabled": True}
        )
        store.save("alarms.json", items)
        label_in.clear()
        refresh()

    def do_rem():
        row_i = lst.currentRow()
        items = store.load("alarms.json", [])
        if 0 <= row_i < len(items):
            items.pop(row_i)
            store.save("alarms.json", items)
            refresh()

    add.clicked.connect(do_add)
    rem.clicked.connect(do_rem)
    refresh()
    return page_chrome("Alarms", body, on_back)


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
    body = QWidget()
    lay = QVBoxLayout(body)
    lst = QListWidget()
    title = QLineEdit()
    title.setPlaceholderText("Event title")
    day = QLineEdit(date.today().isoformat())
    day.setPlaceholderText("YYYY-MM-DD")
    add = QPushButton("Add event")
    rem = QPushButton("Remove selected")
    lay.addWidget(QLabel(date.today().strftime("%A %d %B %Y")))
    lay.addWidget(lst, 1)
    lay.addWidget(day)
    lay.addWidget(title)
    row = QHBoxLayout()
    row.addWidget(add)
    row.addWidget(rem)
    lay.addLayout(row)

    def refresh():
        lst.clear()
        events = sorted(store.load("calendar.json", []), key=lambda e: e.get("date", ""))
        for e in events:
            lst.addItem(f"{e.get('date','')}  {e.get('title','')}")

    def do_add():
        events = store.load("calendar.json", [])
        events.append({"date": day.text().strip(), "title": title.text().strip() or "Event"})
        store.save("calendar.json", events)
        title.clear()
        refresh()

    def do_rem():
        i = lst.currentRow()
        events = sorted(store.load("calendar.json", []), key=lambda e: e.get("date", ""))
        if 0 <= i < len(events):
            # remove matching
            target = events[i]
            all_e = store.load("calendar.json", [])
            all_e = [e for e in all_e if e != target]
            store.save("calendar.json", all_e)
            refresh()

    add.clicked.connect(do_add)
    rem.clicked.connect(do_rem)
    refresh()
    return page_chrome("Calendar", body, on_back)


# ----- Security PIN -----
def make_security_page(on_back: Callable[[], None]) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    sec = store.load("security.json", {"pin": "", "lock_timeout_min": 0})
    status = QLabel("PIN is set" if sec.get("pin") else "PIN disabled")
    pin = QLineEdit()
    pin.setEchoMode(QLineEdit.Password)
    pin.setPlaceholderText("New PIN (digits)")
    save = QPushButton("Set PIN")
    clear = QPushButton("Clear PIN")
    lay.addWidget(status)
    lay.addWidget(pin)
    lay.addWidget(save)
    lay.addWidget(clear)
    lay.addStretch(1)

    def do_save():
        p = pin.text().strip()
        if len(p) < 4:
            QMessageBox.warning(body, "PIN", "Use at least 4 digits")
            return
        store.save("security.json", {"pin": p, "lock_timeout_min": 0})
        status.setText("PIN is set")
        pin.clear()
        store.push_notif("Security", "PIN updated", "security")

    def do_clear():
        store.save("security.json", {"pin": "", "lock_timeout_min": 0})
        status.setText("PIN disabled")
        pin.clear()

    save.clicked.connect(do_save)
    clear.clicked.connect(do_clear)
    return page_chrome("Security", body, on_back)


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


# ----- Weather (Open-Meteo) -----
def make_weather_page(on_back: Callable[[], None], modem=None) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    lat = QLineEdit("49.28")
    lon = QLineEdit("-123.12")
    lat.setPlaceholderText("Latitude")
    lon.setPlaceholderText("Longitude")
    out = QLabel("Tap Fetch")
    out.setWordWrap(True)
    fetch = QPushButton("Fetch weather")
    lay.addWidget(QLabel("Lat / Lon (or use last GPS later)"))
    lay.addWidget(lat)
    lay.addWidget(lon)
    lay.addWidget(fetch)
    lay.addWidget(out, 1)

    def do_fetch():
        try:
            la = float(lat.text())
            lo = float(lon.text())
            url = (
                "https://api.open-meteo.com/v1/forecast?"
                + urllib.parse.urlencode(
                    {
                        "latitude": la,
                        "longitude": lo,
                        "current_weather": "true",
                    }
                )
            )
            with urllib.request.urlopen(url, timeout=8) as resp:
                import json

                data = json.loads(resp.read().decode())
            cw = data.get("current_weather") or {}
            out.setText(
                f"Temp: {cw.get('temperature')}°C\n"
                f"Wind: {cw.get('windspeed')} km/h\n"
                f"Code: {cw.get('weathercode')}\n"
                f"Time: {cw.get('time')}"
            )
        except Exception as e:
            out.setText(f"Failed (need internet):\n{e}")

    fetch.clicked.connect(do_fetch)
    return page_chrome("Weather", body, on_back)


# ----- Steps (Heltec SW-520D) -----
def make_steps_page(on_back: Callable[[], None], bridge=None) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    big = QLabel("0")
    big.setAlignment(Qt.AlignCenter)
    big.setStyleSheet("font-size: 36px; font-weight: bold;")
    hint = QLabel("SW-520D tilt on Heltec\n(crude pedometer)")
    hint.setWordWrap(True)
    hint.setAlignment(Qt.AlignCenter)
    refresh = QPushButton("Refresh")
    reset = QPushButton("Reset today")
    lay.addStretch(1)
    lay.addWidget(big)
    lay.addWidget(hint)
    lay.addWidget(refresh)
    lay.addWidget(reset)
    lay.addStretch(1)

    def show_local() -> None:
        st = store.steps_state()
        big.setText(str(int(st.get("count") or 0)))

    def do_refresh() -> None:
        show_local()
        if bridge:
            try:
                bridge.steps_query()
            except Exception:
                pass

    def do_reset() -> None:
        store.reset_steps_today()
        show_local()
        if bridge:
            try:
                bridge.steps_reset()
            except Exception:
                pass

    refresh.clicked.connect(do_refresh)
    reset.clicked.connect(do_reset)
    show_local()
    page = page_chrome("Steps", body, on_back)
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
            g = modem.gps_info() or "no fix"
            fix["text"] = g
            info.setText(g)
        except Exception as e:
            info.setText(str(e))

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
    body = QWidget()
    lay = QVBoxLayout(body)
    lst = QListWidget()
    rec = QPushButton("Record 5s")
    play = QPushButton("Play selected")
    lay.addWidget(lst, 1)
    lay.addWidget(rec)
    lay.addWidget(play)
    tip = QLabel("Uses arecord/ffmpeg if present → ~/VoiceNotes")
    tip.setStyleSheet("color:#9ab;font-size:11px;")
    lay.addWidget(tip)
    proc = {"p": None}

    def refresh():
        store.ensure()
        lst.clear()
        for p in sorted(store.VOICE.glob("*"), reverse=True):
            if p.suffix.lower() in (".wav", ".mp3", ".ogg"):
                lst.addItem(p.name)

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
    return page_chrome("Voice notes", body, on_back)


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
    body = QWidget()
    lay = QVBoxLayout(body)
    lst = QListWidget()
    open_btn = QPushButton("Open")
    refresh = QPushButton("Refresh")
    lay.addWidget(QLabel(str(folder)))
    lay.addWidget(lst, 1)
    row = QHBoxLayout()
    row.addWidget(open_btn)
    row.addWidget(refresh)
    lay.addLayout(row)

    def do_refresh():
        folder.mkdir(parents=True, exist_ok=True)
        lst.clear()
        files = []
        for pat in patterns:
            files.extend(folder.glob(pat))
        for p in sorted(set(files), key=lambda x: x.name.lower()):
            lst.addItem(p.name)

    def do_open():
        items = lst.selectedItems()
        if not items:
            return
        path = folder / items[0].text()
        if open_cmd:
            subprocess.Popen(
                open_cmd + [str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        # text ebook
        if path.suffix.lower() in (".txt", ".md", ".text"):
            # handled by caller registration for ebooks reader
            pass
        for bin_ in ("xdg-open", "mpv", "vlc", "ffplay"):
            if _which(bin_):
                subprocess.Popen(
                    [bin_, str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return

    open_btn.clicked.connect(do_open)
    refresh.clicked.connect(do_refresh)
    do_refresh()
    return page_chrome(title, body, on_back)


def make_ebook_page(on_back: Callable[[], None]) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    lst = QListWidget()
    text = QTextEdit()
    text.setReadOnly(True)
    open_btn = QPushButton("Read selected")
    lay.addWidget(QLabel(str(store.BOOKS)))
    lay.addWidget(lst)
    lay.addWidget(open_btn)
    lay.addWidget(text, 1)

    def refresh():
        store.ensure()
        lst.clear()
        for p in sorted(store.BOOKS.glob("*.*")):
            if p.suffix.lower() in (".txt", ".md", ".text"):
                lst.addItem(p.name)

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
    refresh()
    return page_chrome("Ebooks", body, on_back)


# ----- Accounts / Sounds / Email -----
def make_accounts_page(on_back: Callable[[], None]) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    server = QLineEdit()
    user = QLineEdit()
    password = QLineEdit()
    password.setEchoMode(QLineEdit.Password)
    display = QLineEdit()
    email_user = QLineEdit()
    email_pass = QLineEdit()
    email_pass.setEchoMode(QLineEdit.Password)
    save = QPushButton("Save SIP + email prefs")
    # load sip.env
    vals = {"SIP_SERVER": "", "SIP_USER": "", "SIP_PASS": "", "SIP_DISPLAY": ""}
    path = CONFIG if CONFIG.exists() else store.DATA / "sip.env"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip()
    server.setText(vals.get("SIP_SERVER", ""))
    user.setText(vals.get("SIP_USER", ""))
    password.setText(vals.get("SIP_PASS", ""))
    display.setText(vals.get("SIP_DISPLAY", ""))
    em = store.load("email.json", {"user": "", "pass": "", "host": "imap.gmail.com"})
    email_user.setText(em.get("user", ""))
    email_pass.setText(em.get("pass", ""))

    for lab, w in [
        ("SIP server", server),
        ("SIP user", user),
        ("SIP pass", password),
        ("Display name", display),
        ("Email user", email_user),
        ("Email app password", email_pass),
    ]:
        lay.addWidget(QLabel(lab))
        lay.addWidget(w)
    lay.addWidget(save)
    lay.addStretch(1)

    def do_save():
        store.ensure()
        dest = Path("/etc/esp-handset/sip.env")
        content = (
            f"SIP_SERVER={server.text().strip()}\n"
            f"SIP_USER={user.text().strip()}\n"
            f"SIP_PASS={password.text().strip()}\n"
            f"SIP_DISPLAY={display.text().strip() or 'ESP Handset'}\n"
        )
        try:
            dest.write_text(content)
        except PermissionError:
            (store.DATA / "sip.env").write_text(content)
            QMessageBox.information(
                body,
                "Accounts",
                "Saved to ~/.esp-handset/sip.env (no permission for /etc).\n"
                "Copy with sudo if needed.",
            )
        store.save(
            "email.json",
            {
                "user": email_user.text().strip(),
                "pass": email_pass.text().strip(),
                "host": "imap.gmail.com",
            },
        )
        store.push_notif("Accounts", "Credentials saved", "settings")

    save.clicked.connect(do_save)
    return page_chrome("Accounts", body, on_back)


def make_sounds_page(on_back: Callable[[], None]) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    prefs = store.load("sounds.json", {"profile": "Normal", "enabled": True})
    profile = QComboBox()
    profile.addItems(["Silent", "Normal", "Loud", "Outdoor"])
    profile.setCurrentText(prefs.get("profile", "Normal"))
    enabled = QCheckBox("Sounds enabled")
    enabled.setChecked(bool(prefs.get("enabled", True)))
    test = QPushButton("Test notify sound")
    save = QPushButton("Save")
    lay.addWidget(QLabel("Profile"))
    lay.addWidget(profile)
    lay.addWidget(enabled)
    lay.addWidget(test)
    lay.addWidget(save)
    lay.addWidget(
        QLabel("Volume keys still go through esp-keyd → PipeWire.")
    )
    lay.addStretch(1)

    def do_save():
        store.save(
            "sounds.json",
            {"profile": profile.currentText(), "enabled": enabled.isChecked()},
        )

    def do_test():
        if not enabled.isChecked() or profile.currentText() == "Silent":
            QMessageBox.information(body, "Sounds", "Silent / disabled")
            return
        # paplay or speaker-test
        if _which("paplay") and Path("/usr/share/sounds/freedesktop/stereo/message.oga").exists():
            subprocess.Popen(
                ["paplay", "/usr/share/sounds/freedesktop/stereo/message.oga"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif _which("speaker-test"):
            subprocess.Popen(
                ["speaker-test", "-t", "sine", "-f", "880", "-l", "1"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            QMessageBox.information(body, "Sounds", "No paplay/speaker-test")

    save.clicked.connect(do_save)
    test.clicked.connect(do_test)
    return page_chrome("Sounds", body, on_back)


def make_email_page(on_back: Callable[[], None]) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    lst = QListWidget()
    fetch = QPushButton("Fetch INBOX (IMAP)")
    lay.addWidget(lst, 1)
    lay.addWidget(fetch)
    tip = QLabel("Set Accounts → Email app password first (Gmail IMAP).")
    tip.setWordWrap(True)
    tip.setStyleSheet("color:#9ab;")
    lay.addWidget(tip)

    def do_fetch():
        em = store.load("email.json", {})
        user = em.get("user") or ""
        password = em.get("pass") or ""
        host = em.get("host") or "imap.gmail.com"
        if not user or not password:
            QMessageBox.warning(body, "Email", "Configure Accounts first")
            return
        try:
            import imaplib
            import email
            from email.header import decode_header

            M = imaplib.IMAP4_SSL(host, 993)
            M.login(user, password)
            M.select("INBOX")
            typ, data = M.search(None, "ALL")
            ids = data[0].split()[-15:]
            lst.clear()
            for num in reversed(ids):
                typ, msg_data = M.fetch(num, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM)])")
                raw = msg_data[0][1].decode("utf-8", errors="replace")
                subj = ""
                for line in raw.splitlines():
                    if line.lower().startswith("subject:"):
                        subj = line.split(":", 1)[-1].strip()
                lst.addItem(subj or f"Message {num.decode()}")
            M.logout()
            store.push_notif("Email", f"Fetched {lst.count()} headers", "email")
        except Exception as e:
            QMessageBox.warning(body, "Email", str(e))

    fetch.clicked.connect(do_fetch)
    return page_chrome("Email", body, on_back)
