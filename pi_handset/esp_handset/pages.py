"""Handset app pages — ESP Phone feature parity (wired + stubs)."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QTextCursor
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from esp_handset import pi_camera

DATA = Path.home() / ".esp-handset"
CONTACTS = DATA / "contacts.json"
SMS_LOG = DATA / "sms.json"
NOTES = DATA / "notes.json"
TODOS = DATA / "todos.json"
CALL_LOG = DATA / "call_log.json"
PHOTOS = Path.home() / "Pictures" / "phone"
CONFIG = Path("/etc/esp-handset/sip.env")
if not CONFIG.exists():
    CONFIG = DATA / "sip.env"


def _load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return default
    return default


def _save_json(path: Path, data) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def page_chrome(
    title: str,
    body: QWidget,
    on_back: Optional[Callable[[], None]] = None,
    *,
    scroll: bool = True,
) -> QWidget:
    """Compact chrome for Digivice panel; body scrolls on 240×320 by default."""
    from PyQt5.QtWidgets import QSizePolicy

    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(4, 3, 4, 3)
    lay.setSpacing(3)
    head = QHBoxLayout()
    head.setSpacing(4)
    if on_back:
        back = QPushButton("←")
        back.setFixedWidth(28)
        back.setFixedHeight(26)
        back.clicked.connect(on_back)
        head.addWidget(back)
    lab = QLabel(title)
    lab.setStyleSheet("font-size: 12px; font-weight: 700;")
    head.addWidget(lab, 1)
    lay.addLayout(head)

    if scroll:
        area = QScrollArea()
        area.setObjectName("digiScroll")
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        area.setFrameShape(QFrame.NoFrame)
        area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 8px; background: #121820; margin: 0; }"
            "QScrollBar::handle:vertical {"
            "  background: #4a6a88; min-height: 28px; border-radius: 3px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        area.setWidget(body)
        lay.addWidget(area, 1)
    else:
        lay.addWidget(body, 1)
    return w


def stub_page(title: str, blurb: str, on_back: Callable[[], None]) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    msg = QLabel(blurb)
    msg.setObjectName("stubBody")
    msg.setWordWrap(True)
    msg.setStyleSheet("color: #9ab; font-size: 14px;")
    lay.addWidget(msg)
    lay.addStretch(1)
    tip = QLabel("Scaffold — behavior will match the ESP Phone app over time.")
    tip.setWordWrap(True)
    tip.setStyleSheet("color: #678; font-size: 11px;")
    lay.addWidget(tip)
    return page_chrome(title, body, on_back)


def make_phone_page(
    on_back, on_status, on_call_log: Optional[Callable[[], None]] = None
) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    dial = QLineEdit()
    dial.setPlaceholderText("Number")
    dial.setStyleSheet("font-size: 14px; padding: 6px;")
    lay.addWidget(dial)
    row = QHBoxLayout()
    call = QPushButton("Call")
    end = QPushButton("End")
    row.addWidget(call)
    row.addWidget(end)
    lay.addLayout(row)
    if on_call_log:
        log_btn = QPushButton("Call log")
        log_btn.clicked.connect(on_call_log)
        lay.addWidget(log_btn)
    tip = QLabel("SIP · Confirm OSK · Call log below")
    tip.setWordWrap(True)
    tip.setStyleSheet("color: #9ab; font-size: 9px;")
    lay.addWidget(tip)
    lay.addStretch(1)

    def do_call():
        num = dial.text().strip()
        if not num:
            return
        os.system(f"linphonecsh dial {num} >/dev/null 2>&1 &")
        log = _load_json(CALL_LOG, [])
        log.insert(0, {"dir": "out", "number": num, "at": datetime.now().isoformat()})
        _save_json(CALL_LOG, log[:100])
        on_status(f"Dialing {num}")

    call.clicked.connect(do_call)
    end.clicked.connect(
        lambda: os.system("linphonecsh generic 'terminate' >/dev/null 2>&1 &")
    )
    return page_chrome("Phone", body, on_back)


def make_sms_page(modem, on_back, on_status) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    sms_list = QListWidget()
    sms_to = QLineEdit()
    sms_to.setPlaceholderText("To")
    sms_body = QTextEdit()
    sms_body.setPlaceholderText("Message")
    sms_body.setMaximumHeight(56)
    send = QPushButton("Send SMS")
    lay.addWidget(sms_list, 1)
    lay.addWidget(sms_to)
    lay.addWidget(sms_body)
    lay.addWidget(send)

    def refresh():
        threads = _load_json(SMS_LOG, {})
        sms_list.clear()
        for num, msgs in threads.items():
            last = msgs[-1] if msgs else ""
            sms_list.addItem(f"{num}: {last}")

    def do_send():
        num = sms_to.text().strip()
        text = sms_body.toPlainText().strip().replace("\n", " ")
        if not num or not text:
            return
        if not modem:
            QMessageBox.warning(body, "SMS", "SIM7600 not connected")
            return
        try:
            ok = modem.send_sms(num, text)
        except Exception as e:
            QMessageBox.warning(body, "SMS", str(e))
            return
        if not ok:
            QMessageBox.warning(body, "SMS", "Send failed")
            return
        threads = _load_json(SMS_LOG, {})
        threads.setdefault(num, []).append(f"> {text}")
        _save_json(SMS_LOG, threads)
        refresh()
        on_status(f"SMS sent to {num}")

    send.clicked.connect(do_send)
    refresh()
    body.refresh_sms = refresh  # type: ignore[attr-defined]
    return page_chrome("Messages", body, on_back)


def make_contacts_page(on_back, open_dial: Callable[[str], None]) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    lst = QListWidget()
    name = QLineEdit()
    name.setPlaceholderText("Name")
    num = QLineEdit()
    num.setPlaceholderText("Number")
    add = QPushButton("Add contact")
    dial = QPushButton("Dial selected")
    lay.addWidget(lst, 1)
    lay.addWidget(name)
    lay.addWidget(num)
    lay.addWidget(add)
    lay.addWidget(dial)

    def refresh():
        contacts = _load_json(CONTACTS, [])
        lst.clear()
        for c in contacts:
            lst.addItem(f"{c.get('name','')}  {c.get('number','')}")
        body._contacts = contacts  # type: ignore[attr-defined]

    def do_add():
        n = name.text().strip()
        number = num.text().strip()
        if not number:
            return
        contacts = _load_json(CONTACTS, [])
        contacts.append({"name": n or number, "number": number})
        _save_json(CONTACTS, contacts)
        refresh()

    def do_dial():
        contacts = getattr(body, "_contacts", [])
        row = lst.currentRow()
        if 0 <= row < len(contacts):
            open_dial(contacts[row]["number"])

    add.clicked.connect(do_add)
    dial.clicked.connect(do_dial)
    refresh()
    return page_chrome("Contacts", body, on_back)


def make_call_log_page(on_back) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    lst = QListWidget()
    for e in _load_json(CALL_LOG, []):
        lst.addItem(f"{e.get('dir','?')}  {e.get('number','')}  {e.get('at','')[:19]}")
    lay.addWidget(lst)
    if lst.count() == 0:
        lay.addWidget(QLabel("No calls yet."))
    return page_chrome("Call Log", body, on_back)


def make_camera_page(on_back, on_status) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    preview = QLabel("No photo yet")
    preview.setAlignment(Qt.AlignCenter)
        preview.setMinimumHeight(120)
    preview.setStyleSheet("background:#111; border-radius:12px; color:#888;")
    gallery = QListWidget()
    snap = QPushButton("Snap (rear CSI)")
    refresh = QPushButton("Refresh gallery")
    lay.addWidget(snap)
    lay.addWidget(preview)
    lay.addWidget(QLabel("Gallery ~/Pictures/phone"))
    lay.addWidget(gallery, 1)
    lay.addWidget(refresh)

    def show_path(path: Path):
        pix = QPixmap(str(path))
        preview.setPixmap(
            pix.scaled(400, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        on_status(f"Saved {path.name}")

    def do_snap():
        try:
            path = pi_camera.capture_rear()
            show_path(path)
            do_refresh()
        except Exception as e:
            QMessageBox.warning(body, "Camera", str(e))

    def do_refresh():
        gallery.clear()
        for p in pi_camera.list_photos():
            gallery.addItem(p.name)

    def show_sel():
        items = gallery.selectedItems()
        if not items:
            return
        path = PHOTOS / items[0].text()
        if path.exists():
            show_path(path)

    snap.clicked.connect(do_snap)
    refresh.clicked.connect(do_refresh)
    gallery.itemSelectionChanged.connect(show_sel)
    PHOTOS.mkdir(parents=True, exist_ok=True)
    do_refresh()
    return page_chrome("Camera", body, on_back)


def make_lora_page(bridge, on_back, on_status) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    log = QTextEdit()
    log.setReadOnly(True)
    out = QLineEdit()
    row = QHBoxLayout()
    send = QPushButton("Send")
    sos = QPushButton("SOS")
    row.addWidget(send)
    row.addWidget(sos)
    lay.addWidget(log, 1)
    lay.addWidget(out)
    lay.addLayout(row)
    tip = QLabel("Heltec-compatible mesh via ESP SX1276")
    tip.setStyleSheet("color:#9ab;")
    lay.addWidget(tip)

    def do_send():
        text = out.text().strip()
        if not text or not bridge:
            if not bridge:
                QMessageBox.warning(body, "LoRa", "ESP not connected")
            return
        try:
            bridge.lora_send(text)
            log.append(f"> {text}")
            out.clear()
        except Exception as e:
            QMessageBox.warning(body, "LoRa", str(e))

    def do_sos():
        if not bridge:
            QMessageBox.warning(body, "LoRa", "ESP not connected")
            return
        try:
            bridge.lora_sos()
            log.append("> SOS")
            on_status("LoRa SOS sent")
        except Exception as e:
            QMessageBox.warning(body, "LoRa", str(e))

    send.clicked.connect(do_send)
    sos.clicked.connect(do_sos)
    body.lora_log = log  # type: ignore[attr-defined]
    return page_chrome("LoRa SOS", body, on_back)


def make_gps_page(modem, on_back, on_status) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    info = QLabel("GPS off / no fix")
    info.setWordWrap(True)
    on_btn = QPushButton("GPS ON + poll")
    lay.addWidget(info)
    lay.addWidget(on_btn)
    lay.addStretch(1)

    def do_gps():
        if not modem:
            QMessageBox.warning(body, "GPS", "SIM7600 not connected")
            return
        try:
            modem.gps_on()
            text = modem.gps_info() or "no fix yet"
            info.setText(text)
            on_status(text[:60])
        except Exception as e:
            QMessageBox.warning(body, "GPS", str(e))

    on_btn.clicked.connect(do_gps)
    return page_chrome("GPS", body, on_back)


def make_notes_page(on_back) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    edit = QTextEdit()
    edit.setPlainText("\n".join(_load_json(NOTES, ["(new note)"])))
    save = QPushButton("Save notes")
    lay.addWidget(edit, 1)
    lay.addWidget(save)

    def do_save():
        lines = [ln for ln in edit.toPlainText().splitlines() if ln.strip()]
        _save_json(NOTES, lines or ["(empty)"])

    save.clicked.connect(do_save)
    return page_chrome("Notes", body, on_back)


def make_todos_page(on_back) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    lst = QListWidget()
    inp = QLineEdit()
    inp.setPlaceholderText("New todo")
    add = QPushButton("Add")
    lay.addWidget(lst, 1)
    lay.addWidget(inp)
    lay.addWidget(add)

    def refresh():
        lst.clear()
        for t in _load_json(TODOS, []):
            lst.addItem(t)

    def do_add():
        t = inp.text().strip()
        if not t:
            return
        items = _load_json(TODOS, [])
        items.append(t)
        _save_json(TODOS, items)
        inp.clear()
        refresh()

    add.clicked.connect(do_add)
    refresh()
    return page_chrome("Todos", body, on_back)


def make_clock_page(on_back) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    big = QLabel(datetime.now().strftime("%H:%M:%S"))
    big.setAlignment(Qt.AlignCenter)
    big.setStyleSheet("font-size: 48px; font-weight: 700;")
    date = QLabel(datetime.now().strftime("%A, %d %B %Y"))
    date.setAlignment(Qt.AlignCenter)
    date.setStyleSheet("color:#9ab;")
    lay.addStretch(1)
    lay.addWidget(big)
    lay.addWidget(date)
    lay.addStretch(1)
    return page_chrome("Clock", body, on_back)


def make_calc_page(on_back) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    disp = QLineEdit("0")
    disp.setReadOnly(True)
    disp.setAlignment(Qt.AlignRight)
    disp.setStyleSheet("font-size: 28px; padding: 12px;")
    lay.addWidget(disp)
    expr = {"v": ""}

    def tap(ch: str):
        if ch == "C":
            expr["v"] = ""
            disp.setText("0")
            return
        if ch == "=":
            try:
                # Safe-ish eval for + - * / digits
                allowed = set("0123456789.+-*/() ")
                if not set(expr["v"]) <= allowed:
                    disp.setText("err")
                    return
                disp.setText(str(eval(expr["v"], {"__builtins__": {}}, {})))  # noqa: S307
                expr["v"] = disp.text()
            except Exception:
                disp.setText("err")
                expr["v"] = ""
            return
        expr["v"] += ch
        disp.setText(expr["v"])

    grid = [
        ["7", "8", "9", "/"],
        ["4", "5", "6", "*"],
        ["1", "2", "3", "-"],
        ["0", ".", "=", "+"],
        ["C"],
    ]
    for row in grid:
        h = QHBoxLayout()
        for ch in row:
            b = QPushButton(ch)
            b.clicked.connect(lambda _=False, c=ch: tap(c))
            h.addWidget(b)
        lay.addLayout(h)
    return page_chrome("Calculator", body, on_back)


def make_appearance_page(shell, on_back) -> QWidget:
    """Wallpaper picker — Pi equivalent of ESP /ui/wallpaper.jpg."""
    from PyQt5.QtWidgets import QFileDialog

    from esp_handset import theme as handset_theme

    body = QWidget()
    lay = QVBoxLayout(body)
    path = handset_theme.resolve_wallpaper()
    info = QLabel(
        f"Current: {path}" if path else "Default gradient (no wallpaper set)"
    )
    info.setWordWrap(True)
    info.setStyleSheet("color:#9ab;")
    tip = QLabel(
        "Same idea as ESP Phone SD art:\n"
        "  ~/.esp-handset/ui/wallpaper.jpg\n"
        "  ~/.esp-handset/ui/icons/   (app icons later)\n\n"
        "Pick any JPG/PNG from Gallery or Desktop."
    )
    tip.setWordWrap(True)
    lay.addWidget(info)
    lay.addWidget(tip)

    def refresh_info():
        p = handset_theme.resolve_wallpaper()
        info.setText(f"Current: {p}" if p else "Default gradient (no wallpaper set)")
        shell.apply_wallpaper()

    def pick():
        start = str(Path.home() / "Pictures")
        fn, _ = QFileDialog.getOpenFileName(
            body,
            "Choose wallpaper",
            start,
            "Images (*.jpg *.jpeg *.png *.webp *.bmp)",
        )
        if not fn:
            return
        try:
            handset_theme.set_wallpaper_file(Path(fn))
            refresh_info()
        except Exception as e:
            QMessageBox.warning(body, "Wallpaper", str(e))

    def clear():
        handset_theme.clear_wallpaper()
        refresh_info()

    pick_btn = QPushButton("Choose wallpaper image…")
    pick_btn.clicked.connect(pick)
    clear_btn = QPushButton("Clear wallpaper")
    clear_btn.clicked.connect(clear)
    lay.addWidget(pick_btn)
    lay.addWidget(clear_btn)
    lay.addStretch(1)
    return page_chrome("Appearance", body, on_back)


def make_settings_hub(on_back, open_page: Callable[[str], None], on_linux) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setSpacing(4)
    lay.setContentsMargins(2, 2, 2, 2)
    tip = QLabel("↓ scroll · D-pad moves focus")
    tip.setStyleSheet("color:#9ab;font-size:10px;")
    lay.addWidget(tip)
    for key, label in [
        ("set_update", "★ Update Digivice"),
        ("set_appearance", "Appearance"),
        ("set_network", "Network / modem"),
        ("set_accounts", "Accounts (SIP)"),
        ("set_sounds", "Sounds"),
        ("set_security", "Security (PIN)"),
        ("set_about", "About"),
        ("help", "Help / Keys"),
    ]:
        b = QPushButton(label)
        b.setMinimumHeight(30)
        b.clicked.connect(lambda _=False, k=key: open_page(k))
        lay.addWidget(b)
    desk = QPushButton("Exit to Linux Desktop")
    desk.setMinimumHeight(30)
    desk.clicked.connect(on_linux)
    lay.addWidget(desk)
    lay.addStretch(1)
    return page_chrome("Settings", body, on_back)


def make_update_page(on_back: Callable[[], None]) -> QWidget:
    """Download latest from GitHub and reinstall Digivice software.

    No QMessageBox (hard buttons cannot answer Yes/No dialogs reliably).
    Uses digivice-gui-update which never kills Digivice mid-run.
    """
    from PyQt5.QtCore import QProcess, QProcessEnvironment, QTimer

    body = QWidget()
    lay = QVBoxLayout(body)
    tip = QLabel(
        "Update from GitHub to /opt.\n"
        "Check needs network. Install needs sudo.\n"
        "Install: press button TWICE (no Yes/No popup).\n"
        "Terminal seed if needed: sudo digivice-full-update"
    )
    tip.setWordWrap(True)
    tip.setStyleSheet("color:#9ab;font-size:10px;")
    status = QLabel("Ready.")
    status.setWordWrap(True)
    log = QTextEdit()
    log.setReadOnly(True)
    log.setMinimumHeight(100)
    log.setStyleSheet("font-size:9px; font-family: monospace;")
    check_btn = QPushButton("Check for updates")
    run_btn = QPushButton("Install update (x2)")
    full_btn = QPushButton("FULL install (x2)")
    full_btn.setStyleSheet("font-weight:700;")
    restart_btn = QPushButton("Restart Digivice")
    lay.addWidget(tip)
    lay.addWidget(status)
    lay.addWidget(log, 1)
    lay.addWidget(check_btn)
    lay.addWidget(run_btn)
    lay.addWidget(full_btn)
    lay.addWidget(restart_btn)

    proc = QProcess(body)
    proc.setProcessChannelMode(QProcess.MergedChannels)
    env = QProcessEnvironment.systemEnvironment()
    env.insert("DISPLAY", os.environ.get("DISPLAY", ":0"))
    env.insert(
        "PATH",
        "/usr/local/bin:/usr/bin:/bin:" + os.environ.get("PATH", ""),
    )
    env.insert("PYTHONUNBUFFERED", "1")
    proc.setProcessEnvironment(env)

    pending = {"action": None, "ts": 0.0}

    def _gui_update_bin() -> list:
        for p in (
            "/usr/local/bin/digivice-gui-update",
            "/opt/esp-handset/session/gui-update.sh",
        ):
            if os.path.isfile(p):
                return ["sudo", "-n", p]
        here = Path(__file__).resolve().parents[1] / "session" / "gui-update.sh"
        if here.is_file():
            return ["sudo", "-n", "bash", str(here)]
        for p in (
            "/usr/local/bin/digivice-update",
            "/opt/esp-handset/session/update-handset.sh",
        ):
            if os.path.isfile(p):
                return ["sudo", "-n", p]
        return ["sudo", "-n", "/usr/local/bin/digivice-gui-update"]

    def append_out() -> None:
        data = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        if not data:
            return
        log.moveCursor(QTextCursor.End)
        log.insertPlainText(data)
        log.moveCursor(QTextCursor.End)

    def set_busy(busy: bool) -> None:
        check_btn.setEnabled(not busy)
        run_btn.setEnabled(not busy)
        full_btn.setEnabled(not busy)

    def on_finished(code: int, _st) -> None:
        set_busy(False)
        append_out()
        if code == 0:
            status.setText("Update finished. Press Restart Digivice.")
            log.append("\n--- OK ---\n")
        else:
            status.setText(
                f"Failed (exit {code}). Or: sudo digivice-full-update"
            )
            log.append(
                "\n--- FAILED ---\n"
                "If sudo denied, seed once:\n"
                "  sudo digivice-full-update\n"
            )

    def on_error(err) -> None:
        set_busy(False)
        status.setText(f"Start error: {err}")
        log.append(f"\nQProcess error: {err}\n")

    proc.readyReadStandardOutput.connect(append_out)
    proc.finished.connect(on_finished)
    try:
        proc.errorOccurred.connect(on_error)
    except Exception:
        pass

    def start(args: list, label: str) -> None:
        if proc.state() != QProcess.NotRunning:
            status.setText("Already running...")
            return
        bin_cmd = _gui_update_bin()
        log.clear()
        status.setText(label)
        set_busy(True)
        full_cmd = bin_cmd + args
        log.append("$ " + " ".join(full_cmd) + "\n\n")
        try:
            r = subprocess.run(
                ["sudo", "-n", "true"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
            if r.returncode != 0:
                log.append(
                    "sudo -n failed — no passwordless sudo yet.\n"
                    "On SSH/keyboard run once:\n"
                    "  sudo digivice-full-update\n\n"
                )
                status.setText("Need sudo once via terminal first")
                set_busy(False)
                return
        except Exception as e:
            log.append(f"sudo probe: {e}\n")
        prog, *argv = full_cmd
        proc.start(prog, argv)
        if not proc.waitForStarted(5000):
            status.setText("Could not start updater")
            set_busy(False)
            log.append(
                "Missing digivice-gui-update.\n"
                "  sudo digivice-full-update\n"
            )

    def needs_confirm(action: str) -> bool:
        import time as _t

        now = _t.time()
        if pending["action"] == action and now - float(pending["ts"]) < 4.0:
            pending["action"] = None
            return False
        pending["action"] = action
        pending["ts"] = now
        status.setText("Press the same button again to confirm (4s)")
        return True

    def do_check() -> None:
        pending["action"] = None
        start(["--check"], "Checking GitHub...")

    def do_run() -> None:
        if needs_confirm("quick"):
            return
        start([], "Installing update...")

    def do_full() -> None:
        if needs_confirm("full"):
            return
        start(["--full"], "FULL update... (may take minutes)")

    def do_restart() -> None:
        status.setText("Restarting...")
        env2 = os.environ.copy()
        env2.setdefault("DISPLAY", ":0")
        try:
            subprocess.Popen(
                [
                    "bash",
                    "-c",
                    "sleep 0.5; /usr/local/bin/handset-phone || handset-phone",
                ],
                start_new_session=True,
                env=env2,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            status.setText(f"Restart failed: {e}")
            return
        QTimer.singleShot(300, lambda: os._exit(0))

    check_btn.clicked.connect(do_check)
    run_btn.clicked.connect(do_run)
    full_btn.clicked.connect(do_full)
    restart_btn.clicked.connect(do_restart)
    return page_chrome("Update", body, on_back)


def make_about_page(modem, on_back) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    lines = [
        "ESP Handset (Pi-primary)",
        "Cellular: SIM7600G-H USB",
        "Keys/LoRa: ESP CDC bridge",
        f"SIP env: {CONFIG}",
    ]
    if modem:
        try:
            lines.append(modem.signal() or "CSQ ?")
            lines.append(f"AT port: {modem.port}")
        except Exception as e:
            lines.append(str(e))
    else:
        lines.append("Modem: not connected")
    lab = QLabel("\n".join(lines))
    lab.setWordWrap(True)
    lay.addWidget(lab)
    lay.addStretch(1)
    return page_chrome("About", body, on_back)


def make_help_page(on_back) -> QWidget:
    return stub_page(
        "Help",
        "Home: top+bottom icon rows\n"
        "←→ along row · ↑↓ swap row\n"
        "Confirm → submenu carousel\n"
        "‹ › cycle (wraps) · grow/shrink\n"
        "Confirm / Back / Home buttons\n"
        "D-pad arrows move focus\n"
        "Type with on-screen keyboard\n"
        "Back×3 (Escape) → desktop\n"
        "F12 / F10 / Ctrl+Q → desktop\n"
        "Settings → Linux → Exit\n"
        "Settings → Update → download\n"
        "SSH: digivice-leave\n"
        "Settings → Linux → confirm",
        on_back,
    )


def make_network_page(modem, on_back, on_status) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    lab = QLabel("Tap refresh for modem CSQ")
    lab.setWordWrap(True)
    btn = QPushButton("Refresh modem STATUS")
    lay.addWidget(lab)
    lay.addWidget(btn)
    lay.addStretch(1)

    def refresh():
        if not modem:
            lab.setText("SIM7600 not connected\nUse Wi‑Fi for SIP testing.")
            return
        try:
            csq = modem.signal() or "CSQ ?"
            lab.setText(f"Port: {modem.port}\n{csq}")
            on_status(csq)
        except Exception as e:
            lab.setText(str(e))

    btn.clicked.connect(refresh)
    refresh()
    return page_chrome("Network", body, on_back)
