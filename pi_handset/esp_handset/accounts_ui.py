"""Settings → Accounts: hub + per-service pages (SIP, Email, AI)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from esp_handset import store
from esp_handset.pages import CONFIG, page_chrome

_BG = "#0e1620"
_SURFACE = "#16202c"
_BORDER = "#243040"
_TEXT = "#e8eef5"
_MUTED = "#7a8a9a"
_ACCENT = "#5ec4a8"
_FIELD = (
    f"QLineEdit {{ font-size:12px; padding:8px; background:{_SURFACE};"
    f" color:{_TEXT}; border:1px solid {_BORDER}; border-radius:8px; }}"
    'QLineEdit[digiFocus="1"] { border:2px solid #FFE600; }'
)


def _label(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setStyleSheet(f"font-size:10px; font-weight:700; color:{_MUTED};")
    return lab


def _field(placeholder: str = "", *, password: bool = False) -> QLineEdit:
    ed = QLineEdit()
    ed.setPlaceholderText(placeholder)
    ed.setStyleSheet(_FIELD)
    ed.setMinimumHeight(32)
    ed.setFocusPolicy(Qt.StrongFocus)
    # Digivice: Confirm focuses for CardKB; Escape leaves (kiosk filter)
    ed.setToolTip("Confirm to type · Back to leave")
    if password:
        ed.setEchoMode(QLineEdit.Password)
    return ed


def _btn(text: str, *, primary: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setFocusPolicy(Qt.StrongFocus)
    b.setMinimumHeight(34)
    if primary:
        b.setStyleSheet(
            f"QPushButton {{ font-size:12px; font-weight:700; color:#0a1218;"
            f" background:{_ACCENT}; border:none; border-radius:10px; }}"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
    else:
        b.setStyleSheet(
            f"QPushButton {{ font-size:11px; font-weight:600; color:{_TEXT};"
            f" background:#1e2a38; border:1px solid {_BORDER}; border-radius:10px; }}"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
    return b


def _status() -> QLabel:
    lab = QLabel("")
    lab.setWordWrap(True)
    lab.setStyleSheet(f"font-size:10px; color:{_MUTED};")
    return lab


def _header(title: str, blurb: str) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(2, 0, 2, 4)
    lay.setSpacing(2)
    t = QLabel(title)
    t.setStyleSheet(f"font-size:15px; font-weight:700; color:{_TEXT};")
    b = QLabel(blurb)
    b.setWordWrap(True)
    b.setStyleSheet(f"font-size:10px; color:{_MUTED};")
    lay.addWidget(t)
    lay.addWidget(b)
    return w


def _read_sip() -> dict:
    vals = {
        "SIP_SERVER": "",
        "SIP_USER": "",
        "SIP_PASS": "",
        "SIP_DISPLAY": "",
    }
    path = CONFIG
    try:
        if not path.is_file() or not os.access(path, os.R_OK):
            path = store.DATA / "sip.env"
    except OSError:
        path = store.DATA / "sip.env"
    if path.is_file() and os.access(path, os.R_OK):
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip()
        except OSError:
            pass
    return vals


def _write_sip(server: str, user: str, password: str, display: str) -> str:
    """Returns where it was saved."""
    store.ensure()
    content = (
        f"SIP_SERVER={server.strip()}\n"
        f"SIP_USER={user.strip()}\n"
        f"SIP_PASS={password.strip()}\n"
        f"SIP_DISPLAY={(display.strip() or 'ESP Handset')}\n"
    )
    dest = Path("/etc/esp-handset/sip.env")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        return str(dest)
    except PermissionError:
        alt = store.DATA / "sip.env"
        alt.write_text(content)
        return str(alt)


def make_sip_account_page(on_back: Callable[[], None]) -> QWidget:
    from PyQt5.QtCore import QObject, pyqtSignal
    import threading

    body = QWidget()
    body.setStyleSheet(f"background:{_BG}; color:{_TEXT};")
    lay = QVBoxLayout(body)
    lay.setContentsMargins(6, 4, 6, 6)
    lay.setSpacing(6)
    lay.addWidget(
        _header("SIP / VoIP", "Test SIP shows the result up here")
    )
    status = _status()
    status.setMinimumHeight(88)
    status.setText("Confirm Test SIP — result appears here")
    status.setStyleSheet(
        f"font-size:11px; font-weight:600; color:{_TEXT};"
        f" background:#1a2430; border:1px solid {_BORDER};"
        " border-radius:8px; padding:6px;"
    )
    lay.addWidget(status)
    save = _btn("Save SIP")
    test = _btn("Test SIP", primary=True)
    lay.addWidget(test)
    lay.addWidget(save)
    vals = _read_sip()
    server = _field("sip.example.com")
    user = _field("user / extension")
    password = _field("password", password=True)
    display = _field("Display name")
    server.setText(vals.get("SIP_SERVER", ""))
    user.setText(vals.get("SIP_USER", ""))
    password.setText(vals.get("SIP_PASS", ""))
    display.setText(vals.get("SIP_DISPLAY", ""))
    for lab, w in (
        ("Server", server),
        ("User", user),
        ("Password", password),
        ("Display name", display),
    ):
        lay.addWidget(_label(lab))
        lay.addWidget(w)
    lay.addStretch(1)

    class _Bridge(QObject):
        progress = pyqtSignal(str)
        done = pyqtSignal(str)

    bridge = _Bridge(body)
    testing = {"on": False, "gen": 0}

    def _show(text: str) -> None:
        status.setText(text)
        status.setWordWrap(True)

    def _on_progress(text: str) -> None:
        _show(text)

    def _on_report(text: str) -> None:
        testing["on"] = False
        test.setEnabled(True)
        _show(text)
        summary = "SIP test done"
        for line in (text or "").splitlines():
            if line.startswith("RESULT:"):
                summary = line.replace("RESULT:", "").strip()
                break
        try:
            store.push_notif("SIP", summary, "settings")
        except Exception:
            pass

    bridge.progress.connect(_on_progress, Qt.QueuedConnection)
    bridge.done.connect(_on_report, Qt.QueuedConnection)

    def do_save() -> None:
        where = _write_sip(
            server.text(), user.text(), password.text(), display.text()
        )
        status.setText(f"Saved · {where}\nRegistering…")
        store.push_notif("SIP", "Account saved", "settings")

        def work() -> None:
            try:
                from esp_handset import sip_call

                hint = sip_call.ensure()
                msg = f"Saved · {hint}" if hint else f"Saved · registered · {where}"
            except Exception as e:
                msg = f"Saved · register later ({e})"
            bridge.progress.emit(msg)

        threading.Thread(target=work, name="sip-save", daemon=True).start()

    def do_test() -> None:
        if testing["on"]:
            _show("Test already running…")
            return
        testing["on"] = True
        testing["gen"] += 1
        gen = testing["gen"]
        _show("Testing SIP…\n(may install linphone, ~1 min)")
        test.setEnabled(False)
        try:
            store.push_notif("SIP", "Testing…", "settings")
        except Exception:
            pass

        def work() -> None:
            try:
                from esp_handset import sip_call

                report = sip_call.doctor()
            except Exception as e:
                report = f"RESULT: TEST FAILED\n{e}"
            if gen == testing["gen"]:
                bridge.done.emit(report)

        threading.Thread(target=work, name="sip-doctor", daemon=True).start()

        def timed_out() -> None:
            if not testing["on"] or testing["gen"] != gen:
                return
            extra = ""
            try:
                from esp_handset import sip_call

                extra = sip_call.recent_log(8)
            except Exception:
                pass
            bridge.done.emit("RESULT: TEST TIMED OUT\n" + extra)

        QTimer.singleShot(80000, timed_out)

    save.clicked.connect(do_save)
    test.clicked.connect(do_test)
    return page_chrome("SIP", body, on_back, scroll=True)


def make_email_account_page(on_back: Callable[[], None]) -> QWidget:
    body = QWidget()
    body.setStyleSheet(f"background:{_BG}; color:{_TEXT};")
    lay = QVBoxLayout(body)
    lay.setContentsMargins(6, 4, 6, 6)
    lay.setSpacing(6)
    lay.addWidget(
        _header(
            "Email",
            "Gmail: App Password only (not your normal password). "
            "Google Account → Security → 2-Step → App passwords.",
        )
    )
    em = store.load(
        "email.json",
        {
            "user": "",
            "pass": "",
            "host": "imap.gmail.com",
            "smtp": "smtp.gmail.com",
        },
    )
    user = _field("you@gmail.com")
    password = _field("16-letter app password", password=True)
    imap_host = _field("imap.gmail.com")
    smtp_host = _field("smtp.gmail.com")
    user.setText(str(em.get("user") or ""))
    password.setText(str(em.get("pass") or ""))
    imap_host.setText(str(em.get("host") or "imap.gmail.com"))
    smtp_host.setText(str(em.get("smtp") or "smtp.gmail.com"))
    for lab, w in (
        ("Address", user),
        ("App password", password),
        ("IMAP host", imap_host),
        ("SMTP host", smtp_host),
    ):
        lay.addWidget(_label(lab))
        lay.addWidget(w)
    status = _status()
    save = _btn("Save Email", primary=True)
    test = _btn("Test login")
    lay.addWidget(save)
    lay.addWidget(test)
    lay.addWidget(status)
    lay.addStretch(1)

    def _normalized() -> dict:
        return {
            "user": user.text().strip(),
            "pass": "".join(password.text().split()),
            "host": imap_host.text().strip() or "imap.gmail.com",
            "smtp": smtp_host.text().strip() or "smtp.gmail.com",
        }

    def do_save() -> None:
        data = _normalized()
        # Keep spaces out of stored app password
        password.setText(data["pass"])
        store.save("email.json", data)
        status.setText("Saved · Email inbox will use these")
        store.push_notif("Email", "Account saved", "settings")

    def do_test() -> None:
        data = _normalized()
        if not data["user"] or not data["pass"]:
            status.setText("Need address + app password first")
            return
        if "@" not in data["user"]:
            status.setText("Address should look like you@gmail.com")
            return
        status.setText("Testing IMAP…")
        try:
            import imaplib

            M = imaplib.IMAP4_SSL(data["host"], 993)
            M.login(data["user"], data["pass"])
            M.select("INBOX")
            M.logout()
            store.save("email.json", data)
            password.setText(data["pass"])
            status.setText("OK · Signed in to IMAP")
            store.push_notif("Email", "Login OK", "settings")
        except Exception as e:
            msg = str(e)
            low = msg.lower()
            if "auth" in low or "invalid" in low or "login" in low:
                status.setText(
                    "Auth failed · use a Google App Password "
                    "(Security → App passwords), not your normal password"
                )
            else:
                status.setText(f"Failed · {msg[:80]}")

    save.clicked.connect(do_save)
    test.clicked.connect(do_test)
    return page_chrome("Email", body, on_back, scroll=True)


def make_ai_account_page(on_back: Callable[[], None]) -> QWidget:
    body = QWidget()
    body.setStyleSheet(f"background:{_BG}; color:{_TEXT};")
    lay = QVBoxLayout(body)
    lay.setContentsMargins(6, 4, 6, 6)
    lay.setSpacing(6)
    lay.addWidget(
        _header(
            "AI · Ollama",
            "Confirm on a field to type · local or LAN Ollama",
        )
    )
    cfg = store.load(
        "ollama.json",
        {"host": "http://127.0.0.1:11434", "model": "deepseek-r1:1.5b"},
    )
    try:
        from esp_handset.ollama_chat import apply_config

        live_host, live_model = apply_config()
        if not cfg.get("host"):
            cfg["host"] = live_host
        if not cfg.get("model"):
            cfg["model"] = live_model
    except Exception:
        pass
    host = _field("http://127.0.0.1:11434")
    model = _field("model name")
    host.setText(str(cfg.get("host") or "http://127.0.0.1:11434"))
    model.setText(str(cfg.get("model") or "deepseek-r1:1.5b"))
    lay.addWidget(_label("Host URL"))
    lay.addWidget(host)
    lay.addWidget(_label("Default model"))
    lay.addWidget(model)
    status = _status()
    save = _btn("Save AI", primary=True)
    lay.addWidget(save)
    lay.addWidget(status)
    lay.addStretch(1)

    def do_save() -> None:
        store.save(
            "ollama.json",
            {
                "host": host.text().strip() or "http://127.0.0.1:11434",
                "model": model.text().strip(),
            },
        )
        status.setText("Saved · Tools → AI will use this")
        store.push_notif("AI", "Ollama settings saved", "settings")

    save.clicked.connect(do_save)
    return page_chrome("AI", body, on_back, scroll=True)


# Legacy combined page — redirect callers to SIP (kept for safety)
def make_accounts_page(on_back: Callable[[], None]) -> QWidget:
    return make_sip_account_page(on_back)
