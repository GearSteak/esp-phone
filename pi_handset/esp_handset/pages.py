"""Handset app pages — ESP Phone feature parity (wired + stubs)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap, QTextCursor
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from esp_handset import pi_camera

DATA = Path.home() / ".esp-handset"
CONTACTS = DATA / "contacts.json"
CONTACT_PHOTOS = DATA / "contact_photos"
SMS_LOG = DATA / "sms.json"
LORA_LOG = DATA / "lora.json"
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
    """Classic T9 dial pad: big typed-number display + 3×4 keypad."""
    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(4)

    dial = QLineEdit()
    dial.setObjectName("dialDisplay")
    dial.setReadOnly(True)
    dial.setAlignment(Qt.AlignCenter)
    dial.setPlaceholderText("Enter number")
    dial.setMinimumHeight(40)
    dial.setStyleSheet(
        "font-size: 22px; font-weight: 700; font-family: monospace;"
        "padding: 8px 4px; letter-spacing: 1px;"
    )
    lay.addWidget(dial)

    # T9 labels (classic phone letters under the digit)
    keys = [
        ("1", ""),
        ("2", "ABC"),
        ("3", "DEF"),
        ("4", "GHI"),
        ("5", "JKL"),
        ("6", "MNO"),
        ("7", "PQRS"),
        ("8", "TUV"),
        ("9", "WXYZ"),
        ("*", ""),
        ("0", "+"),
        ("#", ""),
    ]

    def append_digit(ch: str) -> None:
        # Long-press style: 0 key can also add + via its letter row — tap 0 → 0
        dial.setText(dial.text() + ch)
        dial.setCursorPosition(len(dial.text()))

    def backspace() -> None:
        dial.setText(dial.text()[:-1])

    def do_call() -> None:
        num = dial.text().strip()
        if not num:
            on_status("Enter a number")
            return
        os.system(f"linphonecsh dial {num} >/dev/null 2>&1 &")
        log = _load_json(CALL_LOG, [])
        log.insert(0, {"dir": "out", "number": num, "at": datetime.now().isoformat()})
        _save_json(CALL_LOG, log[:100])
        on_status(f"Dialing {num}")

    def do_end() -> None:
        os.system("linphonecsh generic 'terminate' >/dev/null 2>&1 &")
        on_status("Call ended")

    grid = QGridLayout()
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(3)
    grid.setVerticalSpacing(3)
    for i, (digit, letters) in enumerate(keys):
        label = digit if not letters else f"{digit}\n{letters}"
        btn = QPushButton(label)
        btn.setMinimumHeight(36)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        btn.setStyleSheet(
            "font-size: 14px; font-weight: 800; padding: 2px;"
            "line-height: 1.05;"
        )
        # 0 → digit; hold-style + available as separate action below
        btn.clicked.connect(lambda _=False, c=digit: append_digit(c))
        grid.addWidget(btn, i // 3, i % 3)
    lay.addLayout(grid, 1)

    actions = QHBoxLayout()
    actions.setSpacing(3)
    del_btn = QPushButton("⌫")
    del_btn.setMinimumHeight(32)
    del_btn.setToolTip("Delete")
    del_btn.clicked.connect(backspace)
    plus_btn = QPushButton("+")
    plus_btn.setMinimumHeight(32)
    plus_btn.setFixedWidth(36)
    plus_btn.clicked.connect(lambda: append_digit("+"))
    call = QPushButton("Call")
    call.setMinimumHeight(32)
    call.setStyleSheet("font-weight:800; background:#1a7a3a;")
    call.clicked.connect(do_call)
    end = QPushButton("End")
    end.setMinimumHeight(32)
    end.setStyleSheet("font-weight:800; background:#8a2020;")
    end.clicked.connect(do_end)
    actions.addWidget(del_btn)
    actions.addWidget(plus_btn)
    actions.addWidget(call, 1)
    actions.addWidget(end, 1)
    lay.addLayout(actions)

    if on_call_log:
        log_btn = QPushButton("Call log")
        log_btn.setMinimumHeight(26)
        log_btn.clicked.connect(on_call_log)
        lay.addWidget(log_btn)

    page = page_chrome("Phone", body, on_back, scroll=False)

    def set_dial_number(number: str) -> None:
        dial.setText(str(number or "").strip())
        dial.setCursorPosition(len(dial.text()))

    page.set_dial_number = set_dial_number  # type: ignore[attr-defined]
    return page


def _digits_tail(num: str, n: int = 10) -> str:
    d = "".join(c for c in str(num or "") if c.isdigit())
    return d[-n:] if d else ""


def _normalize_contact(c: dict) -> dict:
    """One contact card: name + phone / LoRa / email + optional photo."""
    phone = str(c.get("phone") or c.get("number") or "").strip()
    lora = str(c.get("lora") or c.get("lora_id") or "").strip()
    email = str(c.get("email") or "").strip()
    image = str(c.get("image") or "").strip()
    name = str(c.get("name") or "").strip()
    if not name:
        name = phone or lora or email or "Unknown"
    return {
        "name": name,
        "phone": phone,
        "number": phone,  # legacy alias used by dialer/SMS
        "lora": lora,
        "email": email,
        "image": image,
    }


def _contact_identity_ok(c: dict) -> bool:
    return bool(c.get("phone") or c.get("lora") or c.get("email"))


def _load_contacts() -> List[dict]:
    raw = _load_json(CONTACTS, [])
    if not isinstance(raw, list):
        return []
    out = [_normalize_contact(c) for c in raw if isinstance(c, dict)]
    return [c for c in out if _contact_identity_ok(c)]


def _save_contacts(contacts: List[dict]) -> None:
    cleaned = [_normalize_contact(c) for c in contacts if isinstance(c, dict)]
    cleaned = [c for c in cleaned if _contact_identity_ok(c)]
    cleaned.sort(
        key=lambda c: (
            str(c.get("name") or "").casefold(),
            str(c.get("phone") or c.get("lora") or c.get("email") or ""),
        )
    )
    _save_json(CONTACTS, cleaned)


def _contact_photo_file(c: dict) -> Optional[Path]:
    img = str(c.get("image") or "").strip()
    if not img:
        return None
    p = Path(img)
    if not p.is_absolute():
        p = CONTACT_PHOTOS / img
    return p if p.is_file() else None


def _import_contact_photo(src: Path, stem: str) -> str:
    """Copy image into contact_photos/; return relative filename."""
    CONTACT_PHOTOS.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (stem or "contact"))[:24]
    ext = src.suffix.lower() if src.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"
    name = f"{safe}_{int(datetime.now().timestamp())}{ext}"
    dest = CONTACT_PHOTOS / name
    shutil.copy2(src, dest)
    return name


def _lookup_contact(
    *, phone: str = "", lora: str = "", email: str = ""
) -> Optional[dict]:
    phone = str(phone or "").strip()
    lora = str(lora or "").strip()
    email = str(email or "").strip().casefold()
    tail = _digits_tail(phone)
    for c in _load_contacts():
        cphone = str(c.get("phone") or "")
        if phone and (cphone == phone or (tail and _digits_tail(cphone) == tail)):
            return c
        if lora and str(c.get("lora") or "") == lora:
            return c
        if email and str(c.get("email") or "").casefold() == email:
            return c
    return None


def _contact_display(
    *, phone: str = "", lora: str = "", email: str = "", fallback: str = ""
) -> Tuple[str, str, Optional[str]]:
    """Return (display_name, initial, photo_path_or_None)."""
    key = fallback or phone or lora or email or "Unknown"
    c = _lookup_contact(phone=phone, lora=lora, email=email)
    if c:
        name = str(c.get("name") or key)
        initial = name[:1].upper() if name else "?"
        if not initial.isalnum():
            initial = "#"
        photo = _contact_photo_file(c)
        return name, initial, str(photo) if photo else None
    name = key
    initial = name[:1].upper() if name else "?"
    if not initial.isalnum():
        initial = "#"
    return name, initial, None


def _avatar_color(key: str) -> str:
    palette = (
        "#2a6f97",
        "#3d7a4a",
        "#8a4a2a",
        "#6a3d8a",
        "#2a7a7a",
        "#8a3d5c",
        "#4a5a8a",
        "#7a6a2a",
    )
    return palette[sum(ord(c) for c in (key or "?")) % len(palette)]


def _make_avatar_label(
    name: str, initial: str, photo_path: Optional[str] = None, size: int = 36
) -> QLabel:
    avatar = QLabel()
    avatar.setAlignment(Qt.AlignCenter)
    avatar.setFixedSize(size, size)
    avatar.setFocusPolicy(Qt.NoFocus)
    if photo_path:
        pix = QPixmap(photo_path)
        if not pix.isNull():
            scaled = pix.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            # Circular crop via mask-ish: just show scaled square with radius stylesheet
            avatar.setPixmap(scaled.copy(0, 0, size, size))
            avatar.setStyleSheet(
                f"border-radius:{size // 2}px; background:#243040;"
            )
            avatar.setScaledContents(True)
            return avatar
    color = _avatar_color(name or initial)
    avatar.setText(initial or "?")
    avatar.setStyleSheet(
        f"background:{color}; color:#fff; border-radius:{size // 2}px;"
        f"font-size:{max(11, size // 2 - 4)}px; font-weight:800;"
    )
    return avatar


def _normalize_sms_msg(raw) -> dict:
    """Normalize legacy string messages and dict messages."""
    if isinstance(raw, dict):
        text = str(raw.get("text") or "")
        direction = str(raw.get("dir") or "in").lower()
        if direction not in ("in", "out"):
            direction = "out" if text.startswith(">") else "in"
        return {
            "dir": direction,
            "text": text[2:].lstrip() if text.startswith("> ") and direction == "out" else text,
            "at": str(raw.get("at") or ""),
            "read": bool(raw.get("read", direction == "out")),
        }
    s = str(raw or "")
    if s.startswith("> "):
        return {"dir": "out", "text": s[2:], "at": "", "read": True}
    if s.startswith(">"):
        return {"dir": "out", "text": s[1:].lstrip(), "at": "", "read": True}
    return {"dir": "in", "text": s, "at": "", "read": True}


def _load_sms_threads() -> dict:
    raw = _load_json(SMS_LOG, {})
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for num, msgs in raw.items():
        if not isinstance(msgs, list):
            continue
        out[str(num)] = [_normalize_sms_msg(m) for m in msgs]
    return out


def _save_sms_threads(threads: dict) -> None:
    _save_json(SMS_LOG, threads)


def _load_lora_threads() -> dict:
    raw = _load_json(LORA_LOG, {})
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for peer, msgs in raw.items():
        if not isinstance(msgs, list):
            continue
        out[str(peer)] = [_normalize_sms_msg(m) for m in msgs]
    return out


def _save_lora_threads(threads: dict) -> None:
    _save_json(LORA_LOG, threads)


def _parse_lora_rx_line(line: str) -> Optional[Tuple[str, str]]:
    """Parse 'LORA RX <deviceId text' → (peer_id, text)."""
    if not line.startswith("LORA RX"):
        return None
    rest = line[7:].strip()
    if rest.startswith("<"):
        body = rest[1:].strip()
        peer, _, text = body.partition(" ")
        if peer:
            return peer.strip(), text.strip()
    if rest.lower().startswith("delivered by"):
        return None
    return "mesh", rest


def _msg_preview(msg: dict) -> str:
    text = str(msg.get("text") or "").replace("\n", " ").strip()
    if msg.get("dir") == "out":
        text = f"You: {text}" if text else "You: "
    return text


def _elide_one_line(text: str, max_chars: int = 34) -> str:
    t = (text or "").replace("\n", " ").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def _chat_bubble(msg: dict) -> QWidget:
    outgoing = msg.get("dir") == "out"
    text = str(msg.get("text") or "")
    wrap = QWidget()
    wrap.setFocusPolicy(Qt.NoFocus)
    h = QHBoxLayout(wrap)
    h.setContentsMargins(2, 1, 2, 1)
    h.setSpacing(0)
    if outgoing:
        h.addStretch(1)
    bubble = QLabel(text)
    bubble.setWordWrap(True)
    bubble.setFocusPolicy(Qt.NoFocus)
    bubble.setMaximumWidth(180)
    if outgoing:
        bubble.setStyleSheet(
            "background:#1f6feb; color:#fff; border-radius:8px;"
            "padding:6px 8px; font-size:11px;"
        )
    else:
        bubble.setStyleSheet(
            "background:#243040; color:#e8eef5; border-radius:8px;"
            "padding:6px 8px; font-size:11px;"
        )
    h.addWidget(bubble)
    if not outgoing:
        h.addStretch(1)
    return wrap


def _chat_conv_row(
    title: str,
    preview: str,
    *,
    initial: str,
    photo: Optional[str] = None,
    unread: bool = False,
) -> QWidget:
    row = QWidget()
    row.setFocusPolicy(Qt.NoFocus)
    h = QHBoxLayout(row)
    h.setContentsMargins(4, 4, 4, 4)
    h.setSpacing(6)
    h.addWidget(_make_avatar_label(title, initial, photo, 36))

    text_col = QVBoxLayout()
    text_col.setSpacing(1)
    text_col.setContentsMargins(0, 0, 0, 0)
    name_row = QHBoxLayout()
    name_row.setSpacing(4)
    name_lab = QLabel(title)
    name_lab.setStyleSheet("font-size:12px; font-weight:700; color:#e8eef5;")
    name_lab.setFocusPolicy(Qt.NoFocus)
    name_row.addWidget(name_lab, 1)
    if unread:
        badge = QLabel("●")
        badge.setStyleSheet("color:#FFE600; font-size:14px; font-weight:800;")
        badge.setFixedWidth(14)
        badge.setFocusPolicy(Qt.NoFocus)
        name_row.addWidget(badge)
    text_col.addLayout(name_row)
    prev_lab = QLabel(preview or "(no messages)")
    prev_lab.setStyleSheet(
        "font-size:10px; color:#cde; font-weight:600;"
        if unread
        else "font-size:10px; color:#9ab;"
    )
    prev_lab.setFocusPolicy(Qt.NoFocus)
    prev_lab.setWordWrap(False)
    text_col.addWidget(prev_lab)
    h.addLayout(text_col, 1)
    for child in row.findChildren(QWidget):
        child.setFocusPolicy(Qt.NoFocus)
    return row


def make_sms_page(
    modem,
    on_back,
    on_status,
    get_modem: Optional[Callable] = None,
) -> QWidget:
    """Conversation inbox + thread view (avatar, unread badge, one-line preview)."""
    from esp_handset import digi_nav

    root = QWidget()
    stack = QStackedWidget(root)
    outer = QVBoxLayout(root)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(stack)

    # ----- Inbox -----
    inbox = QWidget()
    in_lay = QVBoxLayout(inbox)
    in_lay.setContentsMargins(2, 2, 2, 2)
    in_lay.setSpacing(4)

    conv_list = QListWidget()
    conv_list.setSpacing(2)
    conv_list.setStyleSheet(
        "QListWidget { background: transparent; border: none; outline: none; }"
        "QListWidget::item { background: #152030; border-radius: 6px;"
        "  margin: 1px 0; padding: 0; }"
        "QListWidget::item:selected { background: #243448;"
        "  border: 2px solid #FFE600; }"
    )
    in_lay.addWidget(conv_list, 1)

    new_btn = QPushButton("＋ New message")
    new_btn.setMinimumHeight(30)
    new_btn.setStyleSheet("font-weight:700;")
    in_lay.addWidget(new_btn)

    # New-message form (number entry)
    new_form = QWidget()
    new_form.setVisible(False)
    nf_lay = QVBoxLayout(new_form)
    nf_lay.setContentsMargins(0, 0, 0, 0)
    nf_lay.setSpacing(3)
    new_to = QLineEdit()
    new_to.setPlaceholderText("Phone number")
    nf_row = QHBoxLayout()
    new_open = QPushButton("Open")
    new_open.setStyleSheet("font-weight:700;")
    new_cancel = QPushButton("Cancel")
    nf_row.addWidget(new_open, 1)
    nf_row.addWidget(new_cancel, 1)
    nf_lay.addWidget(new_to)
    nf_lay.addLayout(nf_row)
    in_lay.addWidget(new_form)

    stack.addWidget(inbox)

    # ----- Thread -----
    thread = QWidget()
    th_lay = QVBoxLayout(thread)
    th_lay.setContentsMargins(2, 2, 2, 2)
    th_lay.setSpacing(3)

    thread_title = QLabel("Chat")
    thread_title.setStyleSheet("font-size:12px; font-weight:700;")
    thread_title.setWordWrap(True)
    th_lay.addWidget(thread_title)

    msg_list = QListWidget()
    msg_list.setStyleSheet(
        "QListWidget { background: transparent; border: none; outline: none; }"
        "QListWidget::item { background: transparent; margin: 2px 0; padding: 0; }"
        "QListWidget::item:selected { background: rgba(255,230,0,0.12);"
        "  border: 1px solid #FFE600; border-radius: 4px; }"
    )
    th_lay.addWidget(msg_list, 1)

    compose_row = QHBoxLayout()
    compose_row.setSpacing(3)
    compose = QLineEdit()
    compose.setPlaceholderText("Type a message…")
    compose.setMinimumHeight(30)
    send_btn = QPushButton("Send")
    send_btn.setMinimumHeight(30)
    send_btn.setFixedWidth(52)
    send_btn.setStyleSheet("font-weight:800;")
    compose_row.addWidget(compose, 1)
    compose_row.addWidget(send_btn)
    th_lay.addLayout(compose_row)

    stack.addWidget(thread)

    state = {"peer": ""}

    def _active_modem():
        if get_modem:
            try:
                return get_modem()
            except Exception:
                pass
        return modem

    def _build_conv_row(number: str, msgs: list) -> QWidget:
        name, initial, photo = _contact_display(phone=number, fallback=number)
        last = msgs[-1] if msgs else {"text": "", "dir": "in"}
        preview = _elide_one_line(_msg_preview(last))
        unread = any(
            m.get("dir") == "in" and not m.get("read", True) for m in msgs
        )
        return _chat_conv_row(
            name, preview, initial=initial, photo=photo, unread=unread
        )

    def show_inbox() -> None:
        state["peer"] = ""
        new_form.setVisible(False)
        stack.setCurrentWidget(inbox)
        refresh_inbox()
        digi_nav.ensure_page_focus(chrome)

    def refresh_inbox() -> None:
        threads = _load_sms_threads()
        # Sort by last message presence — newest activity first (stable by number)
        items = list(threads.items())

        def sort_key(pair):
            num, msgs = pair
            last_at = ""
            if msgs:
                last_at = str(msgs[-1].get("at") or "")
            return (last_at, num)

        items.sort(key=sort_key, reverse=True)
        conv_list.clear()
        if not items:
            empty = QListWidgetItem("No conversations yet.\n＋ New message below.")
            empty.setFlags(Qt.NoItemFlags)
            conv_list.addItem(empty)
            return
        for num, msgs in items:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, num)
            item.setSizeHint(QSize(200, 48))
            conv_list.addItem(item)
            conv_list.setItemWidget(item, _build_conv_row(num, msgs))

    def mark_read(number: str) -> None:
        threads = _load_sms_threads()
        msgs = threads.get(number)
        if not msgs:
            return
        changed = False
        for m in msgs:
            if m.get("dir") == "in" and not m.get("read", True):
                m["read"] = True
                changed = True
        if changed:
            threads[number] = msgs
            _save_sms_threads(threads)

    def open_thread(number: str) -> None:
        number = str(number or "").strip()
        if not number:
            return
        state["peer"] = number
        name, _, _ = _contact_display(phone=number, fallback=number)
        thread_title.setText(name if name != number else number)
        if name != number:
            thread_title.setText(f"{name}\n{number}")
        mark_read(number)
        refresh_thread()
        stack.setCurrentWidget(thread)
        compose.clear()
        digi_nav.ensure_page_focus(chrome)
        # Prefer landing on compose for typing
        compose.setFocus(Qt.OtherFocusReason)

    def refresh_thread() -> None:
        peer = state["peer"]
        msg_list.clear()
        if not peer:
            return
        threads = _load_sms_threads()
        msgs = threads.get(peer, [])
        if not msgs:
            item = QListWidgetItem("No messages yet — say hi.")
            item.setFlags(Qt.NoItemFlags)
            msg_list.addItem(item)
            return
        for m in msgs:
            item = QListWidgetItem()
            item.setSizeHint(QSize(200, 44))
            msg_list.addItem(item)
            bubble = _chat_bubble(m)
            bubble.adjustSize()
            hint_h = max(36, bubble.sizeHint().height() + 4)
            item.setSizeHint(QSize(200, hint_h))
            msg_list.setItemWidget(item, bubble)
        msg_list.scrollToBottom()

    def open_selected() -> None:
        item = conv_list.currentItem()
        if item is None:
            return
        num = item.data(Qt.UserRole)
        if num:
            open_thread(str(num))

    def start_new() -> None:
        new_form.setVisible(True)
        new_to.setFocus(Qt.OtherFocusReason)
        digi_nav.clear_highlights(chrome)
        digi_nav._highlight(new_to, True)

    def cancel_new() -> None:
        new_form.setVisible(False)
        new_to.clear()
        digi_nav.ensure_page_focus(chrome)

    def open_new() -> None:
        num = new_to.text().strip()
        if not num:
            on_status("Enter a number")
            return
        new_form.setVisible(False)
        # Ensure thread exists
        threads = _load_sms_threads()
        threads.setdefault(num, [])
        _save_sms_threads(threads)
        open_thread(num)

    def do_send() -> None:
        peer = state["peer"]
        text = compose.text().strip().replace("\n", " ")
        if not peer or not text:
            return
        m = _active_modem()
        if not m:
            QMessageBox.warning(root, "SMS", "SIM7600 not connected")
            return
        try:
            ok = m.send_sms(peer, text)
        except Exception as e:
            QMessageBox.warning(root, "SMS", str(e))
            return
        if not ok:
            QMessageBox.warning(root, "SMS", "Send failed")
            return
        threads = _load_sms_threads()
        threads.setdefault(peer, []).append(
            {
                "dir": "out",
                "text": text,
                "at": datetime.now().isoformat(),
                "read": True,
            }
        )
        _save_sms_threads(threads)
        compose.clear()
        refresh_thread()
        on_status(f"SMS sent to {peer}")

    def chrome_back() -> None:
        if stack.currentWidget() is thread:
            show_inbox()
        elif new_form.isVisible():
            cancel_new()
        else:
            on_back()

    def on_hardware_back() -> bool:
        if stack.currentWidget() is thread:
            show_inbox()
            return True
        if new_form.isVisible():
            cancel_new()
            return True
        return False

    def refresh_sms() -> None:
        if stack.currentWidget() is thread and state["peer"]:
            # Live update open chat; mark new as read while viewing
            mark_read(state["peer"])
            refresh_thread()
        refresh_inbox()

    conv_list.itemActivated.connect(lambda _i: open_selected())
    conv_list.itemClicked.connect(lambda _i: open_selected())
    new_btn.clicked.connect(start_new)
    new_open.clicked.connect(open_new)
    new_cancel.clicked.connect(cancel_new)
    send_btn.clicked.connect(do_send)
    compose.returnPressed.connect(do_send)

    chrome = page_chrome("Messages", root, chrome_back, scroll=False)
    chrome.refresh_sms = refresh_sms  # type: ignore[attr-defined]
    chrome.on_hardware_back = on_hardware_back  # type: ignore[attr-defined]
    chrome.open_sms_thread = open_thread  # type: ignore[attr-defined]

    refresh_inbox()
    stack.setCurrentWidget(inbox)
    return chrome


def make_contacts_page(
    on_back,
    open_dial: Callable[[str], None],
    open_sms: Optional[Callable[[str], None]] = None,
    open_lora: Optional[Callable[[str], None]] = None,
    open_email: Optional[Callable[[str], None]] = None,
) -> QWidget:
    """Contact book: photo + phone / LoRa / email; Call · SMS · LoRa · Email."""
    from PyQt5.QtWidgets import QFileDialog

    from esp_handset import digi_nav

    root = QWidget()
    stack = QStackedWidget(root)
    outer = QVBoxLayout(root)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(stack)

    # ----- List -----
    list_page = QWidget()
    list_lay = QVBoxLayout(list_page)
    list_lay.setContentsMargins(2, 2, 2, 2)
    list_lay.setSpacing(4)

    conv_list = QListWidget()
    conv_list.setSpacing(2)
    conv_list.setStyleSheet(
        "QListWidget { background: transparent; border: none; outline: none; }"
        "QListWidget::item { background: #152030; border-radius: 6px;"
        "  margin: 1px 0; padding: 0; }"
        "QListWidget::item:selected { background: #243448;"
        "  border: 2px solid #FFE600; }"
    )
    list_lay.addWidget(conv_list, 1)
    add_btn = QPushButton("＋ Add contact")
    add_btn.setMinimumHeight(30)
    add_btn.setStyleSheet("font-weight:700;")
    list_lay.addWidget(add_btn)
    stack.addWidget(list_page)

    # ----- Detail -----
    detail = QWidget()
    d_lay = QVBoxLayout(detail)
    d_lay.setContentsMargins(2, 2, 2, 2)
    d_lay.setSpacing(4)
    d_avatar_host = QHBoxLayout()
    d_avatar_slot = QVBoxLayout()
    d_avatar_host.addStretch(1)
    d_avatar_host.addLayout(d_avatar_slot)
    d_avatar_host.addStretch(1)
    d_lay.addLayout(d_avatar_host)
    d_name = QLabel("Contact")
    d_name.setAlignment(Qt.AlignCenter)
    d_name.setStyleSheet("font-size:14px; font-weight:800;")
    d_name.setWordWrap(True)
    d_lay.addWidget(d_name)
    d_info = QLabel("")
    d_info.setAlignment(Qt.AlignCenter)
    d_info.setStyleSheet("font-size:10px; color:#9ab;")
    d_info.setWordWrap(True)
    d_lay.addWidget(d_info)
    act = QVBoxLayout()
    act.setSpacing(3)
    btn_call = QPushButton("Call")
    btn_sms = QPushButton("SMS")
    btn_lora = QPushButton("LoRa")
    btn_email = QPushButton("Email")
    btn_edit = QPushButton("Edit")
    for b in (btn_call, btn_sms, btn_lora, btn_email, btn_edit):
        b.setMinimumHeight(30)
        b.setStyleSheet("font-weight:700;")
        act.addWidget(b)
    d_lay.addLayout(act)
    d_lay.addStretch(1)
    stack.addWidget(detail)

    # ----- Edit / Add form -----
    form = QWidget()
    f_lay = QVBoxLayout(form)
    f_lay.setContentsMargins(2, 2, 2, 2)
    f_lay.setSpacing(3)
    name_ed = QLineEdit()
    name_ed.setPlaceholderText("Name")
    phone_ed = QLineEdit()
    phone_ed.setPlaceholderText("Phone")
    lora_ed = QLineEdit()
    lora_ed.setPlaceholderText("LoRa ID")
    email_ed = QLineEdit()
    email_ed.setPlaceholderText("Email")
    photo_lab = QLabel("No photo")
    photo_lab.setStyleSheet("font-size:10px; color:#9ab;")
    photo_lab.setWordWrap(True)
    photo_row = QHBoxLayout()
    pick_photo = QPushButton("Photo")
    clear_photo = QPushButton("Clear")
    photo_row.addWidget(pick_photo, 1)
    photo_row.addWidget(clear_photo, 1)
    save_btn = QPushButton("Save")
    save_btn.setStyleSheet("font-weight:800;")
    save_btn.setMinimumHeight(30)
    cancel_btn = QPushButton("Cancel")
    cancel_btn.setMinimumHeight(28)
    for w in (name_ed, phone_ed, lora_ed, email_ed):
        f_lay.addWidget(w)
    f_lay.addWidget(photo_lab)
    f_lay.addLayout(photo_row)
    f_lay.addWidget(save_btn)
    f_lay.addWidget(cancel_btn)
    f_lay.addStretch(1)
    stack.addWidget(form)

    state = {"index": -1, "image": "", "mode": "add"}  # mode add|edit
    avatar_widget: list = [None]

    def _channels_line(c: dict) -> str:
        bits = []
        if c.get("phone"):
            bits.append(str(c["phone"]))
        if c.get("lora"):
            bits.append(f"LoRa {c['lora']}")
        if c.get("email"):
            bits.append(str(c["email"]))
        return " · ".join(bits) if bits else "No channels"

    def _clear_avatar_slot() -> None:
        while d_avatar_slot.count():
            item = d_avatar_slot.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        avatar_widget[0] = None

    def show_list() -> None:
        stack.setCurrentWidget(list_page)
        refresh_list()
        digi_nav.ensure_page_focus(chrome)

    def refresh_list() -> None:
        contacts = _load_contacts()
        _save_contacts(contacts)  # normalize + sort on disk
        conv_list.clear()
        if not contacts:
            empty = QListWidgetItem("No contacts yet.\n＋ Add below.")
            empty.setFlags(Qt.NoItemFlags)
            conv_list.addItem(empty)
            return
        for i, c in enumerate(contacts):
            name = str(c.get("name") or "Unknown")
            initial = name[:1].upper() if name else "?"
            if not initial.isalnum():
                initial = "#"
            photo = _contact_photo_file(c)
            preview = _elide_one_line(_channels_line(c), 32)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, i)
            item.setSizeHint(QSize(200, 48))
            conv_list.addItem(item)
            conv_list.setItemWidget(
                item,
                _chat_conv_row(
                    name,
                    preview,
                    initial=initial,
                    photo=str(photo) if photo else None,
                    unread=False,
                ),
            )

    def open_detail(index: int) -> None:
        contacts = _load_contacts()
        if index < 0 or index >= len(contacts):
            return
        state["index"] = index
        c = contacts[index]
        name = str(c.get("name") or "Unknown")
        initial = name[:1].upper() if name else "?"
        if not initial.isalnum():
            initial = "#"
        photo = _contact_photo_file(c)
        _clear_avatar_slot()
        av = _make_avatar_label(name, initial, str(photo) if photo else None, 56)
        d_avatar_slot.addWidget(av)
        avatar_widget[0] = av
        d_name.setText(name)
        d_info.setText(_channels_line(c))
        btn_call.setEnabled(bool(c.get("phone")))
        btn_sms.setEnabled(bool(c.get("phone")) and open_sms is not None)
        btn_lora.setEnabled(bool(c.get("lora")) and open_lora is not None)
        btn_email.setEnabled(bool(c.get("email")) and open_email is not None)
        stack.setCurrentWidget(detail)
        digi_nav.ensure_page_focus(chrome)

    def open_selected() -> None:
        item = conv_list.currentItem()
        if item is None:
            return
        idx = item.data(Qt.UserRole)
        if idx is None:
            return
        open_detail(int(idx))

    def fill_form(c: Optional[dict]) -> None:
        c = c or {}
        name_ed.setText(str(c.get("name") or ""))
        phone_ed.setText(str(c.get("phone") or ""))
        lora_ed.setText(str(c.get("lora") or ""))
        email_ed.setText(str(c.get("email") or ""))
        state["image"] = str(c.get("image") or "")
        if state["image"]:
            photo_lab.setText(f"Photo: {Path(state['image']).name}")
        else:
            photo_lab.setText("No photo")

    def show_add() -> None:
        state["mode"] = "add"
        state["index"] = -1
        fill_form(None)
        stack.setCurrentWidget(form)
        name_ed.setFocus(Qt.OtherFocusReason)
        digi_nav.ensure_page_focus(chrome)

    def show_edit() -> None:
        contacts = _load_contacts()
        idx = state["index"]
        if idx < 0 or idx >= len(contacts):
            return
        state["mode"] = "edit"
        fill_form(contacts[idx])
        stack.setCurrentWidget(form)
        digi_nav.ensure_page_focus(chrome)

    def do_pick_photo() -> None:
        start = str(PHOTOS if PHOTOS.is_dir() else Path.home() / "Pictures")
        fn, _ = QFileDialog.getOpenFileName(
            form,
            "Contact photo",
            start,
            "Images (*.jpg *.jpeg *.png *.webp *.bmp)",
        )
        if not fn:
            return
        try:
            rel = _import_contact_photo(Path(fn), name_ed.text().strip() or "contact")
            state["image"] = rel
            photo_lab.setText(f"Photo: {rel}")
        except Exception as e:
            QMessageBox.warning(form, "Photo", str(e))

    def do_clear_photo() -> None:
        state["image"] = ""
        photo_lab.setText("No photo")

    def do_save() -> None:
        c = _normalize_contact(
            {
                "name": name_ed.text().strip(),
                "phone": phone_ed.text().strip(),
                "lora": lora_ed.text().strip(),
                "email": email_ed.text().strip(),
                "image": state["image"],
            }
        )
        if not _contact_identity_ok(c):
            QMessageBox.warning(
                form, "Contacts", "Need at least phone, LoRa ID, or email."
            )
            return
        contacts = _load_contacts()
        if state["mode"] == "edit" and 0 <= state["index"] < len(contacts):
            contacts[state["index"]] = c
        else:
            contacts.append(c)
        _save_contacts(contacts)
        show_list()

    def do_call() -> None:
        contacts = _load_contacts()
        idx = state["index"]
        if 0 <= idx < len(contacts) and contacts[idx].get("phone"):
            open_dial(str(contacts[idx]["phone"]))

    def do_sms() -> None:
        contacts = _load_contacts()
        idx = state["index"]
        if open_sms and 0 <= idx < len(contacts) and contacts[idx].get("phone"):
            open_sms(str(contacts[idx]["phone"]))

    def do_lora() -> None:
        contacts = _load_contacts()
        idx = state["index"]
        if open_lora and 0 <= idx < len(contacts) and contacts[idx].get("lora"):
            open_lora(str(contacts[idx]["lora"]))

    def do_email() -> None:
        contacts = _load_contacts()
        idx = state["index"]
        if open_email and 0 <= idx < len(contacts) and contacts[idx].get("email"):
            open_email(str(contacts[idx]["email"]))

    def chrome_back() -> None:
        cur = stack.currentWidget()
        if cur is form:
            if state["mode"] == "edit" and state["index"] >= 0:
                open_detail(state["index"])
            else:
                show_list()
        elif cur is detail:
            show_list()
        else:
            on_back()

    def on_hardware_back() -> bool:
        cur = stack.currentWidget()
        if cur is form:
            if state["mode"] == "edit" and state["index"] >= 0:
                open_detail(state["index"])
            else:
                show_list()
            return True
        if cur is detail:
            show_list()
            return True
        return False

    conv_list.itemActivated.connect(lambda _i: open_selected())
    conv_list.itemClicked.connect(lambda _i: open_selected())
    add_btn.clicked.connect(show_add)
    btn_call.clicked.connect(do_call)
    btn_sms.clicked.connect(do_sms)
    btn_lora.clicked.connect(do_lora)
    btn_email.clicked.connect(do_email)
    btn_edit.clicked.connect(show_edit)
    pick_photo.clicked.connect(do_pick_photo)
    clear_photo.clicked.connect(do_clear_photo)
    save_btn.clicked.connect(do_save)
    cancel_btn.clicked.connect(chrome_back)

    chrome = page_chrome("Contacts", root, chrome_back, scroll=False)
    chrome.on_hardware_back = on_hardware_back  # type: ignore[attr-defined]
    chrome.refresh_contacts = show_list  # type: ignore[attr-defined]
    show_list()
    return chrome


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
    """Full-frame live CSI preview. Confirm = take photo. Gallery is its own app."""
    from PyQt5.QtCore import QTimer, pyqtSignal, QObject
    from PyQt5.QtGui import QImage, QPixmap

    class _FrameBridge(QObject):
        frame = pyqtSignal(object, int, int)  # bytes, w, h
        err = pyqtSignal(str)

    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setSpacing(2)
    lay.setContentsMargins(0, 0, 0, 0)

    tip = QLabel("Confirm = snap · Gallery is separate")
    tip.setStyleSheet("color:#9ab;font-size:9px;")
    tip.setWordWrap(True)
    tip.setAlignment(Qt.AlignCenter)
    preview = QLabel("Starting camera…")
    preview.setAlignment(Qt.AlignCenter)
    preview.setMinimumHeight(180)
    preview.setStyleSheet(
        "background:#0a0a0a; border: none; color:#888; font-size:11px;"
    )
    status = QLabel("")
    status.setStyleSheet("color:#cde;font-size:9px;")
    status.setAlignment(Qt.AlignCenter)
    status.setWordWrap(True)

    lay.addWidget(tip)
    lay.addWidget(preview, 1)
    lay.addWidget(status)

    bridge = _FrameBridge(body)
    live = pi_camera.LivePreview(width=320, height=240, fps=8.0)
    last_path: list[Optional[Path]] = [None]
    _started = [False]
    _busy = [False]

    def on_frame_bytes(rgb: bytes, w: int, h: int) -> None:
        bridge.frame.emit(rgb, w, h)

    def on_frame_ui(rgb, w: int, h: int) -> None:
        if _busy[0]:
            return
        try:
            img = QImage(rgb, w, h, w * 3, QImage.Format_RGB888)
            if img.isNull():
                return
            pix = QPixmap.fromImage(img.copy())
            preview.setPixmap(
                pix.scaled(
                    max(preview.width(), 200),
                    max(preview.height(), 160),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
        except Exception:
            pass

    def on_err(msg: str) -> None:
        status.setText(msg)
        if not preview.pixmap() or preview.pixmap().isNull():
            preview.setText(msg[:80])

    bridge.frame.connect(on_frame_ui)
    bridge.err.connect(on_err)

    def start_live() -> None:
        if _started[0]:
            return
        status.setText("Starting…")
        ok = live.start(
            on_frame_bytes,
            on_error=lambda m: bridge.err.emit(m),
        )
        _started[0] = ok
        if ok:
            status.setText("Live · Confirm to snap")
        else:
            status.setText("No preview — Confirm still snaps if camera works")
            preview.setText("Preview unavailable\nConfirm = capture")

    def stop_live() -> None:
        live.stop()
        _started[0] = False

    def do_snap() -> bool:
        """Take photo (Confirm). Returns True so digi_activate consumes the key."""
        if _busy[0]:
            status.setText("Already capturing…")
            return True
        _busy[0] = True
        status.setText("Capturing…")

        def work() -> None:
            try:
                if live.running:
                    path = live.capture_still()
                else:
                    path = pi_camera.capture_rear()
                last_path[0] = path
                pix = QPixmap(str(path))
                if not pix.isNull():
                    preview.setPixmap(
                        pix.scaled(
                            max(preview.width(), 200),
                            max(preview.height(), 160),
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation,
                        )
                    )
                status.setText(f"Saved {path.name}")
                on_status(f"Photo {path.name}")
                # Resume live after brief freeze-frame
                QTimer.singleShot(700, lambda: status.setText("Live · Confirm to snap"))
            except Exception as e:
                status.setText(str(e)[:120])
                on_status(f"Camera: {e}")
            finally:
                _busy[0] = False

        QTimer.singleShot(10, work)
        return True

    # Start/stop preview when page is shown/hidden
    def showEvent(e) -> None:  # noqa: N802
        QWidget.showEvent(body, e)
        QTimer.singleShot(100, start_live)

    def hideEvent(e) -> None:  # noqa: N802
        stop_live()
        QWidget.hideEvent(body, e)

    body.showEvent = showEvent  # type: ignore
    body.hideEvent = hideEvent  # type: ignore
    body.destroyed.connect(lambda *_: stop_live())

    chrome = page_chrome("Camera", body, on_back, scroll=False)
    # Confirm always snaps — do not activate chrome Back ←
    chrome.digi_activate = do_snap  # type: ignore[attr-defined]
    # Optional: de-emphasize Back from digi focus (hardware Back still works)
    for b in chrome.findChildren(QPushButton):
        if (b.text() or "").strip() in ("←", "← ", "<"):
            b.setFocusPolicy(Qt.NoFocus)
    return chrome


def make_gallery_page(on_back: Callable[[], None], on_status) -> QWidget:
    """Thumbnail list → full-screen viewer; left/right for prev/next photo."""
    from PyQt5.QtCore import QSize
    from PyQt5.QtGui import QIcon, QPixmap
    from PyQt5.QtWidgets import QListWidgetItem, QSizePolicy, QStackedWidget

    root = QWidget()
    root_lay = QVBoxLayout(root)
    root_lay.setContentsMargins(0, 0, 0, 0)
    root_lay.setSpacing(0)
    stack = QStackedWidget()
    root_lay.addWidget(stack, 1)

    # --- list page ---
    list_page = QWidget()
    ll = QVBoxLayout(list_page)
    ll.setContentsMargins(2, 2, 2, 2)
    ll.setSpacing(4)
    tip = QLabel("Confirm opens photo · refresh reloads")
    tip.setStyleSheet("color:#9ab;font-size:10px;")
    tip.setWordWrap(True)
    lst = QListWidget()
    lst.setIconSize(QSize(72, 54))
    lst.setSpacing(2)
    lst.setUniformItemSizes(True)
    lst.setResizeMode(QListWidget.Adjust)
    lst.setWordWrap(True)
    refresh = QPushButton("Refresh")
    refresh.setMinimumHeight(28)
    empty = QLabel("No photos yet.\nCamera → Snap")
    empty.setAlignment(Qt.AlignCenter)
    empty.setStyleSheet("color:#888;")
    empty.hide()
    ll.addWidget(tip)
    ll.addWidget(lst, 1)
    ll.addWidget(empty)
    ll.addWidget(refresh)

    # --- viewer page ---
    view_page = QWidget()
    vl = QVBoxLayout(view_page)
    vl.setContentsMargins(0, 0, 0, 0)
    vl.setSpacing(2)
    img_lab = QLabel("…")
    img_lab.setAlignment(Qt.AlignCenter)
    img_lab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    img_lab.setStyleSheet("background:#000; color:#888;")
    img_lab.setMinimumHeight(160)
    meta = QLabel("")
    meta.setAlignment(Qt.AlignCenter)
    meta.setStyleSheet("color:#e8eef5;font-size:10px;font-weight:700;")
    meta.setWordWrap(True)
    hint = QLabel("← → prev/next · Back = list")
    hint.setAlignment(Qt.AlignCenter)
    hint.setStyleSheet("color:#9ab;font-size:9px;")
    row = QHBoxLayout()
    prev_btn = QPushButton("◀ Prev")
    next_btn = QPushButton("Next ▶")
    prev_btn.setMinimumHeight(30)
    next_btn.setMinimumHeight(30)
    row.addWidget(prev_btn)
    row.addWidget(next_btn)
    close_btn = QPushButton("Back to list")
    close_btn.setMinimumHeight(28)
    vl.addWidget(img_lab, 1)
    vl.addWidget(meta)
    vl.addWidget(hint)
    vl.addLayout(row)
    vl.addWidget(close_btn)

    stack.addWidget(list_page)
    stack.addWidget(view_page)

    photos: list[Path] = []
    index = [0]

    def load_list() -> None:
        photos.clear()
        photos.extend(pi_camera.list_photos(limit=200))
        lst.clear()
        if not photos:
            empty.show()
            lst.hide()
            on_status("Gallery empty")
            return
        empty.hide()
        lst.show()
        for p in photos:
            item = QListWidgetItem(p.name)
            pix = QPixmap(str(p))
            if not pix.isNull():
                item.setIcon(
                    QIcon(
                        pix.scaled(
                            72, 54, Qt.KeepAspectRatio, Qt.SmoothTransformation
                        )
                    )
                )
            item.setData(Qt.UserRole, str(p))
            item.setSizeHint(QSize(200, 58))
            lst.addItem(item)
        if lst.count() > 0 and lst.currentRow() < 0:
            lst.setCurrentRow(0)
        on_status(f"{len(photos)} photos")

    def show_list_mode() -> None:
        stack.setCurrentWidget(list_page)
        root.setProperty("digiSeekActive", False)
        # prefer list for digi focus
        try:
            from esp_handset import digi_nav

            digi_nav.ensure_page_focus(root)
        except Exception:
            lst.setFocus()

    def paint_viewer() -> None:
        if not photos:
            return
        i = max(0, min(index[0], len(photos) - 1))
        index[0] = i
        path = photos[i]
        pix = QPixmap(str(path))
        if pix.isNull():
            img_lab.setText("Cannot load")
            meta.setText(path.name)
            return
        # fill available label area
        w = max(img_lab.width(), 200)
        h = max(img_lab.height(), 140)
        img_lab.setPixmap(
            pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        meta.setText(f"{i + 1} / {len(photos)}\n{path.name}")
        on_status(f"Photo {i + 1}/{len(photos)}")
        prev_btn.setEnabled(len(photos) > 1)
        next_btn.setEnabled(len(photos) > 1)

    def open_index(i: int) -> None:
        if not photos:
            return
        index[0] = i % len(photos)
        stack.setCurrentWidget(view_page)
        root.setProperty("digiSeekActive", True)
        paint_viewer()
        # digi: land on Next for confirm cycling; L/R still seek
        next_btn.setFocus()

    def open_selected() -> None:
        row = lst.currentRow()
        if row < 0 and photos:
            row = 0
        if 0 <= row < len(photos):
            open_index(row)

    def digi_seek(delta: int) -> bool:
        """Left/right in viewer. Returns True if handled."""
        if stack.currentWidget() is not view_page or not photos:
            return False
        index[0] = (index[0] + delta) % len(photos)
        paint_viewer()
        return True

    root.digi_seek = digi_seek  # type: ignore[attr-defined]
    root.digi_seek_active = lambda: stack.currentWidget() is view_page  # type: ignore

    def handle_back() -> None:
        if stack.currentWidget() is view_page:
            show_list_mode()
        else:
            on_back()

    prev_btn.clicked.connect(lambda: digi_seek(-1))
    next_btn.clicked.connect(lambda: digi_seek(1))
    close_btn.clicked.connect(show_list_mode)
    refresh.clicked.connect(load_list)
    lst.itemActivated.connect(lambda _i: open_selected())
    lst.itemClicked.connect(lambda _i: open_selected())

    # resize viewer image when showing
    def on_view_resize(e) -> None:
        QWidget.resizeEvent(view_page, e)
        if stack.currentWidget() is view_page:
            paint_viewer()

    view_page.resizeEvent = on_view_resize  # type: ignore

    load_list()

    # page_chrome with custom back
    chrome = page_chrome("Gallery", root, handle_back, scroll=False)
    # expose seek on chrome for shell key routing
    chrome.digi_seek = digi_seek  # type: ignore[attr-defined]
    chrome.digi_seek_active = (  # type: ignore[attr-defined]
        lambda: stack.currentWidget() is view_page
    )
    # re-load thumbs when page is shown again
    _show = chrome.showEvent

    def show_ev(e) -> None:  # noqa: N802
        if _show:
            _show(e)
        else:
            QWidget.showEvent(chrome, e)
        if stack.currentWidget() is list_page:
            load_list()

    chrome.showEvent = show_ev  # type: ignore
    return chrome


def make_lora_page(bridge, on_back, on_status) -> QWidget:
    """LoRa mesh inbox + thread — same conversation pattern as SMS."""
    from esp_handset import digi_nav

    root = QWidget()
    stack = QStackedWidget(root)
    outer = QVBoxLayout(root)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(stack)

    inbox = QWidget()
    in_lay = QVBoxLayout(inbox)
    in_lay.setContentsMargins(2, 2, 2, 2)
    in_lay.setSpacing(4)

    conv_list = QListWidget()
    conv_list.setSpacing(2)
    conv_list.setStyleSheet(
        "QListWidget { background: transparent; border: none; outline: none; }"
        "QListWidget::item { background: #152030; border-radius: 6px;"
        "  margin: 1px 0; padding: 0; }"
        "QListWidget::item:selected { background: #243448;"
        "  border: 2px solid #FFE600; }"
    )
    in_lay.addWidget(conv_list, 1)

    row_btns = QHBoxLayout()
    new_btn = QPushButton("＋ New")
    new_btn.setMinimumHeight(30)
    new_btn.setStyleSheet("font-weight:700;")
    sos_btn = QPushButton("SOS")
    sos_btn.setMinimumHeight(30)
    sos_btn.setStyleSheet("font-weight:800; background:#8a2020;")
    row_btns.addWidget(new_btn, 1)
    row_btns.addWidget(sos_btn)
    in_lay.addLayout(row_btns)

    new_form = QWidget()
    new_form.setVisible(False)
    nf_lay = QVBoxLayout(new_form)
    nf_lay.setContentsMargins(0, 0, 0, 0)
    nf_lay.setSpacing(3)
    new_to = QLineEdit()
    new_to.setPlaceholderText("LoRa device ID")
    nf_row = QHBoxLayout()
    new_open = QPushButton("Open")
    new_open.setStyleSheet("font-weight:700;")
    new_cancel = QPushButton("Cancel")
    nf_row.addWidget(new_open, 1)
    nf_row.addWidget(new_cancel, 1)
    nf_lay.addWidget(new_to)
    nf_lay.addLayout(nf_row)
    tip = QLabel("Broadcast = 0 · match Contacts LoRa ID")
    tip.setStyleSheet("font-size:9px; color:#678;")
    tip.setWordWrap(True)
    nf_lay.addWidget(tip)
    in_lay.addWidget(new_form)
    stack.addWidget(inbox)

    thread = QWidget()
    th_lay = QVBoxLayout(thread)
    th_lay.setContentsMargins(2, 2, 2, 2)
    th_lay.setSpacing(3)
    thread_title = QLabel("LoRa")
    thread_title.setStyleSheet("font-size:12px; font-weight:700;")
    thread_title.setWordWrap(True)
    th_lay.addWidget(thread_title)
    msg_list = QListWidget()
    msg_list.setStyleSheet(
        "QListWidget { background: transparent; border: none; outline: none; }"
        "QListWidget::item { background: transparent; margin: 2px 0; padding: 0; }"
        "QListWidget::item:selected { background: rgba(255,230,0,0.12);"
        "  border: 1px solid #FFE600; border-radius: 4px; }"
    )
    th_lay.addWidget(msg_list, 1)
    compose_row = QHBoxLayout()
    compose_row.setSpacing(3)
    compose = QLineEdit()
    compose.setPlaceholderText("Type a message…")
    compose.setMinimumHeight(30)
    send_btn = QPushButton("Send")
    send_btn.setMinimumHeight(30)
    send_btn.setFixedWidth(52)
    send_btn.setStyleSheet("font-weight:800;")
    compose_row.addWidget(compose, 1)
    compose_row.addWidget(send_btn)
    th_lay.addLayout(compose_row)
    stack.addWidget(thread)

    state = {"peer": ""}

    def show_inbox() -> None:
        state["peer"] = ""
        new_form.setVisible(False)
        stack.setCurrentWidget(inbox)
        refresh_inbox()
        digi_nav.ensure_page_focus(chrome)

    def refresh_inbox() -> None:
        threads = _load_lora_threads()
        items = list(threads.items())

        def sort_key(pair):
            peer, msgs = pair
            last_at = str(msgs[-1].get("at") or "") if msgs else ""
            return (last_at, peer)

        items.sort(key=sort_key, reverse=True)
        conv_list.clear()
        if not items:
            empty = QListWidgetItem("No LoRa chats yet.\n＋ New or wait for RX.")
            empty.setFlags(Qt.NoItemFlags)
            conv_list.addItem(empty)
            return
        for peer, msgs in items:
            name, initial, photo = _contact_display(lora=peer, fallback=peer)
            if peer in ("0", "broadcast"):
                name, initial, photo = "Broadcast", "B", None
            last = msgs[-1] if msgs else {"text": "", "dir": "in"}
            preview = _elide_one_line(_msg_preview(last))
            unread = any(
                m.get("dir") == "in" and not m.get("read", True) for m in msgs
            )
            item = QListWidgetItem()
            item.setData(Qt.UserRole, peer)
            item.setSizeHint(QSize(200, 48))
            conv_list.addItem(item)
            conv_list.setItemWidget(
                item,
                _chat_conv_row(
                    name, preview, initial=initial, photo=photo, unread=unread
                ),
            )

    def mark_read(peer: str) -> None:
        threads = _load_lora_threads()
        msgs = threads.get(peer)
        if not msgs:
            return
        changed = False
        for m in msgs:
            if m.get("dir") == "in" and not m.get("read", True):
                m["read"] = True
                changed = True
        if changed:
            threads[peer] = msgs
            _save_lora_threads(threads)

    def open_thread(peer: str) -> None:
        peer = str(peer or "").strip()
        if not peer:
            return
        if peer == "0":
            peer = "broadcast"
        state["peer"] = peer
        name, _, _ = _contact_display(lora=peer, fallback=peer)
        if peer == "broadcast":
            name = "Broadcast"
        thread_title.setText(f"{name}\nID {peer}" if name != peer else f"LoRa {peer}")
        mark_read(peer)
        refresh_thread()
        stack.setCurrentWidget(thread)
        compose.clear()
        digi_nav.ensure_page_focus(chrome)
        compose.setFocus(Qt.OtherFocusReason)

    def refresh_thread() -> None:
        peer = state["peer"]
        msg_list.clear()
        if not peer:
            return
        msgs = _load_lora_threads().get(peer, [])
        if not msgs:
            item = QListWidgetItem("No messages yet.")
            item.setFlags(Qt.NoItemFlags)
            msg_list.addItem(item)
            return
        for m in msgs:
            item = QListWidgetItem()
            bubble = _chat_bubble(m)
            bubble.adjustSize()
            item.setSizeHint(QSize(200, max(36, bubble.sizeHint().height() + 4)))
            msg_list.addItem(item)
            msg_list.setItemWidget(item, bubble)
        msg_list.scrollToBottom()

    def open_selected() -> None:
        item = conv_list.currentItem()
        if item is None:
            return
        peer = item.data(Qt.UserRole)
        if peer:
            open_thread(str(peer))

    def start_new() -> None:
        new_form.setVisible(True)
        new_to.setFocus(Qt.OtherFocusReason)

    def cancel_new() -> None:
        new_form.setVisible(False)
        new_to.clear()
        digi_nav.ensure_page_focus(chrome)

    def open_new() -> None:
        peer = new_to.text().strip() or "broadcast"
        if peer == "0":
            peer = "broadcast"
        new_form.setVisible(False)
        threads = _load_lora_threads()
        threads.setdefault(peer, [])
        _save_lora_threads(threads)
        open_thread(peer)

    def _target_id(peer: str) -> int:
        if peer in ("broadcast", "mesh", ""):
            return 0
        try:
            return int(peer)
        except ValueError:
            return 0

    def do_send() -> None:
        peer = state["peer"]
        text = compose.text().strip().replace("\n", " ")
        if not peer or not text:
            return
        if not bridge:
            QMessageBox.warning(root, "LoRa", "ESP not connected")
            return
        try:
            bridge.lora_send(text, target=_target_id(peer))
        except Exception as e:
            QMessageBox.warning(root, "LoRa", str(e))
            return
        threads = _load_lora_threads()
        threads.setdefault(peer, []).append(
            {
                "dir": "out",
                "text": text,
                "at": datetime.now().isoformat(),
                "read": True,
            }
        )
        _save_lora_threads(threads)
        compose.clear()
        refresh_thread()
        on_status(f"LoRa → {peer}")

    def do_sos() -> None:
        if not bridge:
            QMessageBox.warning(root, "LoRa", "ESP not connected")
            return
        try:
            bridge.lora_sos()
        except Exception as e:
            QMessageBox.warning(root, "LoRa", str(e))
            return
        threads = _load_lora_threads()
        threads.setdefault("broadcast", []).append(
            {
                "dir": "out",
                "text": "SOS NEED HELP",
                "at": datetime.now().isoformat(),
                "read": True,
            }
        )
        _save_lora_threads(threads)
        on_status("LoRa SOS sent")
        refresh_inbox()
        if stack.currentWidget() is thread and state["peer"] == "broadcast":
            refresh_thread()

    def ingest_rx(line: str) -> None:
        """Called from handset_app when LORA RX arrives."""
        parsed = _parse_lora_rx_line(line)
        if not parsed:
            return
        peer, text = parsed
        if not text:
            return
        threads = _load_lora_threads()
        threads.setdefault(peer, []).append(
            {
                "dir": "in",
                "text": text,
                "at": datetime.now().isoformat(),
                "read": False,
            }
        )
        _save_lora_threads(threads)
        if stack.currentWidget() is thread and state["peer"] == peer:
            mark_read(peer)
            refresh_thread()
        else:
            refresh_inbox()

    def chrome_back() -> None:
        if stack.currentWidget() is thread:
            show_inbox()
        elif new_form.isVisible():
            cancel_new()
        else:
            on_back()

    def on_hardware_back() -> bool:
        if stack.currentWidget() is thread:
            show_inbox()
            return True
        if new_form.isVisible():
            cancel_new()
            return True
        return False

    def refresh_lora() -> None:
        if stack.currentWidget() is thread and state["peer"]:
            mark_read(state["peer"])
            refresh_thread()
        refresh_inbox()

    conv_list.itemActivated.connect(lambda _i: open_selected())
    conv_list.itemClicked.connect(lambda _i: open_selected())
    new_btn.clicked.connect(start_new)
    new_open.clicked.connect(open_new)
    new_cancel.clicked.connect(cancel_new)
    send_btn.clicked.connect(do_send)
    compose.returnPressed.connect(do_send)
    sos_btn.clicked.connect(do_sos)

    chrome = page_chrome("LoRa", root, chrome_back, scroll=False)
    chrome.refresh_lora = refresh_lora  # type: ignore[attr-defined]
    chrome.on_hardware_back = on_hardware_back  # type: ignore[attr-defined]
    chrome.open_lora_thread = open_thread  # type: ignore[attr-defined]
    chrome.ingest_lora_rx = ingest_rx  # type: ignore[attr-defined]
    # Legacy no-op so old log.append callers don't crash
    chrome.lora_log = None  # type: ignore[attr-defined]

    refresh_inbox()
    stack.setCurrentWidget(inbox)
    return chrome


def make_gps_page(modem, on_back, on_status, get_modem=None) -> QWidget:
    """SIM7600 GNSS — status on-page (no blank QMessageBox on 240×320)."""
    from PyQt5.QtCore import QTimer

    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setSpacing(4)
    tip = QLabel(
        "GNSS antenna on SIM7600 IPEX.\n"
        "Outdoors · cold start 30–120s."
    )
    tip.setWordWrap(True)
    tip.setStyleSheet("color:#9ab;font-size:10px;")
    summary = QLabel("GPS off")
    summary.setWordWrap(True)
    summary.setAlignment(Qt.AlignCenter)
    summary.setStyleSheet(
        "font-size:14px; font-weight:700; padding:8px;"
        "background:#1a2230; color:#cde;"
    )
    detail = QLabel("")
    detail.setWordWrap(True)
    detail.setAlignment(Qt.AlignCenter)
    detail.setStyleSheet("font-size:11px; color:#9ab;")
    on_btn = QPushButton("Start GPS")
    on_btn.setMinimumHeight(32)
    on_btn.setStyleSheet("font-weight:700;")
    poll_btn = QPushButton("Refresh")
    poll_btn.setMinimumHeight(28)
    off_btn = QPushButton("Stop GPS")
    off_btn.setMinimumHeight(28)
    lay.addWidget(tip)
    lay.addWidget(summary)
    lay.addWidget(detail)
    lay.addWidget(on_btn)
    lay.addWidget(poll_btn)
    lay.addWidget(off_btn)
    lay.addStretch(1)

    state = {"on": False}
    timer = QTimer(body)
    timer.setInterval(4000)

    def _m():
        if get_modem:
            return get_modem()
        return modem

    def _show(fix: dict, err: str = "") -> None:
        if err:
            summary.setText("ERROR")
            summary.setStyleSheet(
                "font-size:14px; font-weight:700; padding:8px;"
                "background:#4a1010; color:#ff8a8a;"
            )
            detail.setText(err)
            on_status(err.split("\n")[0][:60])
            return
        if fix.get("ok"):
            summary.setText("FIX\n" + str(fix.get("summary") or ""))
            summary.setStyleSheet(
                "font-size:13px; font-weight:700; padding:8px;"
                "background:#0d3d1f; color:#7dffa0;"
            )
            detail.setText(str(fix.get("detail") or ""))
            on_status(str(fix.get("summary") or "")[:60])
        elif fix.get("searching"):
            summary.setText("SEARCHING…")
            summary.setStyleSheet(
                "font-size:14px; font-weight:700; padding:8px;"
                "background:#3a2a10; color:#ffcc66;"
            )
            detail.setText(str(fix.get("detail") or "Wait outdoors"))
            on_status("GPS searching")
        else:
            summary.setText(str(fix.get("summary") or "No fix"))
            summary.setStyleSheet(
                "font-size:14px; font-weight:700; padding:8px;"
                "background:#1a2230; color:#cde;"
            )
            detail.setText(str(fix.get("detail") or ""))

    def _poll() -> None:
        m = _m()
        if not m:
            _show({}, "SIM7600 not connected.\nSettings→Network→Reconnect")
            return
        try:
            fix = m.gps_fix()
            _show(fix)
        except Exception as e:
            msg = str(e).strip() or repr(e) or "Unknown modem error"
            _show({}, msg)

    def do_start() -> None:
        m = _m()
        if not m:
            _show({}, "SIM7600 not connected.\nSettings→Network→Reconnect")
            return
        summary.setText("STARTING…")
        summary.setStyleSheet(
            "font-size:14px; font-weight:700; padding:8px;"
            "background:#1a3040; color:#9cf;"
        )
        detail.setText("Sending AT+CGPS=1…")
        try:
            m.gps_on()
            state["on"] = True
            if not timer.isActive():
                timer.start()
            detail.setText("GNSS on — polling for fix…")
            _poll()
        except Exception as e:
            state["on"] = False
            timer.stop()
            msg = str(e).strip() or repr(e) or "Start failed"
            _show({}, msg)

    def do_stop() -> None:
        timer.stop()
        state["on"] = False
        m = _m()
        if m:
            try:
                m.gps_off()
            except Exception:
                pass
        summary.setText("GPS off")
        summary.setStyleSheet(
            "font-size:14px; font-weight:700; padding:8px;"
            "background:#1a2230; color:#cde;"
        )
        detail.setText("Stopped.")
        on_status("GPS off")

    def on_tick() -> None:
        if state["on"]:
            _poll()

    on_btn.clicked.connect(do_start)
    poll_btn.clicked.connect(_poll)
    off_btn.clicked.connect(do_stop)
    timer.timeout.connect(on_tick)
    m0 = _m()
    if not m0:
        _show({}, "SIM7600 not connected.\nSettings→Network→Reconnect")
    else:
        try:
            detail.setText(f"Modem AT: {m0.port}\nPress Start GPS")
        except Exception:
            pass
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
        ("set_mouse", "Mouse speed"),
        ("set_debug", "Debug · Audio"),
        ("set_appearance", "Appearance"),
        ("set_network", "Network / modem"),
        ("set_accounts", "Accounts (SIP)"),
        ("set_sounds", "Sounds"),
        ("set_security", "Security (PIN)"),
        ("set_power", "Power · Off / Restart"),
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


def make_power_page(on_back: Callable[[], None]) -> QWidget:
    """Power off / restart. Double-press confirm (no Yes/No dialog)."""
    from PyQt5.QtCore import QTimer

    body = QWidget()
    lay = QVBoxLayout(body)
    tip = QLabel(
        "Shutdown or restart the Pi.\n"
        "Press the SAME button twice within 4s to confirm."
    )
    tip.setWordWrap(True)
    tip.setStyleSheet("color:#9ab;font-size:10px;")
    status = QLabel("Ready.")
    status.setWordWrap(True)
    off_btn = QPushButton("Power off (x2)")
    off_btn.setMinimumHeight(36)
    off_btn.setStyleSheet("font-weight:700;")
    reboot_btn = QPushButton("Restart (x2)")
    reboot_btn.setMinimumHeight(36)
    lay.addWidget(tip)
    lay.addWidget(status)
    lay.addWidget(off_btn)
    lay.addWidget(reboot_btn)
    lay.addStretch(1)

    pending = {"action": None, "ts": 0.0}

    def _power_bin(arg: str) -> list:
        for p in (
            "/usr/local/bin/digivice-power",
            "/opt/esp-handset/session/power.sh",
        ):
            if os.path.isfile(p):
                return ["sudo", "-n", p, arg]
        here = Path(__file__).resolve().parents[1] / "session" / "power.sh"
        if here.is_file():
            return ["sudo", "-n", "bash", str(here), arg]
        # Fallback to common paths (need NOPASSWD for these if used)
        if arg == "poweroff":
            return ["sudo", "-n", "systemctl", "poweroff"]
        return ["sudo", "-n", "systemctl", "reboot"]

    def needs_confirm(action: str) -> bool:
        import time as _t

        now = _t.time()
        if pending["action"] == action and now - float(pending["ts"]) < 4.0:
            pending["action"] = None
            return False
        pending["action"] = action
        pending["ts"] = now
        label = "Power off" if action == "poweroff" else "Restart"
        status.setText(f"Press {label} again to confirm (4s)")
        return True

    def run_power(arg: str, label: str) -> None:
        if needs_confirm(arg):
            return
        cmd = _power_bin(arg)
        status.setText(f"{label}…")
        off_btn.setEnabled(False)
        reboot_btn.setEnabled(False)
        try:
            # Detach so UI can show status before system dies
            env = os.environ.copy()
            env.setdefault("PATH", "/usr/local/bin:/usr/sbin:/sbin:/usr/bin:/bin")
            subprocess.Popen(
                cmd,
                start_new_session=True,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            status.setText(f"{label} commanded.\nIf nothing happens, seed:\n  sudo digivice-full-update")
        except Exception as e:
            status.setText(f"Failed: {e}")
            off_btn.setEnabled(True)
            reboot_btn.setEnabled(True)
            return
        # Soft blank after a moment (process may still be running)
        QTimer.singleShot(2500, lambda: status.setText(f"Waiting for {label.lower()}…"))

    off_btn.clicked.connect(lambda: run_power("poweroff", "Power off"))
    reboot_btn.clicked.connect(lambda: run_power("reboot", "Restart"))
    return page_chrome("Power", body, on_back)


def make_update_page(on_back: Callable[[], None]) -> QWidget:
    """Stage update to /opt/esp-handset.staging, then exit → apply → relaunch.

    Never overwrites live /opt while Digivice is running. Never KILLs itself.
    """
    from PyQt5.QtCore import QProcess, QProcessEnvironment, QTimer

    body = QWidget()
    lay = QVBoxLayout(body)
    tip = QLabel(
        "Pull → stage (live Digivice untouched)\n"
        "→ quit → swap → relaunch.\n"
        "Stay on Wi‑Fi; can take 1–3 min."
    )
    tip.setWordWrap(True)
    tip.setStyleSheet("color:#9ab;font-size:10px;")
    status = QLabel("Ready.")
    status.setWordWrap(True)
    meta = QLabel("")
    meta.setWordWrap(True)
    meta.setStyleSheet("color:#678;font-size:9px;")
    log = QTextEdit()
    log.setReadOnly(True)
    log.setMinimumHeight(100)
    log.setStyleSheet("font-size:9px; font-family: monospace;")
    update_btn = QPushButton("Update Digivice")
    update_btn.setStyleSheet("font-weight:700; min-height:36px;")
    lay.addWidget(tip)
    lay.addWidget(status)
    lay.addWidget(meta)
    lay.addWidget(log, 1)
    lay.addWidget(update_btn)

    proc = QProcess(body)
    proc.setProcessChannelMode(QProcess.MergedChannels)
    env = QProcessEnvironment.systemEnvironment()
    env.insert("DISPLAY", os.environ.get("DISPLAY", ":0"))
    if os.environ.get("XAUTHORITY"):
        env.insert("XAUTHORITY", os.environ["XAUTHORITY"])
    env.insert(
        "PATH",
        "/usr/local/bin:/usr/bin:/bin:" + os.environ.get("PATH", ""),
    )
    env.insert("PYTHONUNBUFFERED", "1")
    env.insert("ESP_HANDSET_SOFT_SERVICES", "1")
    env.insert("ESP_HANDSET_STAGE", "1")
    proc.setProcessEnvironment(env)

    watchdog = QTimer(body)
    watchdog.setSingleShot(True)
    applying = {"on": False}

    def _read_stamp() -> str:
        for p in (
            DATA / "last_update",
            Path("/etc/esp-handset/last_update"),
            DATA / "last_gui_update",
        ):
            try:
                if p.is_file():
                    return p.read_text(encoding="utf-8").strip()[:80]
            except OSError:
                continue
        return "(never)"

    def _installed_hint() -> str:
        for p in (
            Path("/opt/esp-handset/handset_app.py"),
            Path("/opt/esp-handset/esp_handset/__init__.py"),
        ):
            if p.is_file():
                try:
                    import time as _t

                    ts = _t.strftime(
                        "%Y-%m-%d %H:%M", _t.localtime(p.stat().st_mtime)
                    )
                    return f"Installed files: {ts}"
                except OSError:
                    return "Installed: /opt/esp-handset"
        return "Installed: missing — run sudo digivice-full-update once"

    def refresh_meta() -> None:
        meta.setText(f"Last: {_read_stamp()}\n{_installed_hint()}")

    refresh_meta()

    def append_out() -> None:
        data = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        if not data:
            return
        log.moveCursor(QTextCursor.End)
        log.insertPlainText(data)
        log.moveCursor(QTextCursor.End)

    def restart_digivice() -> None:
        """Spawn apply (waits for us), then quit cleanly — no pkill of self."""
        if applying["on"]:
            return
        applying["on"] = True
        import shlex

        status.setText("Quitting → apply staged update…")
        log.append("\n--- scheduling apply, then clean quit ---\n")
        DATA.mkdir(parents=True, exist_ok=True)
        log_path = str(DATA / "apply-update.log")
        apply = "/usr/local/bin/digivice-apply-update"
        if not os.path.isfile(apply):
            for p in (
                "/opt/esp-handset/session/apply-update.sh",
                str(Path.home() / "esp-phone/pi_handset/session/apply-update.sh"),
            ):
                if os.path.isfile(p):
                    apply = p
                    break

        qlog = shlex.quote(log_path)
        qapply = shlex.quote(apply)
        # Start apply FIRST so it is waiting; then we quit. No KILL race.
        script = (
            f"exec >>{qlog} 2>&1; "
            'echo "=== apply wait $(date -Iseconds) ==="; '
            f"sudo -n {qapply} 2>/dev/null || sudo -n bash {qapply} 2>/dev/null "
            f"|| bash {qapply}; "
        )
        env2 = os.environ.copy()
        env2.setdefault("DISPLAY", ":0")
        try:
            subprocess.Popen(
                ["bash", "-c", script],
                start_new_session=True,
                env=env2,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except Exception as e:
            status.setText(f"Apply spawn failed: {e}")
            applying["on"] = False
            update_btn.setEnabled(True)
            return

        def _quit() -> None:
            try:
                from PyQt5.QtWidgets import QApplication

                app = QApplication.instance()
                if app is not None:
                    app.quit()
            except Exception:
                pass

        # Give apply time to start waiting before we tear down Qt/SPI
        QTimer.singleShot(800, _quit)

    def on_timeout() -> None:
        if proc.state() == QProcess.NotRunning:
            return
        log.append("\n--- TIMEOUT (10 min) — stopping updater ---\n")
        proc.terminate()
        update_btn.setEnabled(True)
        status.setText("Timed out — Digivice still running")

    def on_finished(code: int, _st) -> None:
        watchdog.stop()
        append_out()
        refresh_meta()
        if code == 0:
            status.setText("Staged OK — applying…")
            log.append("\n--- OK — apply after quit ---\n")
            QTimer.singleShot(300, restart_digivice)
        else:
            update_btn.setEnabled(True)
            status.setText(f"Failed (exit {code}) — UI left running")
            log.append(
                "\n--- FAILED (safe: no restart) ---\n"
                "Common fixes:\n"
                "  • Wi‑Fi / GitHub down → try later\n"
                "  • sudo denied → sudo digivice-full-update once\n"
                "  • Or from SSH: cd ~/esp-phone && git pull && sudo digivice-update\n"
            )

    def on_error(err) -> None:
        watchdog.stop()
        update_btn.setEnabled(True)
        status.setText(f"Start error: {err}")
        log.append(f"\nQProcess error: {err}\n")

    proc.readyReadStandardOutput.connect(append_out)
    proc.finished.connect(on_finished)
    watchdog.timeout.connect(on_timeout)
    try:
        proc.errorOccurred.connect(on_error)
    except Exception:
        pass

    def _gui_update_bin() -> list:
        # Only sudoers-allowlisted paths (not arbitrary repo bash — that fails sudo -n)
        for p in (
            "/usr/local/bin/digivice-gui-update",
            "/opt/esp-handset/session/gui-update.sh",
        ):
            if os.path.isfile(p):
                if p.endswith(".sh"):
                    return ["sudo", "-n", "bash", p]
                return ["sudo", "-n", p]
        return ["sudo", "-n", "/usr/local/bin/digivice-gui-update"]

    def _preflight() -> Optional[str]:
        try:
            r = subprocess.run(
                ["sudo", "-n", "true"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if r.returncode != 0:
                return (
                    "Passwordless sudo missing.\n"
                    "Seed once over HDMI/SSH:\n"
                    "  sudo digivice-full-update"
                )
        except Exception as e:
            return f"sudo check failed: {e}"
        if not os.path.isfile("/usr/local/bin/digivice-gui-update") and not os.path.isfile(
            "/opt/esp-handset/session/gui-update.sh"
        ):
            return (
                "digivice-gui-update missing.\n"
                "  sudo digivice-full-update"
            )
        return None

    def do_update() -> None:
        if proc.state() != QProcess.NotRunning or applying["on"]:
            status.setText("Already running…")
            return
        err = _preflight()
        if err:
            status.setText("Cannot update")
            log.clear()
            log.append(err + "\n")
            update_btn.setEnabled(True)
            return
        log.clear()
        update_btn.setEnabled(False)
        bin_cmd = _gui_update_bin()
        status.setText("Staging (live Digivice untouched)…")
        log.append("$ " + " ".join(bin_cmd) + "\n\n")
        prog, *argv = bin_cmd
        proc.start(prog, argv)
        if not proc.waitForStarted(5000):
            status.setText("Could not start updater")
            update_btn.setEnabled(True)
            log.append(
                "Missing digivice-gui-update.\n"
                "  sudo digivice-full-update\n"
            )
            return
        watchdog.start(10 * 60 * 1000)

    update_btn.clicked.connect(do_update)
    return page_chrome("Update", body, on_back)


def make_mouse_page(on_back: Callable[[], None]) -> QWidget:
    """Desktop d-pad mouse speed (buttons daemon reads ~/.esp-handset/mouse_step)."""
    from PyQt5.QtWidgets import QSizePolicy

    PRESETS = [
        ("Very slow", 3),
        ("Slow", 6),
        ("Normal", 10),
        ("Fast", 16),
        ("Turbo", 24),
    ]
    step_path = DATA / "mouse_step"
    etc_path = Path("/etc/esp-handset/mouse_step")

    body = QWidget()
    lay = QVBoxLayout(body)
    tip = QLabel(
        "D-pad mouse speed on Linux desktop.\n"
        "(Phone Digivice UI uses keys, not the mouse.)"
    )
    tip.setWordWrap(True)
    tip.setStyleSheet("color:#9ab;font-size:10px;")
    cur = QLabel("")
    cur.setWordWrap(True)
    cur.setStyleSheet("font-weight:700;")
    lay.addWidget(tip)
    lay.addWidget(cur)

    def _read_step() -> int:
        for p in (step_path, etc_path):
            try:
                if p.is_file():
                    v = int(p.read_text(encoding="utf-8").strip().split()[0])
                    if 1 <= v <= 64:
                        return v
            except (OSError, ValueError):
                continue
        return 10

    def _label_for(v: int) -> str:
        for name, n in PRESETS:
            if n == v:
                return name
        return f"Custom ({v})"

    def refresh() -> None:
        v = _read_step()
        cur.setText(f"Current: {_label_for(v)}  ·  step {v}")

    def set_step(n: int) -> None:
        DATA.mkdir(parents=True, exist_ok=True)
        step_path.write_text(f"{n}\n", encoding="utf-8")
        try:
            subprocess.run(
                ["sudo", "-n", "tee", str(etc_path)],
                input=f"{n}\n".encode(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
        except Exception:
            pass
        refresh()

    for name, n in PRESETS:
        b = QPushButton(f"{name}  ({n})")
        b.setMinimumHeight(28)
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        b.clicked.connect(lambda _=False, v=n: set_step(v))
        lay.addWidget(b)

    lay.addStretch(1)
    refresh()
    return page_chrome("Mouse speed", body, on_back)


def make_debug_page(on_back: Callable[[], None]) -> QWidget:
    """Hardware debug: big PASS/FAIL audio checks for soldered mic & speaker."""
    import struct
    import wave
    from shutil import which

    from PyQt5.QtCore import QProcess, QTimer
    from PyQt5.QtWidgets import QSizePolicy

    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(4)

    def _badge(title: str) -> QLabel:
        lab = QLabel(f"{title}\n—")
        lab.setAlignment(Qt.AlignCenter)
        lab.setWordWrap(True)
        lab.setMinimumHeight(44)
        lab.setStyleSheet(
            "font-size:13px; font-weight:700; padding:6px;"
            "background:#1a2230; color:#cde; border:1px solid #345;"
        )
        return lab

    spk_badge = _badge("SPEAKER")
    mic_badge = _badge("MIC")
    row = QHBoxLayout()
    row.setSpacing(4)
    row.addWidget(spk_badge, 1)
    row.addWidget(mic_badge, 1)
    lay.addLayout(row)

    hw = QLabel("Scanning audio…")
    hw.setWordWrap(True)
    hw.setAlignment(Qt.AlignCenter)
    hw.setStyleSheet("font-size:12px; font-weight:700; color:#ffd700;")
    lay.addWidget(hw)

    status = QLabel("Pick a test below.")
    status.setWordWrap(True)
    status.setAlignment(Qt.AlignCenter)
    status.setStyleSheet("font-size:12px; color:#cde;")
    lay.addWidget(status)

    spk_btn = QPushButton("1 · Play beep")
    spk_btn.setMinimumHeight(34)
    spk_btn.setStyleSheet("font-size:13px; font-weight:700;")
    mic_btn = QPushButton("2 · Mic test")
    mic_btn.setMinimumHeight(34)
    mic_btn.setStyleSheet("font-size:13px; font-weight:700;")

    hear_row = QHBoxLayout()
    hear_tip = QLabel("Heard it?")
    hear_tip.setStyleSheet("font-size:12px; font-weight:700;")
    yes_btn = QPushButton("YES")
    no_btn = QPushButton("NO")
    yes_btn.setMinimumHeight(32)
    no_btn.setMinimumHeight(32)
    yes_btn.setStyleSheet("font-size:13px; font-weight:700; background:#1a4a2a;")
    no_btn.setStyleSheet("font-size:13px; font-weight:700; background:#4a1a1a;")
    yes_btn.setEnabled(False)
    no_btn.setEnabled(False)
    hear_row.addWidget(hear_tip)
    hear_row.addWidget(yes_btn, 1)
    hear_row.addWidget(no_btn, 1)

    stop_btn = QPushButton("Stop")
    stop_btn.setMinimumHeight(26)

    for b in (spk_btn, mic_btn, stop_btn, yes_btn, no_btn):
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    lay.addWidget(spk_btn)
    lay.addWidget(mic_btn)
    lay.addLayout(hear_row)
    lay.addWidget(stop_btn)
    lay.addStretch(1)

    procs: list = []
    test_wav = DATA / "debug_mic_test.wav"
    busy = {"on": False}
    pending = {"kind": None}  # "speaker" | "mic" after a test finishes
    state = {"spk_dev": False, "mic_dev": False, "spk": "?", "mic": "?"}

    def _which(name: str) -> Optional[str]:
        return which(name)

    def _set_badge(lab: QLabel, title: str, verdict: str) -> None:
        """verdict: ok | bad | none | wait | ask"""
        colors = {
            "ok": ("#0d3d1f", "#7dffa0", "PASS"),
            "bad": ("#4a1010", "#ff8a8a", "FAIL"),
            "none": ("#3a2a10", "#ffcc66", "NO DEVICE"),
            "wait": ("#1a2230", "#cde", "…"),
            "ask": ("#1a3040", "#9cf", "DID YOU HEAR IT?"),
            "?": ("#1a2230", "#cde", "—"),
        }
        bg, fg, word = colors.get(verdict, colors["?"])
        lab.setText(f"{title}\n{word}")
        lab.setStyleSheet(
            f"font-size:14px; font-weight:700; padding:8px;"
            f"background:{bg}; color:{fg}; border:2px solid {fg};"
        )

    def _kill_all() -> None:
        for p in list(procs):
            try:
                if isinstance(p, QProcess):
                    if p.state() != QProcess.NotRunning:
                        p.kill()
                        p.waitForFinished(800)
            except Exception:
                pass
        procs.clear()
        for name in ("speaker-test", "arecord", "aplay", "paplay", "ffplay", "mpv"):
            try:
                subprocess.run(
                    ["pkill", "-f", name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    check=False,
                )
            except Exception:
                pass

    def _set_busy(on: bool) -> None:
        busy["on"] = on
        spk_btn.setEnabled(not on)
        mic_btn.setEnabled(not on)

    def _ask_heard(kind: str) -> None:
        pending["kind"] = kind
        yes_btn.setEnabled(True)
        no_btn.setEnabled(True)
        if kind == "speaker":
            _set_badge(spk_badge, "SPEAKER", "ask")
            status.setText("Beep played.\nPress YES if you heard it,\nNO if silence.")
        else:
            _set_badge(mic_badge, "MIC", "ask")
            status.setText("Playback done.\nHeard your voice? YES / NO")

    def _clear_ask() -> None:
        pending["kind"] = None
        yes_btn.setEnabled(False)
        no_btn.setEnabled(False)

    def on_yes() -> None:
        kind = pending.get("kind")
        _clear_ask()
        if kind == "speaker":
            state["spk"] = "ok"
            _set_badge(spk_badge, "SPEAKER", "ok")
            status.setText("SPEAKER: PASS\nAmp + wiring look good.")
        elif kind == "mic":
            state["mic"] = "ok"
            _set_badge(mic_badge, "MIC", "ok")
            status.setText("MIC: PASS\nMic + speaker loop OK.")

    def on_no() -> None:
        kind = pending.get("kind")
        _clear_ask()
        if kind == "speaker":
            state["spk"] = "bad"
            _set_badge(spk_badge, "SPEAKER", "bad")
            status.setText(
                "SPEAKER: FAIL\nCheck amp power, DIN/BCLK/LRC,\nvolume, and solder joints."
            )
        elif kind == "mic":
            state["mic"] = "bad"
            _set_badge(mic_badge, "MIC", "bad")
            status.setText(
                "MIC: FAIL\nIf speaker PASS but this FAIL →\nmic wiring/gain. Else both."
            )

    def _run_cmd(cmd: list, timeout_ms: int = 0) -> QProcess:
        p = QProcess(body)
        p.setProcessChannelMode(QProcess.MergedChannels)
        procs.append(p)
        p.start(cmd[0], cmd[1:])
        if timeout_ms > 0:

            def _to() -> None:
                if p.state() != QProcess.NotRunning:
                    p.kill()

            QTimer.singleShot(timeout_ms, _to)
        return p

    def _count_cards(tool: str) -> int:
        if not _which(tool):
            return -1
        try:
            r = subprocess.run(
                [tool, "-l"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            out = (r.stdout or "") + (r.stderr or "")
            return sum(1 for line in out.splitlines() if line.lower().startswith("card "))
        except Exception:
            return -1

    def scan_hw() -> None:
        play_n = _count_cards("aplay")
        cap_n = _count_cards("arecord")
        state["spk_dev"] = play_n > 0
        state["mic_dev"] = cap_n > 0
        parts = []
        if play_n < 0:
            parts.append("aplay missing")
        elif play_n == 0:
            parts.append("Speaker: NO CARD")
            _set_badge(spk_badge, "SPEAKER", "none")
        else:
            parts.append(f"Speaker: {play_n} card(s)")
            if state["spk"] == "?":
                _set_badge(spk_badge, "SPEAKER", "?")
        if cap_n < 0:
            parts.append("arecord missing")
        elif cap_n == 0:
            parts.append("Mic: NO CARD")
            _set_badge(mic_badge, "MIC", "none")
        else:
            parts.append(f"Mic: {cap_n} card(s)")
            if state["mic"] == "?":
                _set_badge(mic_badge, "MIC", "?")
        if play_n == 0 and cap_n == 0:
            hw.setText("NO AUDIO HARDWARE\nCheck USB/I2S / solder")
            status.setText("Nothing for Linux to play or record.")
        elif play_n <= 0 and cap_n <= 0:
            hw.setText("Install: sudo apt install alsa-utils")
        else:
            hw.setText(" · ".join(parts))

    def _wav_level(path: Path) -> tuple[float, float]:
        """Return (peak 0..1, rms 0..1) for 16-bit wav, or (0,0)."""
        try:
            with wave.open(str(path), "rb") as w:
                nch = w.getnchannels()
                sw = w.getsampwidth()
                nframes = w.getnframes()
                raw = w.readframes(nframes)
            if sw != 2 or not raw:
                return 0.0, 0.0
            n = len(raw) // 2
            samples = struct.unpack("<" + "h" * n, raw[: n * 2])
            if nch > 1:
                samples = samples[::nch]
            if not samples:
                return 0.0, 0.0
            peak = max(abs(s) for s in samples) / 32768.0
            acc = sum((s / 32768.0) ** 2 for s in samples)
            rms = (acc / len(samples)) ** 0.5
            return peak, rms
        except Exception:
            return 0.0, 0.0

    def speaker_test() -> None:
        if busy["on"]:
            return
        _clear_ask()
        if not state["spk_dev"] and _count_cards("aplay") == 0:
            _set_badge(spk_badge, "SPEAKER", "none")
            status.setText("No playback device.\nCannot test speaker.")
            return
        _kill_all()
        _set_busy(True)
        _set_badge(spk_badge, "SPEAKER", "wait")
        status.setText("Playing beep…\nListen for a tone.")
        if _which("speaker-test"):
            p = _run_cmd(
                ["speaker-test", "-t", "sine", "-f", "880", "-l", "1", "-c", "1"],
                timeout_ms=3500,
            )

            def _done(_code=0, _st=None) -> None:
                _set_busy(False)
                _ask_heard("speaker")

            p.finished.connect(_done)
            return
        oga = Path("/usr/share/sounds/freedesktop/stereo/bell.oga")
        if not oga.is_file():
            oga = Path("/usr/share/sounds/freedesktop/stereo/message.oga")
        if _which("paplay") and oga.is_file():
            p = _run_cmd(["paplay", str(oga)], timeout_ms=5000)

            def _done2(_code=0, _st=None) -> None:
                _set_busy(False)
                _ask_heard("speaker")

            p.finished.connect(_done2)
            return
        if _which("aplay") and Path("/usr/share/sounds/alsa/Front_Center.wav").is_file():
            p = _run_cmd(
                ["aplay", "/usr/share/sounds/alsa/Front_Center.wav"],
                timeout_ms=5000,
            )

            def _done3(_code=0, _st=None) -> None:
                _set_busy(False)
                _ask_heard("speaker")

            p.finished.connect(_done3)
            return
        _set_busy(False)
        _set_badge(spk_badge, "SPEAKER", "bad")
        status.setText("No player tool.\nsudo apt install alsa-utils")

    def mic_test() -> None:
        if busy["on"]:
            return
        _clear_ask()
        if not _which("arecord"):
            _set_badge(mic_badge, "MIC", "bad")
            status.setText("arecord missing.\nsudo apt install alsa-utils")
            return
        if not state["mic_dev"] and _count_cards("arecord") == 0:
            _set_badge(mic_badge, "MIC", "none")
            status.setText("No capture device.\nMic not seen by Linux.")
            return
        _kill_all()
        DATA.mkdir(parents=True, exist_ok=True)
        try:
            if test_wav.is_file():
                test_wav.unlink()
        except OSError:
            pass
        _set_busy(True)
        _set_badge(mic_badge, "MIC", "wait")
        status.setText("Recording 3s…\nSpeak into the mic NOW.")

        rec = _run_cmd(
            [
                "arecord",
                "-d",
                "3",
                "-f",
                "S16_LE",
                "-r",
                "16000",
                "-c",
                "1",
                str(test_wav),
            ],
            timeout_ms=8000,
        )

        def _after_rec(code: int, _st) -> None:
            if code != 0 or not test_wav.is_file() or test_wav.stat().st_size < 100:
                _set_busy(False)
                state["mic"] = "bad"
                _set_badge(mic_badge, "MIC", "bad")
                status.setText(
                    "MIC: FAIL\nRecord failed.\nWiring, mute, or no device."
                )
                return
            peak, rms = _wav_level(test_wav)
            pct = int(peak * 100)
            # Very quiet → likely dead mic / not connected
            if peak < 0.02 and rms < 0.005:
                _set_busy(False)
                state["mic"] = "bad"
                _set_badge(mic_badge, "MIC", "bad")
                status.setText(
                    f"MIC: FAIL (silent)\nLevel {pct}% — no voice picked up.\n"
                    "Check mic solder / bias / gain."
                )
                return
            status.setText(f"Got signal ({pct}% peak).\nPlaying it back…")
            play_cmd = None
            if _which("aplay"):
                play_cmd = ["aplay", str(test_wav)]
            elif _which("paplay"):
                play_cmd = ["paplay", str(test_wav)]
            elif _which("ffplay"):
                play_cmd = ["ffplay", "-nodisp", "-autoexit", str(test_wav)]
            if not play_cmd:
                _set_busy(False)
                # Mic captured audio — soft pass even without playback
                state["mic"] = "ok"
                _set_badge(mic_badge, "MIC", "ok")
                status.setText(
                    f"MIC: PASS (level {pct}%)\nNo player to hear it back."
                )
                return
            play = _run_cmd(play_cmd, timeout_ms=8000)

            def _after_play(_c=0, _s=None) -> None:
                _set_busy(False)
                # Auto: mic got signal. Still ask if they heard playback.
                status.setText(
                    f"Mic level {pct}% (signal OK).\n"
                    "Heard your voice on speaker?\nYES / NO"
                )
                _ask_heard("mic")

            play.finished.connect(_after_play)

        rec.finished.connect(_after_rec)

    def stop_test() -> None:
        _kill_all()
        _set_busy(False)
        _clear_ask()
        status.setText("Stopped.")
        if state["spk"] == "?":
            _set_badge(spk_badge, "SPEAKER", "?")
        if state["mic"] == "?":
            _set_badge(mic_badge, "MIC", "?")

    spk_btn.clicked.connect(speaker_test)
    mic_btn.clicked.connect(mic_test)
    stop_btn.clicked.connect(stop_test)
    yes_btn.clicked.connect(on_yes)
    no_btn.clicked.connect(on_no)
    QTimer.singleShot(150, scan_hw)
    return page_chrome("Debug · Audio", body, on_back)


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
        "Back → previous screen\n"
        "Back×3 on Digivice home → desktop\n"
        "Home → Digivice home (never desktop)\n"
        "F12 / F10 / Ctrl+Q → desktop\n"
        "Settings → Linux → Exit\n"
        "Settings → Update → software only\n"
        "Settings → Mouse → desktop pointer speed\n"
        "Settings → Debug → mic / speaker test\n"
        "Settings → Power → Off/Restart (x2)\n"
        "SSH: digivice-leave\n"
        "Settings → Linux → confirm",
        on_back,
    )


def make_network_page(
    modem,
    on_back,
    on_status,
    get_modem=None,
    set_modem=None,
) -> QWidget:
    body = QWidget()
    lay = QVBoxLayout(body)
    lab = QLabel("Tap refresh for modem")
    lab.setWordWrap(True)
    lab.setStyleSheet("font-size:11px;")
    btn = QPushButton("Refresh status")
    btn.setMinimumHeight(28)
    scan = QPushButton("Scan USB ports")
    scan.setMinimumHeight(28)
    recon = QPushButton("Reconnect modem")
    recon.setMinimumHeight(30)
    recon.setStyleSheet("font-weight:700;")
    lay.addWidget(lab)
    lay.addWidget(btn)
    lay.addWidget(scan)
    lay.addWidget(recon)
    lay.addStretch(1)

    def _cur():
        if get_modem:
            return get_modem()
        return modem

    def refresh():
        m = _cur()
        if not m:
            from esp_handset.sim7600 import Sim7600

            lab.setText("SIM7600 not connected\n\n" + Sim7600.diagnose())
            return
        try:
            csq = m.signal() or "CSQ ?"
            lab.setText(f"Port: {m.port}\n{csq}")
            on_status(csq)
        except Exception as e:
            lab.setText(str(e).strip() or "modem error")

    def do_scan():
        from esp_handset.sim7600 import Sim7600

        lab.setText(Sim7600.diagnose())
        on_status("modem scan")

    def do_reconnect():
        from esp_handset.sim7600 import Sim7600

        lab.setText("Connecting…\nprobing ttyUSB for AT")
        old = _cur()
        try:
            if old is not None:
                try:
                    old.close()
                except Exception:
                    pass
            m = Sim7600()
            m.open(retries=8, retry_s=2.0)
            if set_modem:
                set_modem(m)
            lab.setText(f"Connected!\nPort: {m.port}\n" + (m.signal() or ""))
            on_status(f"modem {m.port}")
        except Exception as e:
            if set_modem:
                set_modem(None)
            msg = str(e).strip() or "reconnect failed"
            lab.setText(msg + "\n\n" + Sim7600.diagnose())
            on_status("modem fail")

    btn.clicked.connect(refresh)
    scan.clicked.connect(do_scan)
    recon.clicked.connect(do_reconnect)
    refresh()
    return page_chrome("Network", body, on_back)
