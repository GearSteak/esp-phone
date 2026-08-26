"""Gmail-inspired Digivice mail — dark inbox, reader, compose on 240×320."""
from __future__ import annotations

import email as email_lib
import imaplib
import re
import smtplib
import ssl
import threading
from datetime import datetime
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from typing import Callable, List, Optional

from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal
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


_PANELS = (
    ("inbox", "Inbox"),
    ("sent", "Sent"),
    ("drafts", "Drafts"),
    ("spam", "Spam"),
    ("trash", "Trash"),
)
_PANEL_ALIASES = {
    "inbox": ("INBOX",),
    "sent": ("[Gmail]/Sent Mail", "Sent Mail", "Sent Items", "Sent"),
    "drafts": ("[Gmail]/Drafts", "Drafts"),
    "spam": ("[Gmail]/Spam", "Junk E-mail", "Junk", "Spam"),
    "trash": ("[Gmail]/Trash", "[Gmail]/Bin", "Deleted Items", "Trash", "Bin"),
}


def _cache_get(panel: str = "inbox") -> List[dict]:
    raw = store.load("email_cache.json", {"messages": []})
    if not isinstance(raw, dict):
        return []
    folders = raw.get("folders")
    if isinstance(folders, dict):
        return list(folders.get(panel) or [])
    if panel == "inbox":
        return list(raw.get("messages") or [])
    return []


def _cache_set(messages: List[dict], panel: str = "inbox") -> None:
    raw = store.load("email_cache.json", {})
    if not isinstance(raw, dict):
        raw = {}
    folders = dict(raw.get("folders") or {})
    if raw.get("messages") and "inbox" not in folders:
        folders["inbox"] = list(raw.get("messages") or [])
    folders[panel] = messages[:40]
    store.save(
        "email_cache.json",
        {
            "folders": folders,
            "at": datetime.now().isoformat(timespec="seconds"),
        },
    )


def _imap_list_names(M) -> List[str]:
    typ, data = M.list()
    names: List[str] = []
    if typ != "OK" or not data:
        return names
    for line in data:
        if not line:
            continue
        s = line.decode("utf-8", "replace") if isinstance(line, (bytes, bytearray)) else str(line)
        quoted = re.findall(r'"((?:\\.|[^"\\])*)"', s)
        if quoted:
            names.append(quoted[-1].replace(r"\"", '"'))
            continue
        parts = s.split()
        if parts:
            names.append(parts[-1].strip())
    return names


def _pick_mailbox(names: List[str], panel: str) -> str:
    aliases = _PANEL_ALIASES.get(panel) or ("INBOX",)
    by_l = {n.lower(): n for n in names}
    for a in aliases:
        hit = by_l.get(a.lower())
        if hit:
            return hit
    for a in aliases:
        al = a.lower()
        for n in names:
            nl = n.lower()
            if "all mail" in nl:
                continue
            if al in nl:
                return n
    return "INBOX" if panel == "inbox" else aliases[0]


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _snippet_text(text: str, limit: int = 90) -> str:
    s = _collapse_ws(text)
    if not s:
        return ""
    if len(s) <= limit:
        return s
    return s[: limit - 1].rstrip() + "…"


