"""Gmail-inspired Digivice mail — dark inbox, reader, compose on 240×320."""
from __future__ import annotations

import email as email_lib
import imaplib
import re
import smtplib
import ssl
from datetime import datetime
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from typing import Callable, List, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QPainter
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from esp_handset import store
from esp_handset.pages import page_chrome

# Gmail dark (Material) — tuned for ST7789
_BG = "#202124"
_SURFACE = "#292a2d"
_CHIP = "#3c4043"
_TEXT = "#e8eaed"
_MUTED = "#9aa0a6"
_BLUE = "#8ab4f8"
_RED = "#ea4335"
_GREEN = "#81c995"
_AVATAR = (
    "#ea4335",
    "#fbbc04",
    "#34a853",
    "#4285f4",
    "#a142f4",
    "#ff6d01",
    "#46bdc6",
    "#f538a0",
)


def _btn(text: str, *, primary: bool = False, fab: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setFocusPolicy(Qt.StrongFocus)
    b.setCursor(Qt.PointingHandCursor)
    if fab:
        b.setFixedSize(40, 40)
        b.setStyleSheet(
            f"QPushButton {{ font-size:20px; font-weight:700; color:#fff;"
            f" background:{_RED}; border:none; border-radius:20px; }}"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
    elif primary:
        b.setMinimumHeight(30)
        b.setStyleSheet(
            f"QPushButton {{ font-size:11px; font-weight:700; padding:4px 10px;"
            f" color:#202124; background:{_BLUE}; border:none; border-radius:16px; }}"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
    else:
        b.setMinimumHeight(28)
        b.setStyleSheet(
            f"QPushButton {{ font-size:11px; font-weight:600; padding:4px 8px;"
            f" color:{_TEXT}; background:{_CHIP}; border:none; border-radius:14px; }}"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
    return b


def _decode_hdr(raw) -> str:
    if raw is None:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return str(raw)


def _from_name(from_hdr: str) -> str:
    s = (from_hdr or "").strip()
    if not s:
        return "Unknown"
    m = re.match(r'^"?([^"<]+)"?\s*<', s)
    if m:
        return m.group(1).strip() or s
    if "<" in s:
        return s.split("<", 1)[0].strip().strip('"') or s
    return s


def _from_email(from_hdr: str) -> str:
    s = (from_hdr or "").strip()
    m = re.search(r"<([^>]+)>", s)
    if m:
        return m.group(1).strip()
    if "@" in s:
        return s
    return ""


def _initial(name: str) -> str:
    for ch in (name or "?").strip():
        if ch.isalnum():
            return ch.upper()
    return "?"


def _avatar_color(key: str) -> str:
    h = sum(ord(c) for c in (key or "?"))
    return _AVATAR[h % len(_AVATAR)]


def _fmt_when(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    try:
        local = dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        local = dt.replace(tzinfo=None) if getattr(dt, "tzinfo", None) else dt
    now = datetime.now()
    if local.date() == now.date():
        return local.strftime("%H:%M")
    if local.year == now.year:
        return local.strftime("%b %d")
    return local.strftime("%Y")


def _parse_date(hdr: str) -> Optional[datetime]:
    try:
        return parsedate_to_datetime(hdr)
    except Exception:
        return None


def _creds() -> dict:
    raw = store.load(
        "email.json",
        {"user": "", "pass": "", "host": "imap.gmail.com", "smtp": "smtp.gmail.com"},
    )
    if not isinstance(raw, dict):
        raw = {}
    user = str(raw.get("user") or "").strip()
    # Google app passwords are often typed with spaces (xxxx xxxx xxxx xxxx)
    password = "".join(str(raw.get("pass") or "").split())
    host = str(raw.get("host") or "imap.gmail.com").strip() or "imap.gmail.com"
    smtp = str(raw.get("smtp") or "smtp.gmail.com").strip() or "smtp.gmail.com"
    return {"user": user, "pass": password, "host": host, "smtp": smtp}


def _auth_hint(err: str, user: str) -> str:
    """Human tip when IMAP/SMTP rejects the login."""
    e = (err or "").lower()
    gmail = "gmail" in (user or "").lower() or "@gmail." in (user or "").lower()
    if any(
        x in e
        for x in (
            "authentication failed",
            "invalid credentials",
            "auth",
            "login failed",
            "application-specific",
        )
    ):
        if gmail:
            return (
                "Gmail rejected the password.\n\n"
                "Use a Google App Password, not your normal login:\n"
                "1. Google Account → Security\n"
                "2. Turn on 2-Step Verification\n"
                "3. App passwords → Mail → Digivice\n"
                "4. Paste the 16-letter code in\n"
                "   Settings → Accounts → Email\n\n"
                "Also enable IMAP in Gmail Settings → Forwarding/IMAP."
            )
        return (
            "Login rejected.\n\n"
            "Check address + password in\n"
            "Settings → Accounts → Email.\n"
            "Many hosts need an app password."
        )
    return err or "Unknown error"


def _cache_get() -> List[dict]:
    return list(store.load("email_cache.json", {"messages": []}).get("messages") or [])


def _cache_set(messages: List[dict]) -> None:
    store.save(
        "email_cache.json",
        {
            "messages": messages[:40],
            "at": datetime.now().isoformat(timespec="seconds"),
        },
    )


class Avatar(QWidget):
    def __init__(self, letter: str, color: str, parent=None):
        super().__init__(parent)
        self.letter = (letter or "?")[:1]
        self.color = QColor(color)
        self.setFixedSize(32, 32)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(self.color)
        p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, 32, 32)
        p.setPen(QColor("#ffffff"))
        f = QFont("DejaVu Sans")
        f.setPixelSize(14)
        f.setBold(True)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignCenter, self.letter)


class MailRow(QFrame):
    """One Gmail-style thread row."""

    def __init__(self, msg: dict, parent=None):
        super().__init__(parent)
        self.msg = msg
        unread = bool(msg.get("unread"))
        self.setStyleSheet(
            f"QFrame {{ background: transparent; border: none;"
            f" border-bottom: 1px solid {_CHIP}; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 8, 6, 8)
        lay.setSpacing(8)
        name = msg.get("from_name") or "Unknown"
        lay.addWidget(Avatar(_initial(name), _avatar_color(name)), 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(1)
        top = QHBoxLayout()
        frm = QLabel(name)
        weight = "700" if unread else "600"
        frm.setStyleSheet(
            f"font-size:12px; font-weight:{weight}; color:{_TEXT}; border:none;"
        )
        frm.setMaximumWidth(140)
        when = QLabel(str(msg.get("when") or ""))
        when.setStyleSheet(
            f"font-size:9px; color:{_BLUE if unread else _MUTED}; border:none;"
            + (" font-weight:700;" if unread else "")
        )
        when.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(frm, 1)
        top.addWidget(when, 0)
        col.addLayout(top)
        sub = QLabel(str(msg.get("subject") or "(no subject)"))
        sub.setStyleSheet(
            f"font-size:11px; font-weight:{'700' if unread else '500'};"
            f" color:{_TEXT}; border:none;"
        )
        sub.setWordWrap(False)
        col.addWidget(sub)
        snip = QLabel(str(msg.get("snippet") or ""))
        snip.setStyleSheet(f"font-size:10px; color:{_MUTED}; border:none;")
        snip.setWordWrap(False)
        col.addWidget(snip)
        lay.addLayout(col, 1)
        self.setMinimumHeight(58)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


def make_email_page(on_back: Callable[[], None]) -> QWidget:
    del on_back
    body = QWidget()
    body.setStyleSheet(f"background:{_BG}; color:{_TEXT};")
    root = QVBoxLayout(body)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    stack = QStackedWidget()
    root.addWidget(stack, 1)

    # ── Inbox ────────────────────────────────────────────────────────────
    inbox = QWidget()
    il = QVBoxLayout(inbox)
    il.setContentsMargins(4, 2, 4, 4)
    il.setSpacing(4)

    head = QHBoxLayout()
    head.setSpacing(4)
    title = QLabel("Inbox")
    title.setStyleSheet(
        f"font-size:18px; font-weight:700; color:{_TEXT}; letter-spacing:0.2px;"
    )
    acct = QLabel("")
    acct.setStyleSheet(f"font-size:9px; color:{_MUTED};")
    acct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    head.addWidget(title, 1)
    head.addWidget(acct, 0)
    il.addLayout(head)

    tabs = QHBoxLayout()
    tabs.setSpacing(4)
    primary_chip = QLabel("● Primary")
    primary_chip.setStyleSheet(
        f"font-size:10px; font-weight:700; color:{_RED};"
        f" background:{_SURFACE}; padding:4px 10px; border-radius:12px;"
    )
    status = QLabel("")
    status.setStyleSheet(f"font-size:9px; color:{_MUTED};")
    tabs.addWidget(primary_chip)
    tabs.addStretch(1)
    tabs.addWidget(status)
    il.addLayout(tabs)

    lst = QListWidget()
    lst.setFocusPolicy(Qt.StrongFocus)
    lst.setSpacing(0)
    lst.setStyleSheet(
        f"QListWidget {{ background:{_SURFACE}; border:none; border-radius:12px;"
        f" outline:none; }}"
        "QListWidget::item { background: transparent; padding:0; margin:0; }"
        f"QListWidget::item:selected {{ background:{_CHIP}; }}"
        'QListWidget[digiFocus="1"] { border:2px solid #FFE600; border-radius:12px; }'
    )
    il.addWidget(lst, 1)

    empty = QLabel("Your Primary inbox is empty.\n\nPull to refresh —\nor set Accounts → Email.")
    empty.setAlignment(Qt.AlignCenter)
    empty.setWordWrap(True)
    empty.setStyleSheet(
        f"color:{_MUTED}; font-size:12px; padding:20px;"
        f" background:{_SURFACE}; border-radius:12px;"
    )
    empty.hide()
    il.addWidget(empty, 1)

    bar = QHBoxLayout()
    bar.setSpacing(6)
    refresh = _btn("↻ Refresh")
    compose_btn = _btn("✏️", fab=True)
    bar.addWidget(refresh, 1)
    bar.addWidget(compose_btn, 0)
    il.addLayout(bar)

    # ── Reader ───────────────────────────────────────────────────────────
    reader = QWidget()
    rl = QVBoxLayout(reader)
    rl.setContentsMargins(6, 4, 6, 4)
    rl.setSpacing(4)
    r_back = _btn("← Inbox")
    rl.addWidget(r_back, 0, Qt.AlignLeft)
    r_subj = QLabel("")
    r_subj.setWordWrap(True)
    r_subj.setStyleSheet(f"font-size:15px; font-weight:700; color:{_TEXT};")
    rl.addWidget(r_subj)
    r_meta = QHBoxLayout()
    r_avatar_host = QWidget()
    r_avatar_lay = QHBoxLayout(r_avatar_host)
    r_avatar_lay.setContentsMargins(0, 0, 0, 0)
    r_from = QLabel("")
    r_from.setWordWrap(True)
    r_from.setStyleSheet(f"font-size:11px; color:{_TEXT};")
    r_when = QLabel("")
    r_when.setStyleSheet(f"font-size:9px; color:{_MUTED};")
    r_meta.addWidget(r_avatar_host, 0)
    r_col = QVBoxLayout()
    r_col.setSpacing(0)
    r_col.addWidget(r_from)
    r_col.addWidget(r_when)
    r_meta.addLayout(r_col, 1)
    rl.addLayout(r_meta)
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background:{_CHIP};")
    rl.addWidget(line)
    r_scroll = QScrollArea()
    r_scroll.setWidgetResizable(True)
    r_scroll.setFrameShape(QFrame.NoFrame)
    r_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
    r_body = QLabel("")
    r_body.setWordWrap(True)
    r_body.setTextInteractionFlags(Qt.TextSelectableByMouse)
    r_body.setAlignment(Qt.AlignTop | Qt.AlignLeft)
    r_body.setStyleSheet(
        f"font-size:12px; color:{_TEXT}; background:transparent; padding:4px;"
    )
    r_scroll.setWidget(r_body)
    rl.addWidget(r_scroll, 1)

    # ── Compose ──────────────────────────────────────────────────────────
    compose = QWidget()
    cl = QVBoxLayout(compose)
    cl.setContentsMargins(6, 4, 6, 4)
    cl.setSpacing(4)
    c_head = QHBoxLayout()
    c_back = _btn("✕")
    c_title = QLabel("Compose")
    c_title.setStyleSheet(f"font-size:14px; font-weight:700; color:{_TEXT};")
    c_send = _btn("Send", primary=True)
    c_head.addWidget(c_back)
    c_head.addWidget(c_title, 1)
    c_head.addWidget(c_send)
    cl.addLayout(c_head)
    _field = (
        f"font-size:12px; padding:8px; background:{_SURFACE}; color:{_TEXT};"
        f" border:none; border-radius:8px;"
    )
    c_to = QLineEdit()
    c_to.setPlaceholderText("To")
    c_to.setStyleSheet(_field)
    c_subj = QLineEdit()
    c_subj.setPlaceholderText("Subject")
    c_subj.setStyleSheet(_field)
    c_body = QTextEdit()
    c_body.setPlaceholderText("Compose email")
    c_body.setStyleSheet(
        f"QTextEdit {{ font-size:12px; padding:8px; background:{_SURFACE};"
        f" color:{_TEXT}; border:none; border-radius:8px; }}"
    )
    cl.addWidget(c_to)
    cl.addWidget(c_subj)
    cl.addWidget(c_body, 1)
    c_status = QLabel("")
    c_status.setStyleSheet(f"font-size:9px; color:{_MUTED};")
    c_status.setWordWrap(True)
    cl.addWidget(c_status)

    stack.addWidget(inbox)
    stack.addWidget(reader)
    stack.addWidget(compose)

    state = {"messages": [], "busy": False}

    def _set_acct() -> None:
        em = _creds()
        u = (em.get("user") or "").strip()
        if u:
            short = u if len(u) <= 22 else u[:19] + "…"
            acct.setText(short)
        else:
            acct.setText("No account")

    def _fill_list(messages: List[dict]) -> None:
        state["messages"] = list(messages)
        lst.clear()
        if not messages:
            lst.hide()
            empty.show()
            status.setText("")
            return
        empty.hide()
        lst.show()
        unread_n = sum(1 for m in messages if m.get("unread"))
        status.setText(f"{unread_n} unread" if unread_n else f"{len(messages)} mail")
        for msg in messages:
            item = QListWidgetItem(lst)
            row = MailRow(msg)
            item.setSizeHint(row.sizeHint())
            lst.addItem(item)
            lst.setItemWidget(item, row)

    def _show_inbox() -> None:
        stack.setCurrentWidget(inbox)
        lst.setFocus(Qt.OtherFocusReason)

    def _open_reader(msg: dict) -> None:
        name = msg.get("from_name") or "Unknown"
        # rebuild avatar
        while r_avatar_lay.count():
            w = r_avatar_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        r_avatar_lay.addWidget(Avatar(_initial(name), _avatar_color(name)))
        r_subj.setText(str(msg.get("subject") or "(no subject)"))
        addr = msg.get("from_email") or ""
        r_from.setText(f"{name}\n{addr}" if addr else name)
        r_when.setText(str(msg.get("when_full") or msg.get("when") or ""))
        body_txt = str(msg.get("body") or msg.get("snippet") or "Open Refresh to load body.")
        r_body.setText(body_txt)
        stack.setCurrentWidget(reader)
        # Lazy body fetch
        if not msg.get("body") and msg.get("uid"):
            QTimer.singleShot(50, lambda m=msg: _fetch_body(m))

    def _fetch_body(msg: dict) -> None:
        em = _creds()
        user = em.get("user") or ""
        password = em.get("pass") or ""
        host = em.get("host") or "imap.gmail.com"
        uid = msg.get("uid")
        if not user or not password or not uid:
            return
        try:
            uid_b = uid.encode() if isinstance(uid, str) else uid
            M = imaplib.IMAP4_SSL(host, 993)
            M.login(user, password)
            M.select("INBOX")
            typ, data = M.fetch(uid_b, "(RFC822)")
            M.logout()
            if typ != "OK" or not data or not data[0]:
                return
            raw = data[0][1]
            parsed = email_lib.message_from_bytes(raw)
            text = _extract_text(parsed)
            msg["body"] = text[:4000]
            # update cache
            for m in state["messages"]:
                if m.get("uid") == uid:
                    m["body"] = msg["body"]
                    m["unread"] = False
            _cache_set(state["messages"])
            if stack.currentWidget() is reader:
                r_body.setText(msg["body"])
            _fill_list(state["messages"])
        except Exception as e:
            if stack.currentWidget() is reader:
                r_body.setText(f"(Could not load body)\n{e}\n\n{msg.get('snippet') or ''}")

    def _extract_text(msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                disp = str(part.get("Content-Disposition") or "")
                if ctype == "text/plain" and "attachment" not in disp.lower():
                    try:
                        payload = part.get_payload(decode=True) or b""
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="replace").strip()
                    except Exception:
                        continue
            return "(HTML-only message)"
        try:
            payload = msg.get_payload(decode=True) or b""
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace").strip()
        except Exception:
            return str(msg.get_payload())[:2000]

    def do_fetch() -> None:
        if state["busy"]:
            return
        em = _creds()
        user = em.get("user") or ""
        password = em.get("pass") or ""
        host = em.get("host") or "imap.gmail.com"
        if not user or not password:
            status.setText("Set Accounts → Email")
            empty.setText(
                "Sign in to get started\n\n"
                "Settings → Accounts\n"
                "Email + app password\n"
                "(Gmail IMAP)"
            )
            lst.hide()
            empty.show()
            return
        state["busy"] = True
        status.setText("Syncing…")
        refresh.setEnabled(False)

        def work():
            messages: List[dict] = []
            err = ""
            try:
                M = imaplib.IMAP4_SSL(host, 993)
                M.login(user, password)
                M.select("INBOX")
                typ, data = M.search(None, "ALL")
                ids = data[0].split()[-20:]
                for num in reversed(ids):
                    typ, msg_data = M.fetch(
                        num,
                        "(FLAGS BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])",
                    )
                    flags = ""
                    raw = b""
                    if msg_data:
                        for part in msg_data:
                            if isinstance(part, tuple) and len(part) >= 2:
                                meta = part[0]
                                if isinstance(meta, (bytes, bytearray)):
                                    flags += meta.decode("utf-8", errors="replace")
                                if isinstance(part[1], (bytes, bytearray)):
                                    raw = bytes(part[1])
                            elif isinstance(part, (bytes, bytearray)):
                                flags += part.decode("utf-8", errors="replace")
                    hdr = email_lib.message_from_bytes(raw) if raw else None
                    subj = _decode_hdr(hdr["Subject"]) if hdr else ""
                    frm = _decode_hdr(hdr["From"]) if hdr else ""
                    date_h = _decode_hdr(hdr["Date"]) if hdr else ""
                    dt = _parse_date(date_h)
                    unread = "\\Seen" not in flags
                    uid_s = (
                        num.decode()
                        if isinstance(num, (bytes, bytearray))
                        else str(num)
                    )
                    messages.append(
                        {
                            "uid": uid_s,
                            "subject": subj or "(no subject)",
                            "from_name": _from_name(frm),
                            "from_email": _from_email(frm),
                            "when": _fmt_when(dt),
                            "when_full": date_h,
                            "snippet": "Tap to open",
                            "unread": unread,
                            "body": "",
                        }
                    )
                M.logout()
            except Exception as e:
                err = str(e)
            return messages, err

        # Keep UI responsive: run sync on timer tick (short IMAP ok on Pi)
        try:
            messages, err = work()
        finally:
            state["busy"] = False
            refresh.setEnabled(True)
        if err:
            status.setText("Sync failed")
            empty.setText(f"Couldn't sync\n\n{err}")
            if not state["messages"]:
                lst.hide()
                empty.show()
            return
        _cache_set(messages)
        _fill_list(messages)
        store.push_notif("Email", f"{len(messages)} in Inbox", "email", toast=False)
        status.setText("Updated just now")

    def on_item(_item: QListWidgetItem) -> None:
        row = lst.currentRow()
        if 0 <= row < len(state["messages"]):
            _open_reader(state["messages"][row])

    def open_compose(to: str = "") -> None:
        c_to.setText(to or "")
        c_subj.clear()
        c_body.clear()
        c_status.setText("SMTP · Gmail app password")
        stack.setCurrentWidget(compose)
        (c_to if not to else c_subj).setFocus(Qt.OtherFocusReason)

    def do_send() -> None:
        em = _creds()
        user = em.get("user") or ""
        password = em.get("pass") or ""
        smtp_host = em.get("smtp") or "smtp.gmail.com"
        to = c_to.text().strip()
        subj = c_subj.text().strip()
        body_txt = c_body.toPlainText().strip()
        if not user or not password:
            c_status.setText("Configure Accounts first")
            return
        if not to or "@" not in to:
            c_status.setText("Need a To address")
            return
        c_status.setText("Sending…")
        try:
            msg = EmailMessage()
            msg["From"] = user
            msg["To"] = to
            msg["Subject"] = subj or "(no subject)"
            msg.set_content(body_txt or "")
            ctx = ssl.create_default_context()
            with smtplib.SMTP(smtp_host, 587, timeout=20) as s:
                s.starttls(context=ctx)
                s.login(user, password)
                s.send_message(msg)
            c_status.setText("Sent")
            store.push_notif("Email", f"Sent to {to}", "email")
            QTimer.singleShot(600, _show_inbox)
        except Exception as e:
            c_status.setText(str(e)[:80])

    refresh.clicked.connect(do_fetch)
    compose_btn.clicked.connect(lambda: open_compose())
    lst.itemActivated.connect(on_item)
    lst.itemClicked.connect(on_item)
    r_back.clicked.connect(_show_inbox)
    c_back.clicked.connect(_show_inbox)
    c_send.clicked.connect(do_send)

    _set_acct()
    cached = _cache_get()
    if cached:
        _fill_list(cached)
        status.setText("Cached · Refresh to sync")
    else:
        _fill_list([])
        empty.show()
        lst.hide()

    chrome = page_chrome("Email", body, None, scroll=False)

    def on_hardware_back() -> bool:
        w = stack.currentWidget()
        if w is reader or w is compose:
            _show_inbox()
            return True
        return False

    def compose_to(addr: str) -> None:
        open_compose(str(addr or ""))

    def prefill_to(addr: str) -> None:
        compose_to(addr)

    chrome.on_hardware_back = on_hardware_back  # type: ignore[attr-defined]
    chrome.compose_to = compose_to  # type: ignore[attr-defined]
    chrome.prefill_to = prefill_to  # type: ignore[attr-defined]
    # Auto-refresh once if account exists and cache empty
    if _creds().get("user") and _creds().get("pass") and not cached:
        QTimer.singleShot(400, do_fetch)
    return chrome