def _strip_html_preview(raw: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw or "")
    s = re.sub(r"(?is)<br\s*/?>", " ", s)
    s = re.sub(r"(?is)</p>", " ", s)
    s = re.sub(r"(?is)<[^>]+>", " ", s)
    s = (
        s.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    return _collapse_ws(s)


def _decode_part_bytes(payload: bytes, charset: Optional[str]) -> str:
    import quopri

    raw = payload or b""
    # Quoted-printable left as text shows literal "=0A" (Uber etc.)
    if b"=" in raw[:800] and (
        b"=0A" in raw or b"=0D" in raw or b"=\n" in raw or b"=\r\n" in raw
    ):
        try:
            raw = quopri.decodestring(raw)
        except Exception:
            pass
    for enc in ((charset or "").strip(), "utf-8", "latin-1"):
        if not enc:
            continue
        try:
            return raw.decode(enc, errors="replace")
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def _extract_text(msg) -> str:
    """Prefer text/plain; fall back to lightly stripped HTML."""
    if msg.is_multipart():
        html_fallback = ""
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp.lower():
                continue
            try:
                payload = part.get_payload(decode=True) or b""
            except Exception:
                continue
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            if ctype == "text/plain":
                return _decode_part_bytes(payload, charset).strip()
            if ctype == "text/html" and not html_fallback:
                html_fallback = _strip_html_preview(
                    _decode_part_bytes(payload, charset)
                )
        return html_fallback or "(HTML-only message)"
    try:
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        text = _decode_part_bytes(payload, charset).strip()
        if (msg.get_content_type() or "").lower() == "text/html":
            return _strip_html_preview(text)
        return text
    except Exception:
        return str(msg.get_payload())[:2000]


def _fetch_payload_parts(msg_data) -> List[bytes]:
    """Collect byte payloads from an imaplib fetch response."""
    out: List[bytes] = []
    if not msg_data:
        return out
    for part in msg_data:
        if isinstance(part, tuple) and len(part) >= 2:
            blob = part[1]
            if isinstance(blob, (bytes, bytearray)):
                out.append(bytes(blob))
        elif isinstance(part, (bytes, bytearray)):
            # metadata-only lines — ignore
            continue
    return out


def _flags_from_fetch(msg_data) -> str:
    flags = ""
    if not msg_data:
        return flags
    for part in msg_data:
        meta = part[0] if isinstance(part, tuple) and part else part
        if isinstance(meta, (bytes, bytearray)):
            flags += meta.decode("utf-8", errors="replace")
        elif isinstance(meta, str):
            flags += meta
    return flags


def _uid_str(uid) -> str:
    if isinstance(uid, (bytes, bytearray)):
        return uid.decode("utf-8", errors="replace")
    return str(uid)


_PLACEHOLDER_SNIPS = frozenset({"", "tap to open", "loading…", "loading..."})


def _bytes_to_snippet(raw: bytes, limit: int = 90) -> str:
    if not raw:
        return ""
    try:
        text = _decode_part_bytes(raw, "utf-8")
        # Quoted-printable leftovers / MIME noise — keep readable preview
        if re.search(r"(?i)<html|</p>|<br\s*/?>", text[:800]):
            text = _strip_html_preview(text)
        # If we got a MIME multipart blob, strip boundary lines
        if text.lstrip().startswith("--") or "Content-Type:" in text[:120]:
            text = re.sub(r"(?im)^--.*$", " ", text)
            text = re.sub(r"(?im)^Content-.*$", " ", text)
            text = _strip_html_preview(text)
        return _snippet_text(text, limit=limit)
    except Exception:
        return ""


class Avatar(QWidget):
    def __init__(self, letter: str, color: str, parent=None, size: int = 32):
        super().__init__(parent)
        self.letter = (letter or "?")[:1]
        self.color = QColor(color)
        self._sz = size
        self.setFixedSize(size, size)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(self.color)
        p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, self._sz, self._sz)
        p.setPen(QColor("#ffffff"))
        f = QFont("DejaVu Sans")
        f.setPixelSize(max(9, self._sz // 2))
        f.setBold(True)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignCenter, self.letter)


class MailRow(QFrame):
    """Narrow list row for the left pane (from + time)."""

    def __init__(self, msg: dict, parent=None):
        super().__init__(parent)
        self.msg = msg
        unread = bool(msg.get("unread"))
        self.setMinimumWidth(160)
        self.setStyleSheet(
            f"QFrame {{ background: transparent; border: none;"
            f" border-bottom: 1px solid {_CHIP}; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        name = msg.get("from_name") or "Unknown"
        lay.addWidget(Avatar(_initial(name), _avatar_color(name), size=22), 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(0)
        frm = QLabel(name)
        frm.setStyleSheet(
            f"font-size:10px; font-weight:{'700' if unread else '600'};"
            f" color:{_TEXT}; border:none;"
        )
        frm.setWordWrap(False)
        when = QLabel(str(msg.get("when") or ""))
        when.setStyleSheet(
            f"font-size:8px; color:{_BLUE if unread else _MUTED}; border:none;"
        )
        col.addWidget(frm)
        col.addWidget(when)
        lay.addLayout(col, 1)
        self.setMinimumHeight(36)
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
    il.setContentsMargins(4, 1, 4, 2)
    il.setSpacing(2)

    head = QHBoxLayout()
    head.setSpacing(4)
    title = QLabel("Inbox")
    title.setStyleSheet(
        f"font-size:13px; font-weight:700; color:{_TEXT}; letter-spacing:0.2px;"
    )
    acct = QLabel("")
    acct.setStyleSheet(f"font-size:8px; color:{_MUTED};")
    acct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    head.addWidget(title, 1)
    head.addWidget(acct, 0)
    il.addLayout(head)

    chips_row = QHBoxLayout()
    chips_row.setSpacing(2)
    chip_btns: dict = {}
    for key, lab in _PANELS:
        b = QPushButton(lab)
        b.setFocusPolicy(Qt.StrongFocus)
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedHeight(16)
        b.setProperty("panel", key)
        chips_row.addWidget(b, 1)
        chip_btns[key] = b
    compose_btn = QPushButton("✏️")
    compose_btn.setFocusPolicy(Qt.StrongFocus)
    compose_btn.setCursor(Qt.PointingHandCursor)
    compose_btn.setFixedSize(22, 16)
    compose_btn.setToolTip("Compose")
    compose_btn.setStyleSheet(
        f"QPushButton {{ font-size:9px; font-weight:700; padding:0;"
        f" color:#fff; background:{_RED}; border:none; border-radius:8px; }}"
        'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
    )
    chips_row.addWidget(compose_btn, 0)
    il.addLayout(chips_row)

    status = QLabel("")
    status.setStyleSheet(f"font-size:8px; color:{_MUTED};")
    il.addWidget(status)

    split = QHBoxLayout()
    split.setSpacing(4)

    lst = QListWidget()
    lst.setFocusPolicy(Qt.StrongFocus)
    lst.setSpacing(0)
    lst.setFixedWidth(108)
    lst.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    lst.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    lst.setStyleSheet(
        f"QListWidget {{ background:{_SURFACE}; border:none; border-radius:10px;"
        f" outline:none; }}"
        "QListWidget::item { background: transparent; padding:0; margin:0; }"
        f"QListWidget::item:selected {{ background:{_CHIP}; }}"
        'QListWidget[digiFocus="1"] { border:2px solid #FFE600; border-radius:10px; }'
        "QScrollBar:horizontal { height: 8px; background: #121820; }"
        "QScrollBar::handle:horizontal { background: #4a6a88; min-width: 20px; border-radius: 3px; }"
        "QScrollBar:vertical { width: 8px; background: #121820; }"
        "QScrollBar::handle:vertical { background: #4a6a88; min-height: 20px; border-radius: 3px; }"
    )
    empty = QLabel("Empty folder.\nSet Accounts → Email.")
    empty.setAlignment(Qt.AlignCenter)
    empty.setWordWrap(True)
    empty.setStyleSheet(
        f"color:{_MUTED}; font-size:10px; padding:8px;"
        f" background:{_SURFACE}; border-radius:10px;"
    )
    empty.setFixedWidth(108)
    empty.hide()
    left = QVBoxLayout()
    left.setSpacing(0)
    left.setContentsMargins(0, 0, 0, 0)
    left.addWidget(lst, 1)
    left.addWidget(empty, 1)
    split.addLayout(left, 0)

    preview = QWidget()
    preview.setStyleSheet(
        f"background:{_SURFACE}; border-radius:10px;"
        'QWidget[digiFocus="1"] { border:2px solid #FFE600; }'
    )
    pl = QVBoxLayout(preview)
    pl.setContentsMargins(6, 6, 6, 6)
    pl.setSpacing(2)
    p_from = QLabel("Select a message")
    p_from.setWordWrap(True)
    p_from.setStyleSheet(f"font-size:10px; font-weight:700; color:{_TEXT};")
    p_subj = QLabel("")
    p_subj.setWordWrap(True)
    p_subj.setStyleSheet(f"font-size:11px; font-weight:600; color:{_BLUE};")
    p_scroll = QScrollArea()
    p_scroll.setWidgetResizable(True)
    p_scroll.setFrameShape(QFrame.NoFrame)
    p_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
    p_body = QLabel("")
    p_body.setWordWrap(True)
    p_body.setAlignment(Qt.AlignTop | Qt.AlignLeft)
    p_body.setStyleSheet(f"font-size:10px; color:{_TEXT}; background:transparent;")
    p_scroll.setWidget(p_body)
    pl.addWidget(p_from)
    pl.addWidget(p_subj)
    pl.addWidget(p_scroll, 1)
    split.addWidget(preview, 1)
    il.addLayout(split, 1)

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

    state = {
        "messages": [],
        "busy": False,
        "pending": False,
        "panel": "inbox",
        "mailbox": "INBOX",
    }

    class _FetchBus(QObject):
        finished = pyqtSignal(object, str, str, str)  # messages, err, panel, mailbox

    class _BodyBus(QObject):
        finished = pyqtSignal(str, str, str)  # uid, text, err

    fetch_bus = _FetchBus()
    body_bus = _BodyBus()

    def _chip_style(key: str) -> None:
        active = state["panel"]
        for k, b in chip_btns.items():
            on = k == active
            b.setStyleSheet(
                f"QPushButton {{ font-size:7px; font-weight:{'700' if on else '600'};"
                f" padding:0px 1px; border:none; border-radius:7px;"
                f" color:{'#fff' if on else _TEXT};"
                f" background:{_RED if on else _CHIP}; }}"
                'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
            )

    def _clear_preview(hint: str = "Select a message") -> None:
        p_from.setText(hint)
        p_subj.setText("")
        p_body.setText("")

    def _show_preview(msg: dict) -> None:
        name = msg.get("from_name") or "Unknown"
        addr = msg.get("from_email") or ""
        p_from.setText(f"{name}" + (f"\n{addr}" if addr else ""))
        p_subj.setText(str(msg.get("subject") or "(no subject)"))
        p_body.setText(_reader_preview(msg))

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
            _clear_preview("This folder is empty")
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
        lst.setCurrentRow(0)
        _show_preview(messages[0])

    def _show_inbox() -> None:
        stack.setCurrentWidget(inbox)
        lst.setFocus(Qt.OtherFocusReason)

    def _reader_preview(msg: dict) -> str:
        body = str(msg.get("body") or "").strip()
        if body:
            return body
        snip = str(msg.get("snippet") or "").strip()
        if snip.casefold() in _PLACEHOLDER_SNIPS:
            snip = ""
        if snip:
            return snip
        if msg.get("uid"):
            return "Loading…"
        return "Open to load body."

    def _open_reader(msg: dict) -> None:
        try:
            name = msg.get("from_name") or "Unknown"
            # rebuild avatar
            while r_avatar_lay.count():
                w = r_avatar_lay.takeAt(0).widget()
                if w:
                    w.deleteLater()
            r_avatar_lay.addWidget(Avatar(_initial(name), _avatar_color(name), size=28))
            r_subj.setText(str(msg.get("subject") or "(no subject)"))
            addr = msg.get("from_email") or ""
            r_from.setText(f"{name}\n{addr}" if addr else name)
            r_when.setText(str(msg.get("when_full") or msg.get("when") or ""))
            r_body.setText(_reader_preview(msg))
            stack.setCurrentWidget(reader)
            r_back.setFocus(Qt.OtherFocusReason)
            # Lazy body fetch via stable IMAP UID
            if not str(msg.get("body") or "").strip() and msg.get("uid"):
                QTimer.singleShot(50, lambda m=msg: _fetch_body(m))
        except Exception as e:
            try:
                r_body.setText(f"(Could not open message)\n{e}")
                stack.setCurrentWidget(reader)
            except Exception:
                pass

    def _apply_body(uid: str, text: str, err: str) -> None:
        snip = ""
        if text:
            snip = _snippet_text(text)
            for m in state["messages"]:
                if _uid_str(m.get("uid") or "") == uid:
                    m["body"] = text[:4000]
                    if snip:
                        m["snippet"] = snip
                    m["unread"] = False
            _cache_set(state["messages"], state["panel"])
        if stack.currentWidget() is reader:
            if err and not text:
                r_body.setText(
                    f"(Could not load body)\n{err}\n\n"
                    f"{snip or ''}"
                )
            elif not text:
                r_body.setText(
                    f"(Could not load body)\nUID FETCH failed for {uid}"
                )
            else:
                r_body.setText(text[:4000] or "(empty message)")
        cur = lst.currentRow()
        if text and 0 <= cur < len(state["messages"]):
            if _uid_str(state["messages"][cur].get("uid") or "") == uid:
                p_body.setText(text[:4000] or "(empty message)")

    body_bus.finished.connect(_apply_body)

    def _fetch_body(msg: dict, for_preview: bool = False) -> None:
        del for_preview
        em = _creds()
        user = em.get("user") or ""
        password = em.get("pass") or ""
        host = em.get("host") or "imap.gmail.com"
        uid = _uid_str(msg.get("uid") or "")
        mailbox = state.get("mailbox") or "INBOX"
        if not user or not password or not uid:
            if stack.currentWidget() is reader:
                r_body.setText("(Missing account or message id)")
            return

        def work() -> None:
            text = ""
            err = ""
            try:
                uid_b = uid.encode("utf-8")
                M = imaplib.IMAP4_SSL(host, 993)
                M.login(user, password)
                M.select(mailbox)
                for spec in ("(BODY.PEEK[1])", "(BODY.PEEK[TEXT])"):
                    typ, data = M.uid("fetch", uid_b, spec)
                    payloads = _fetch_payload_parts(data)
                    if typ != "OK" or not payloads:
                        continue
                    blob = payloads[0][:12000]
                    if not blob or blob.strip().upper() == b"NIL":
                        continue
                    decoded = _decode_part_bytes(blob, "utf-8").strip()
                    if not decoded:
                        continue
                    if re.search(r"(?i)<html|</p>|<br\s*/?>", decoded[:600]):
                        decoded = _strip_html_preview(decoded)
                    if decoded.lstrip().startswith("--") and "Content-Type:" in decoded[:200]:
                        continue
                    text = decoded
                    if text:
                        break
                if not text:
                    typ, data = M.uid("fetch", uid_b, "(RFC822)")
                    payloads = _fetch_payload_parts(data)
                    if typ == "OK" and payloads:
                        raw = payloads[0][:200_000]
                        text = _extract_text(email_lib.message_from_bytes(raw))
                # Prefer full RFC822 parse when peek left QP artifacts
                if text and ("=0A" in text or "=0D" in text or "=\n" in text):
                    typ, data = M.uid("fetch", uid_b, "(RFC822)")
                    payloads = _fetch_payload_parts(data)
                    if typ == "OK" and payloads:
                        raw = payloads[0][:200_000]
                        text = _extract_text(email_lib.message_from_bytes(raw))
                try:
                    M.logout()
                except Exception:
                    pass
            except Exception as e:
                err = str(e)
            body_bus.finished.emit(uid, text, err)

        threading.Thread(target=work, name="imap-body", daemon=True).start()

    def _apply_fetch(messages: object, err: str, panel: str, mailbox: str) -> None:
        state["busy"] = False
        if mailbox:
            state["mailbox"] = mailbox
        if panel != state["panel"]:
            if state["pending"]:
                state["pending"] = False
                do_fetch()
            return
        msgs = list(messages) if isinstance(messages, list) else []
        if err:
            status.setText("Sync failed")
            empty.setText(f"Couldn't sync\n\n{_auth_hint(err, _creds().get('user') or '')}")
            if not state["messages"]:
                lst.hide()
                empty.show()
        else:
            _cache_set(msgs, panel)
            _fill_list(msgs)
            store.push_notif(
                "Email",
                f"{len(msgs)} in {title.text()}",
                "email",
                toast=False,
            )
            status.setText("Updated just now")
        if state["pending"]:
            state["pending"] = False
            do_fetch()

    fetch_bus.finished.connect(_apply_fetch)

    def do_fetch() -> None:
        if state["busy"]:
            state["pending"] = True
            return
        em = _creds()
        user = em.get("user") or ""
        password = em.get("pass") or ""
        host = em.get("host") or "imap.gmail.com"
        panel = state["panel"]
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
        prev_body = {
            _uid_str(m.get("uid") or ""): str(m.get("body") or "")
            for m in state["messages"]
            if m.get("uid") and m.get("body")
        }

        def work() -> None:
            messages: List[dict] = []
            err = ""
            mailbox = "INBOX"
            try:
                M = imaplib.IMAP4_SSL(host, 993)
                M.login(user, password)
                names = _imap_list_names(M)
                mailbox = _pick_mailbox(names, panel)
                typ, _sel = M.select(mailbox)
                if typ != "OK":
                    raise RuntimeError(f"Cannot open {mailbox}")
                typ, data = M.uid("search", None, "ALL")
                if typ != "OK" or not data or data[0] is None:
                    raise RuntimeError("UID SEARCH failed")
                ids = data[0].split()[-20:]
                for num in reversed(ids):
                    try:
                        uid_s = _uid_str(num)
                        typ, msg_data = M.uid(
                            "fetch",
                            num,
                            "(FLAGS BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)]"
                            " BODY.PEEK[1]<0.800>)",
                        )
                        if typ != "OK" or not msg_data:
                            typ, msg_data = M.uid(
                                "fetch",
                                num,
                                "(FLAGS BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])",
                            )
                        flags = _flags_from_fetch(msg_data)
                        payloads = _fetch_payload_parts(msg_data)
                        hdr_raw = payloads[0] if payloads else b""
                        peek_raw = payloads[1] if len(payloads) > 1 else b""
                        hdr = (
                            email_lib.message_from_bytes(hdr_raw)
                            if hdr_raw
                            else None
                        )
                        subj = _decode_hdr(hdr["Subject"]) if hdr else ""
                        frm = _decode_hdr(hdr["From"]) if hdr else ""
                        date_h = _decode_hdr(hdr["Date"]) if hdr else ""
                        dt = _parse_date(date_h)
                        unread = "\\Seen" not in flags
                        snip = _bytes_to_snippet(peek_raw)
                        if not snip:
                            try:
                                typ2, peek_data = M.uid(
                                    "fetch", num, "(BODY.PEEK[TEXT]<0.800>)"
                                )
                                peek2 = _fetch_payload_parts(peek_data)
                                if typ2 == "OK" and peek2:
                                    snip = _bytes_to_snippet(peek2[0])
                            except Exception:
                                snip = ""
                        messages.append(
                            {
                                "uid": uid_s,
                                "subject": subj or "(no subject)",
                                "from_name": _from_name(frm),
                                "from_email": _from_email(frm),
                                "when": _fmt_when(dt),
                                "when_full": date_h,
                                "snippet": snip,
                                "unread": unread,
                                "body": prev_body.get(uid_s, ""),
                            }
                        )
                    except Exception:
                        continue
                M.logout()
            except Exception as e:
                err = str(e)
            fetch_bus.finished.emit(messages, err, panel, mailbox)

        threading.Thread(target=work, name="imap-sync", daemon=True).start()

    def on_item(item: Optional[QListWidgetItem] = None) -> None:
        # Confirm / activate → full reader; arrows already drive the right pane
        row = lst.row(item) if item is not None else lst.currentRow()
        if row < 0:
            row = lst.currentRow()
        if 0 <= row < len(state["messages"]):
            _open_reader(state["messages"][row])

    def on_select() -> None:
        row = lst.currentRow()
        if 0 <= row < len(state["messages"]):
            _show_preview(state["messages"][row])
        elif not state["messages"]:
            _clear_preview("This folder is empty")

    def set_panel(key: str) -> None:
        state["panel"] = key
        state["mailbox"] = _PANEL_ALIASES.get(key, ("INBOX",))[0]
        label = dict(_PANELS).get(key, "Mail")
        title.setText(label)
        r_back.setText(f"← {label}")
        _chip_style(key)
        cached = _cache_get(key)
        if cached:
            _fill_list(cached)
            status.setText("Cached · syncing…")
        else:
            _fill_list([])
            empty.show()
            lst.hide()
        do_fetch()

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

    compose_btn.clicked.connect(lambda: open_compose())
    lst.itemActivated.connect(on_item)
    lst.currentRowChanged.connect(lambda _i: on_select())
    for key, b in chip_btns.items():
        b.clicked.connect(lambda _=False, k=key: set_panel(k))
    r_back.clicked.connect(_show_inbox)
    c_back.clicked.connect(_show_inbox)
    c_send.clicked.connect(do_send)

    _chip_style("inbox")
    _set_acct()
    cached = _cache_get("inbox")
    if cached:
        _fill_list(cached)
        status.setText("Cached")
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

    def on_page_show() -> None:
        _set_acct()
        if stack.currentWidget() is inbox:
            do_fetch()

    chrome.on_hardware_back = on_hardware_back  # type: ignore[attr-defined]
    chrome.compose_to = compose_to  # type: ignore[attr-defined]
    chrome.prefill_to = prefill_to  # type: ignore[attr-defined]
    chrome.on_page_show = on_page_show  # type: ignore[attr-defined]
    return chrome
