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


def _sip_config_path() -> Path:
    """Prefer a sip.env the Digivice user can actually read (not root-only /etc)."""
    home = DATA / "sip.env"
    etc = Path("/etc/esp-handset/sip.env")
    for p in (home, etc):
        try:
            if p.is_file() and os.access(p, os.R_OK):
                return p
        except OSError:
            continue
    return home


CONFIG = _sip_config_path()


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
    """Page body only. Title lives in the shell status bar (clock · title · SIM).
    Hardware Back is the back control — no in-page ← row (that ate the Dial pad)."""
    from PyQt5.QtWidgets import QSizePolicy

    del on_back  # hardware Back / on_hardware_back on nested pages
    w = QWidget()
    w.setProperty("digiTitle", title)
    lay = QVBoxLayout(w)
    lay.setContentsMargins(3, 2, 3, 2)
    lay.setSpacing(2)

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
    from esp_handset.call_ui import make_phone_page as _make

    return _make(on_back, on_status, on_call_log=on_call_log)


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
    """Contacts: letter×contact radial → actions → edit / photo."""
    from PyQt5.QtGui import QIcon
    from PyQt5.QtWidgets import QSizePolicy

    from esp_handset import digi_nav
    from esp_handset.contacts_radial import ContactsRadial

    _ED = (
        "font-size:11px; padding:2px 4px; min-height:22px; max-height:24px;"
    )
    _BTN = "font-size:11px; font-weight:700; padding:2px 4px;"

    root = QWidget()
    stack = QStackedWidget(root)
    outer = QVBoxLayout(root)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    outer.addWidget(stack)

    # ----- LIST (radial + Add) -----
    list_page = QWidget()
    ll = QVBoxLayout(list_page)
    ll.setContentsMargins(2, 1, 2, 1)
    ll.setSpacing(2)

    def _channels_line(c: dict) -> str:
        bits = []
        if c.get("phone"):
            bits.append(str(c["phone"]))
        if c.get("lora"):
            bits.append(f"LoRa {c['lora']}")
        if c.get("email"):
            bits.append(str(c["email"]))
        return " · ".join(bits) if bits else "(no channels)"

    def _photo_for(c: dict) -> Optional[str]:
        p = _contact_photo_file(c)
        return str(p) if p else None

    radial = ContactsRadial(
        list_page,
        channels_line=lambda c: _elide_one_line(_channels_line(c), 28),
        photo_path=_photo_for,
        avatar_color=_avatar_color,
    )
    add_btn = QPushButton("＋ Add")
    add_btn.setFixedHeight(26)
    # No per-button background — let shell digiFocus yellow work
    add_btn.setStyleSheet("font-size:11px; font-weight:700; padding:2px 4px;")
    ll.addWidget(radial, 1)
    ll.addWidget(add_btn)
    stack.addWidget(list_page)

    # ----- ACTIONS (radial: Call / SMS / LoRa / @ / Edit) -----
    from esp_handset.radial_menu import RadialMenu
    from esp_handset.shell_data import AppEntry

    actions_page = QWidget()
    al = QVBoxLayout(actions_page)
    al.setContentsMargins(2, 0, 2, 0)
    al.setSpacing(0)
    act_title = QLabel("Contact")
    act_title.setAlignment(Qt.AlignCenter)
    act_title.setFixedHeight(16)
    act_title.setStyleSheet("font-size:11px; font-weight:800; color:#e8eef5;")
    act_sub = QLabel("")
    act_sub.setAlignment(Qt.AlignCenter)
    act_sub.setFixedHeight(14)
    act_sub.setStyleSheet("font-size:8px; color:#8aa;")
    act_sub.setWordWrap(False)
    al.addWidget(act_title)
    al.addWidget(act_sub)
    actions_radial = RadialMenu([], actions_page)
    al.addWidget(actions_radial, 1)
    stack.addWidget(actions_page)

    # ----- EDIT (fields only) -----
    edit_page = QWidget()
    el = QVBoxLayout(edit_page)
    el.setContentsMargins(2, 1, 2, 1)
    el.setSpacing(2)

    top = QHBoxLayout()
    top.setSpacing(4)
    preview = QLabel("?")
    preview.setAlignment(Qt.AlignCenter)
    preview.setFixedSize(28, 28)
    preview.setStyleSheet("font-size:12px; font-weight:800; background:#1a2230;")
    name_ed = QLineEdit()
    name_ed.setPlaceholderText("Name")
    name_ed.setStyleSheet(_ED)
    name_ed.setFixedHeight(24)
    top.addWidget(preview)
    top.addWidget(name_ed, 1)
    el.addLayout(top)

    phone_ed = QLineEdit()
    phone_ed.setPlaceholderText("Phone")
    phone_ed.setStyleSheet(_ED)
    phone_ed.setFixedHeight(24)
    lora_ed = QLineEdit()
    lora_ed.setPlaceholderText("LoRa ID")
    lora_ed.setStyleSheet(_ED)
    lora_ed.setFixedHeight(24)
    email_ed = QLineEdit()
    email_ed.setPlaceholderText("Email")
    email_ed.setStyleSheet(_ED)
    email_ed.setFixedHeight(24)
    el.addWidget(phone_ed)
    el.addWidget(lora_ed)
    el.addWidget(email_ed)

    form_status = QLabel("")
    form_status.setStyleSheet("color:#ffcc66;font-size:9px;")
    form_status.setFixedHeight(14)
    form_status.hide()
    el.addWidget(form_status)

    row1 = QHBoxLayout()
    row1.setSpacing(2)
    photo_btn = QPushButton("Photo")
    clear_photo = QPushButton("No pic")
    save_btn = QPushButton("Save")
    for b in (photo_btn, clear_photo, save_btn):
        b.setFixedHeight(26)
        b.setStyleSheet(
            "font-size:11px; font-weight:700; padding:2px 4px;"
            'QPushButton[digiFocus="1"] { background:#FFE600; color:#000;'
            "border:2px solid #000; }"
        )
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    save_btn.setStyleSheet(
        "font-size:11px; font-weight:700; padding:2px 4px; background:#1a7a3a;"
        'QPushButton[digiFocus="1"] { background:#FFE600; color:#000;'
        "border:2px solid #000; }"
    )
    row1.addWidget(photo_btn, 1)
    row1.addWidget(clear_photo, 1)
    row1.addWidget(save_btn, 1)
    el.addLayout(row1)
    el.addStretch(1)
    stack.addWidget(edit_page)

    # ----- PHOTO PICKER (own screen) -----
    photo_page = QWidget()
    pl = QVBoxLayout(photo_page)
    pl.setContentsMargins(2, 1, 2, 1)
    pl.setSpacing(2)
    photo_tip = QLabel("Confirm a Camera shot · Back = edit")
    photo_tip.setStyleSheet("color:#9ab;font-size:9px;")
    photo_list = QListWidget()
    photo_list.setIconSize(QSize(36, 28))
    photo_list.setStyleSheet(
        "QListWidget { background:#121820; border: none; }"
        "QListWidget::item { padding: 2px; }"
        "QListWidget::item:selected { background:#FFE600; color:#000; }"
    )
    photo_done = QPushButton("Done")
    photo_done.setFixedHeight(26)
    photo_done.setStyleSheet(_BTN)
    pl.addWidget(photo_tip)
    pl.addWidget(photo_list, 1)
    pl.addWidget(photo_done)
    stack.addWidget(photo_page)

    state = {"index": -1, "image": "", "mode": "add"}

    def _set_status(msg: str) -> None:
        if msg:
            form_status.setText(msg)
            form_status.show()
        else:
            form_status.hide()
            form_status.clear()

    def _refresh_preview() -> None:
        name = name_ed.text().strip() or "?"
        initial = name[:1].upper()
        if not initial.isalnum():
            initial = "#"
        photo = None
        if state["image"]:
            p = CONTACT_PHOTOS / state["image"]
            if not p.is_file():
                p = Path(state["image"])
            if p.is_file():
                photo = str(p)
        if photo:
            pix = QPixmap(photo)
            if not pix.isNull():
                preview.setPixmap(
                    pix.scaled(28, 28, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                )
                preview.setText("")
                preview.setStyleSheet("background:#1a2230;")
                return
        preview.setPixmap(QPixmap())
        preview.setText(initial)
        preview.setStyleSheet(
            f"font-size:12px; font-weight:800; color:#fff;"
            f"background:{_avatar_color(name)};"
        )

    def show_list() -> None:
        stack.setCurrentWidget(list_page)
        refresh_list()
        digi_nav.ensure_page_focus(chrome)

    def show_actions() -> None:
        stack.setCurrentWidget(actions_page)
        digi_nav.ensure_page_focus(chrome)

    def show_edit() -> None:
        stack.setCurrentWidget(edit_page)
        digi_nav.ensure_page_focus(chrome)
        name_ed.setFocus(Qt.OtherFocusReason)

    def refresh_list() -> None:
        contacts = _load_contacts()
        _save_contacts(contacts)
        contacts = _load_contacts()
        radial.set_contacts(contacts)

    def load_gallery_photos() -> None:
        photo_list.clear()
        try:
            paths = list(pi_camera.list_photos(limit=50))
        except Exception:
            paths = []
        if not paths and PHOTOS.is_dir():
            paths = sorted(
                [
                    p
                    for p in PHOTOS.iterdir()
                    if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp")
                ],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:50]
        if not paths:
            item = QListWidgetItem("No Camera photos — snap first")
            item.setFlags(Qt.NoItemFlags)
            photo_list.addItem(item)
            return
        for p in paths:
            it = QListWidgetItem(p.name)
            it.setData(Qt.UserRole, str(p))
            try:
                pix = QPixmap(str(p))
                if not pix.isNull():
                    it.setIcon(
                        QIcon(
                            pix.scaled(36, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        )
                    )
            except Exception:
                pass
            photo_list.addItem(it)

    def fill_form(c: Optional[dict]) -> None:
        c = c or {}
        name_ed.setText(str(c.get("name") or ""))
        phone_ed.setText(str(c.get("phone") or ""))
        lora_ed.setText(str(c.get("lora") or ""))
        email_ed.setText(str(c.get("email") or ""))
        state["image"] = str(c.get("image") or "")
        _set_status("")
        _refresh_preview()

    def _refresh_actions(c: Optional[dict]) -> None:
        c = c or {}
        name = str(c.get("name") or "Contact")
        act_title.setText(name)
        act_sub.setText(_elide_one_line(_channels_line(c), 40))
        entries: List[AppEntry] = []
        if c.get("phone"):
            entries.append(AppEntry("act_call", "Call", str(c.get("phone") or ""), "☎"))
            if open_sms is not None:
                entries.append(AppEntry("act_sms", "SMS", "Text message", "✉"))
        if c.get("lora") and open_lora is not None:
            entries.append(AppEntry("act_lora", "LoRa", str(c.get("lora") or ""), "⌁"))
        if c.get("email") and open_email is not None:
            entries.append(AppEntry("act_mail", "Email", str(c.get("email") or ""), "@"))
        entries.append(AppEntry("act_edit", "Edit", "Name · photo · channels", "✎"))
        actions_radial.set_entries(entries, 0)

    def on_action_key(key: str) -> None:
        if key == "act_call":
            do_call()
        elif key == "act_sms":
            do_sms()
        elif key == "act_lora":
            do_lora()
        elif key == "act_mail":
            do_email()
        elif key == "act_edit":
            open_editor(state["index"])

    def open_actions(index: int) -> None:
        contacts = _load_contacts()
        if index < 0 or index >= len(contacts):
            return
        state["mode"] = "edit"
        state["index"] = index
        fill_form(contacts[index])
        _refresh_actions(contacts[index])
        show_actions()

    def open_editor(index: int = -1) -> None:
        contacts = _load_contacts()
        if index >= 0 and index < len(contacts):
            state["mode"] = "edit"
            state["index"] = index
            fill_form(contacts[index])
        else:
            state["mode"] = "add"
            state["index"] = -1
            fill_form(None)
        show_edit()

    def open_photo_picker() -> None:
        load_gallery_photos()
        stack.setCurrentWidget(photo_page)
        digi_nav.ensure_page_focus(chrome)

    def on_photo_chosen() -> None:
        item = photo_list.currentItem()
        if item is None or not (item.flags() & Qt.ItemIsEnabled):
            return
        path = item.data(Qt.UserRole)
        if not path:
            return
        try:
            rel = _import_contact_photo(
                Path(str(path)), name_ed.text().strip() or "contact"
            )
            state["image"] = rel
            _set_status("Photo set")
            _refresh_preview()
            show_edit()
        except Exception as e:
            _set_status(str(e)[:40])

    def do_clear_photo() -> None:
        state["image"] = ""
        _set_status("No photo")
        _refresh_preview()

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
            _set_status("Need phone, LoRa, or email")
            return
        contacts = _load_contacts()
        if state["mode"] == "edit" and 0 <= state["index"] < len(contacts):
            contacts[state["index"]] = c
        else:
            contacts.append(c)
        _save_contacts(contacts)
        show_list()

    def current_contact() -> Optional[dict]:
        contacts = _load_contacts()
        idx = state["index"]
        if 0 <= idx < len(contacts):
            return contacts[idx]
        return None

    def do_call() -> None:
        c = current_contact()
        if c and c.get("phone"):
            open_dial(str(c["phone"]))

    def do_sms() -> None:
        c = current_contact()
        if open_sms and c and c.get("phone"):
            open_sms(str(c["phone"]))

    def do_lora() -> None:
        c = current_contact()
        if open_lora and c and c.get("lora"):
            open_lora(str(c["lora"]))

    def do_email() -> None:
        c = current_contact()
        if open_email and c and c.get("email"):
            open_email(str(c["email"]))

    def chrome_back() -> None:
        cur = stack.currentWidget()
        if cur is photo_page:
            show_edit()
        elif cur is edit_page:
            if state["mode"] == "edit" and state["index"] >= 0:
                _refresh_actions(current_contact())
                show_actions()
            else:
                show_list()
        elif cur is actions_page:
            show_list()
        else:
            on_back()

    def on_hardware_back() -> bool:
        cur = stack.currentWidget()
        if cur is photo_page:
            show_edit()
            return True
        if cur is edit_page:
            if state["mode"] == "edit" and state["index"] >= 0:
                _refresh_actions(current_contact())
                show_actions()
            else:
                show_list()
            return True
        if cur is actions_page:
            show_list()
            return True
        return False

    name_ed.textChanged.connect(lambda _t: _refresh_preview())
    radial.activated.connect(open_actions)
    actions_radial.activated.connect(on_action_key)
    add_btn.clicked.connect(lambda: open_editor(-1))
    photo_btn.clicked.connect(open_photo_picker)
    photo_list.itemActivated.connect(lambda _i: on_photo_chosen())
    photo_list.itemClicked.connect(lambda _i: on_photo_chosen())
    photo_done.clicked.connect(show_edit)
    clear_photo.clicked.connect(do_clear_photo)
    save_btn.clicked.connect(do_save)

    chrome = page_chrome("Contacts", root, chrome_back, scroll=False)
    chrome.on_hardware_back = on_hardware_back  # type: ignore[attr-defined]
    chrome.refresh_contacts = show_list  # type: ignore[attr-defined]
    show_list()
    return chrome


def make_call_log_page(on_back, on_redial=None) -> QWidget:
    from esp_handset.call_ui import make_call_log_page as _make

    return _make(on_back, on_redial=on_redial)


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
    tip = QLabel("Photos from Camera")
    tip.setStyleSheet("color:#5ec4a8;font-size:11px;font-weight:700;")
    tip.setWordWrap(True)
    lst = QListWidget()
    lst.setIconSize(QSize(72, 54))
    lst.setSpacing(3)
    lst.setUniformItemSizes(True)
    lst.setResizeMode(QListWidget.Adjust)
    lst.setWordWrap(True)
    lst.setStyleSheet(
        "QListWidget { background:#16202c; border:1px solid #243040; border-radius:8px;"
        " outline:none; color:#e8eef5; font-size:11px; }"
        "QListWidget::item { padding:6px; border-bottom:1px solid #243040; }"
        "QListWidget::item:selected { background:#1a3a32; }"
        'QListWidget[digiFocus="1"] { border:2px solid #FFE600; }'
    )
    refresh = QPushButton("Refresh")
    refresh.setMinimumHeight(30)
    refresh.setStyleSheet(
        "QPushButton { font-size:11px; font-weight:700; padding:4px 10px;"
        " color:#0a1218; background:#5ec4a8; border:none; border-radius:8px; }"
        'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
    )
    empty = QLabel("No photos yet.\nOpen Camera on home · Snap")
    empty.setAlignment(Qt.AlignCenter)
    empty.setStyleSheet(
        "color:#7a8a9a; font-size:11px; padding:16px; background:#16202c;"
        " border-radius:8px; border:1px dashed #243040;"
    )
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

    def on_hardware_back() -> bool:
        if stack.currentWidget() is view_page:
            show_list_mode()
            return True
        return False

    chrome.on_hardware_back = on_hardware_back  # type: ignore[attr-defined]
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
    from esp_handset.media_ui import media_btn, media_header, style_media_body, _SURFACE, _TEXT, _BORDER

    body = QWidget()
    style_media_body(body)
    lay = QVBoxLayout(body)
    lay.setContentsMargins(4, 2, 4, 2)
    lay.setSpacing(4)
    lay.addWidget(media_header("✎", "Notes", "Autosave when you hit Save"))
    edit = QTextEdit()
    edit.setPlainText("\n".join(_load_json(NOTES, ["(new note)"])))
    edit.setStyleSheet(
        f"QTextEdit {{ background:{_SURFACE}; color:{_TEXT}; border:1px solid {_BORDER};"
        f" border-radius:8px; font-size:12px; padding:8px; }}"
    )
    save = media_btn("Save", primary=True)
    lay.addWidget(edit, 1)
    lay.addWidget(save)

    def do_save():
        lines = [ln for ln in edit.toPlainText().splitlines() if ln.strip()]
        _save_json(NOTES, lines or ["(empty)"])

    save.clicked.connect(do_save)
    return page_chrome("Notes", body, on_back, scroll=False)


def make_todos_page(on_back) -> QWidget:
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
    lay.addWidget(media_header("☑", "Todos", "Confirm adds · keep it short"))
    lst = media_list()
    empty = media_empty("Nothing to do.\nAdd one below.")
    empty.hide()
    inp = QLineEdit()
    inp.setPlaceholderText("New todo")
    inp.setStyleSheet(
        f"QLineEdit {{ background:{_SURFACE}; color:{_TEXT}; border:1px solid {_BORDER};"
        f" border-radius:8px; padding:6px 8px; font-size:12px; }}"
    )
    add = media_btn("Add", primary=True)
    lay.addWidget(lst, 1)
    lay.addWidget(empty)
    lay.addWidget(inp)
    lay.addWidget(add)

    def refresh():
        lst.clear()
        items = _load_json(TODOS, [])
        for t in items:
            lst.addItem(f"○  {t}")
        if not items:
            lst.hide()
            empty.show()
        else:
            empty.hide()
            lst.show()

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
    inp.returnPressed.connect(do_add)
    refresh()
    return page_chrome("Todos", body, on_back, scroll=False)


def make_clock_page(on_back) -> QWidget:
    from esp_handset.clock_ui import make_alarms_page

    return make_alarms_page(on_back)


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


def _panel_rotation_degrees() -> str:
    for path in (
        Path("/etc/esp-handset/panel-rotation"),
        Path.home() / ".esp-handset" / "panel-rotation",
    ):
        try:
            if path.is_file():
                v = path.read_text(encoding="utf-8").strip()
                if v in ("0", "90", "180", "270"):
                    return v
        except OSError:
            continue
    return os.environ.get("ESP_PANEL_ROTATION", "0").strip() or "0"


def make_orientation_page(on_back: Callable[[], None]) -> QWidget:
    """Flip Waveshare 2\" panel for different cases (saves + reboot)."""
    from PyQt5.QtCore import QTimer

    from esp_handset.radial_menu import RadialMenu
    from esp_handset.shell_data import AppEntry

    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(2, 0, 2, 0)
    lay.setSpacing(2)
    tip = QLabel("Pick rotation · Confirm applies · Reboot finishes")
    tip.setWordWrap(True)
    tip.setStyleSheet("color:#9ab;font-size:9px;")
    tip.setFixedHeight(28)
    current = QLabel("")
    current.setStyleSheet("font-size:10px; font-weight:700;")
    status = QLabel("Ready.")
    status.setWordWrap(True)
    status.setStyleSheet("color:#8aa;font-size:9px;")
    status.setFixedHeight(36)
    lay.addWidget(tip)
    lay.addWidget(current)
    lay.addWidget(status)

    choices = [
        AppEntry("0", "0°", "Normal", "0"),
        AppEntry("180", "180°", "Flip (upside-down fix)", "↻"),
        AppEntry("90", "90°", "Rotate right", "↷"),
        AppEntry("270", "270°", "Rotate left", "↶"),
        AppEntry("reboot", "Reboot", "Press twice to confirm", "⏻"),
    ]

    def refresh() -> None:
        cur = _panel_rotation_degrees()
        labels = {e.key: e.title for e in choices if e.key != "reboot"}
        current.setText(f"Current: {labels.get(cur, cur)}")

    refresh()
    pending = {"action": None, "ts": 0.0}

    def _rotation_bin(deg: str) -> list:
        for p in (
            "/usr/local/bin/digivice-set-rotation",
            "/opt/esp-handset/display/set-panel-rotation.sh",
        ):
            if os.path.isfile(p):
                return ["sudo", "-n", p, deg]
        here = Path(__file__).resolve().parents[1] / "display" / "set-panel-rotation.sh"
        if here.is_file():
            return ["sudo", "-n", "bash", str(here), deg]
        return ["sudo", "-n", "/usr/local/bin/digivice-set-rotation", deg]

    def _power_bin(arg: str) -> list:
        for p in (
            "/usr/local/bin/digivice-power",
            "/opt/esp-handset/session/power.sh",
        ):
            if os.path.isfile(p):
                return ["sudo", "-n", p, arg]
        return ["sudo", "-n", "systemctl", "reboot"]

    def apply_deg(deg: str, label: str) -> None:
        status.setText(f"Applying {label}…")
        cmd = _rotation_bin(deg)
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                env={
                    **os.environ,
                    "PATH": "/usr/local/bin:/usr/sbin:/sbin:/usr/bin:/bin:"
                    + os.environ.get("PATH", ""),
                },
            )
            out = ((r.stdout or "") + (r.stderr or "")).strip()
            if r.returncode != 0 and "Panel rotation set" not in out:
                status.setText(
                    f"Apply exit {r.returncode}.\n"
                    f"{out[-120:] if out else 'sudo digivice-full-update once'}"
                )
            else:
                status.setText(f"Saved {deg}°. Reboot (x2) to apply.")
        except FileNotFoundError:
            status.setText("digivice-set-rotation missing — run full-update")
        except subprocess.TimeoutExpired:
            status.setText("Timed out applying rotation")
        except Exception as e:
            status.setText(f"Failed: {e}")
        refresh()

    def needs_confirm() -> bool:
        import time as _t

        now = _t.time()
        if pending["action"] == "reboot" and now - float(pending["ts"]) < 4.0:
            pending["action"] = None
            return False
        pending["action"] = "reboot"
        pending["ts"] = now
        status.setText("Confirm again within 4s")
        return True

    def do_reboot() -> None:
        if needs_confirm():
            return
        status.setText("Rebooting…")
        try:
            subprocess.Popen(
                _power_bin("reboot"),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            status.setText(f"Reboot failed: {e}")
            return
        QTimer.singleShot(2500, lambda: status.setText("Waiting for reboot…"))

    def on_pick(key: str) -> None:
        if key == "reboot":
            do_reboot()
            return
        lab = next((e.title for e in choices if e.key == key), key)
        apply_deg(key, lab)

    radial = RadialMenu(choices, body, on_activate=on_pick)
    lay.addWidget(radial, 1)
    chrome = page_chrome("Orientation", body, on_back, scroll=False)
    return chrome


def make_settings_hub(on_back, open_page: Callable[[str], None], on_linux) -> QWidget:
    from esp_handset.radial_menu import RadialMenu
    from esp_handset.shell_data import SETTINGS_APPS

    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(2, 0, 2, 0)
    entries = list(SETTINGS_APPS)

    def on_pick(key: str) -> None:
        if key == "linux":
            on_linux()
            return
        open_page(key)

    radial = RadialMenu(entries, body, on_activate=on_pick)
    lay.addWidget(radial, 1)
    return page_chrome("Settings", body, on_back, scroll=False)


def make_power_page(on_back: Callable[[], None]) -> QWidget:
    """Power off / restart. Double-press confirm (no Yes/No dialog)."""
    from PyQt5.QtCore import QTimer

    from esp_handset.radial_menu import RadialMenu
    from esp_handset.shell_data import AppEntry

    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(2, 0, 2, 0)
    lay.setSpacing(2)
    tip = QLabel("Confirm the same action twice within 4s")
    tip.setWordWrap(True)
    tip.setStyleSheet("color:#9ab;font-size:9px;")
    status = QLabel("Ready.")
    status.setWordWrap(True)
    status.setStyleSheet("font-size:10px; font-weight:700;")
    lay.addWidget(tip)
    lay.addWidget(status)

    entries = [
        AppEntry("poweroff", "Power off", "Press twice", "⏻"),
        AppEntry("reboot", "Restart", "Press twice", "↻"),
    ]
    pending = {"action": None, "ts": 0.0}
    busy = {"on": False}

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
        status.setText(f"Confirm {label} again (4s)")
        return True

    def run_power(arg: str, label: str) -> None:
        if busy["on"]:
            return
        if needs_confirm(arg):
            return
        cmd = _power_bin(arg)
        status.setText(f"{label}…")
        busy["on"] = True
        try:
            env = os.environ.copy()
            env.setdefault("PATH", "/usr/local/bin:/usr/sbin:/sbin:/usr/bin:/bin")
            subprocess.Popen(
                cmd,
                start_new_session=True,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            status.setText(f"{label} commanded.")
        except Exception as e:
            status.setText(f"Failed: {e}")
            busy["on"] = False
            return
        QTimer.singleShot(2500, lambda: status.setText(f"Waiting for {label.lower()}…"))

    def on_pick(key: str) -> None:
        if key == "poweroff":
            run_power("poweroff", "Power off")
        elif key == "reboot":
            run_power("reboot", "Restart")

    radial = RadialMenu(entries, body, on_activate=on_pick)
    lay.addWidget(radial, 1)
    return page_chrome("Power", body, on_back, scroll=False)


def make_update_page(on_back: Callable[[], None]) -> QWidget:
    """Check GitHub first (splash-style). Only pull/install if an update exists."""
    from PyQt5.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal
    import threading

    from esp_handset.boot_splash import SplashStatus, check_for_updates

    body = QWidget()
    body.setStyleSheet("background:#000;")
    lay = QVBoxLayout(body)
    lay.setContentsMargins(0, 0, 0, 4)
    lay.setSpacing(4)
    splash = SplashStatus(body)
    splash.set_line("hello ·", "checking updates")
    status = QLabel("")
    status.setWordWrap(True)
    status.setStyleSheet("color:#9ab;font-size:10px; padding:0 6px;")
    log = QTextEdit()
    log.setReadOnly(True)
    log.setMaximumHeight(72)
    log.setVisible(False)
    log.setStyleSheet(
        "font-size:8px; font-family: monospace; background:#0a0a0a; color:#8a9;"
    )
    action_btn = QPushButton("Check again")
    action_btn.setStyleSheet(
        "font-weight:700; min-height:32px; background:#1a1a1a; color:#e8eef5;"
        " border:1px solid #333; border-radius:8px;"
    )
    lay.addWidget(splash, 1)
    lay.addWidget(status)
    lay.addWidget(log)
    lay.addWidget(action_btn)

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
    phase = {"mode": "check"}  # check | ready | updating | current

    class _Bridge(QObject):
        checked = pyqtSignal(object)

    bridge = _Bridge(body)

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

    def refresh_meta() -> None:
        status.setText(f"Last: {_read_stamp()}")

    def append_out() -> None:
        data = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        if not data:
            return
        log.setVisible(True)
        log.moveCursor(QTextCursor.End)
        log.insertPlainText(data)
        log.moveCursor(QTextCursor.End)

    def restart_digivice() -> None:
        """Spawn apply (waits for us), then quit cleanly — no pkill of self."""
        if applying["on"]:
            return
        applying["on"] = True
        import shlex

        splash.set_line("applying ·", "restarting Digivice")
        status.setText("Quitting → apply staged update…")
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
            action_btn.setEnabled(True)
            return

        def _quit() -> None:
            try:
                from PyQt5.QtWidgets import QApplication

                app = QApplication.instance()
                if app is not None:
                    app.quit()
            except Exception:
                pass

        QTimer.singleShot(800, _quit)

    def on_timeout() -> None:
        if proc.state() == QProcess.NotRunning:
            return
        proc.terminate()
        action_btn.setEnabled(True)
        phase["mode"] = "ready"
        splash.set_line("timed out ·", "Digivice still running")
        status.setText("Update timed out")

    def on_finished(code: int, _st) -> None:
        watchdog.stop()
        append_out()
        refresh_meta()
        if code == 0:
            splash.set_line("staged ·", "applying…")
            QTimer.singleShot(300, restart_digivice)
        else:
            action_btn.setEnabled(True)
            phase["mode"] = "check"
            splash.set_line("update failed ·", "Confirm = try again")
            status.setText(f"Failed (exit {code})")

    def on_error(err) -> None:
        watchdog.stop()
        action_btn.setEnabled(True)
        splash.set_line("couldn't start ·", str(err)[:40])
        status.setText(f"Start error: {err}")

    proc.readyReadStandardOutput.connect(append_out)
    proc.finished.connect(on_finished)
    watchdog.timeout.connect(on_timeout)
    try:
        proc.errorOccurred.connect(on_error)
    except Exception:
        pass

    def _gui_update_bin() -> list:
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
                return "Need sudo digivice-full-update once"
        except Exception as e:
            return f"sudo check failed: {e}"
        if not os.path.isfile("/usr/local/bin/digivice-gui-update") and not os.path.isfile(
            "/opt/esp-handset/session/gui-update.sh"
        ):
            return "digivice-gui-update missing"
        return None

    def do_update() -> None:
        if proc.state() != QProcess.NotRunning or applying["on"]:
            return
        err = _preflight()
        if err:
            splash.set_line("can't update ·", err[:48])
            status.setText(err)
            action_btn.setEnabled(True)
            return
        phase["mode"] = "updating"
        log.clear()
        log.setVisible(True)
        action_btn.setEnabled(False)
        splash.set_line("updating ·", "keep Wi‑Fi on")
        status.setText("Staging (live Digivice untouched)…")
        bin_cmd = _gui_update_bin()
        prog, *argv = bin_cmd
        proc.start(prog, argv)
        if not proc.waitForStarted(5000):
            splash.set_line("couldn't start ·", "missing updater")
            action_btn.setEnabled(True)
            phase["mode"] = "check"
            return
        watchdog.start(10 * 60 * 1000)

    def on_checked(result) -> None:
        action_btn.setEnabled(True)
        st = getattr(result, "status", "error")
        detail = getattr(result, "detail", "") or ""
        if st == "available":
            phase["mode"] = "ready"
            splash.set_line("update ready ·", "Confirm = install")
            status.setText(detail)
            action_btn.setText("Install update")
        elif st == "up_to_date":
            phase["mode"] = "current"
            splash.set_line("all set ·", "up to date")
            status.setText(detail or _read_stamp())
            action_btn.setText("Check again")
        elif st == "offline":
            phase["mode"] = "check"
            splash.set_line("no signal ·", detail or "offline")
            action_btn.setText("Check again")
        else:
            phase["mode"] = "check"
            splash.set_line("ready ·", detail or "couldn't check")
            action_btn.setText("Check again")

    bridge.checked.connect(on_checked)

    def start_check() -> None:
        if proc.state() != QProcess.NotRunning or applying["on"]:
            return
        phase["mode"] = "check"
        action_btn.setEnabled(False)
        action_btn.setText("Checking…")
        splash.set_line("hello ·", "checking updates")
        status.setText("")

        def work() -> None:
            try:
                res = check_for_updates(timeout_s=8.0)
            except Exception as e:
                from esp_handset.boot_splash import UpdateCheck

                res = UpdateCheck("error", str(e)[:60])
            bridge.checked.emit(res)

        threading.Thread(target=work, name="upd-check", daemon=True).start()

    def on_action() -> None:
        if phase["mode"] == "ready":
            do_update()
            return
        start_check()

    action_btn.clicked.connect(on_action)

    chrome = page_chrome("Update", body, on_back, scroll=False)

    def on_page_show() -> None:
        if proc.state() != QProcess.NotRunning or applying["on"]:
            return
        if phase["mode"] in ("updating", "ready"):
            return
        QTimer.singleShot(80, start_check)

    chrome.on_page_show = on_page_show  # type: ignore[attr-defined]
    chrome.digi_activate = lambda: (on_action(), True)[1]  # type: ignore[attr-defined]
    return chrome


def make_mouse_page(on_back: Callable[[], None]) -> QWidget:
    """Desktop d-pad mouse speed (buttons daemon reads ~/.esp-handset/mouse_step)."""
    from esp_handset.radial_menu import RadialMenu
    from esp_handset.shell_data import AppEntry

    PRESETS = [
        ("very_slow", "Very slow", 3),
        ("slow", "Slow", 6),
        ("normal", "Normal", 10),
        ("fast", "Fast", 16),
        ("turbo", "Turbo", 24),
    ]
    step_path = DATA / "mouse_step"
    etc_path = Path("/etc/esp-handset/mouse_step")

    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(2, 0, 2, 0)
    tip = QLabel("Desktop pointer speed · Confirm to set")
    tip.setWordWrap(True)
    tip.setStyleSheet("color:#9ab;font-size:9px;")
    cur = QLabel("")
    cur.setStyleSheet("font-size:10px; font-weight:700;")
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
        for _k, name, n in PRESETS:
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

    entries = [
        AppEntry(key, name, f"step {n}", str(n) if n < 10 else "»")
        for key, name, n in PRESETS
    ]
    steps = {key: n for key, _name, n in PRESETS}

    def on_pick(key: str) -> None:
        if key in steps:
            set_step(steps[key])

    radial = RadialMenu(entries, body, on_activate=on_pick)
    # Start on current preset when possible
    v = _read_step()
    for i, (_k, _name, n) in enumerate(PRESETS):
        if n == v:
            radial.set_entries(entries, i)
            break
    lay.addWidget(radial, 1)
    refresh()
    return page_chrome("Mouse speed", body, on_back, scroll=False)


def make_debug_notifs_page(
    on_back: Callable[[], None],
    *,
    show_toast: Optional[Callable[[str, str, str], None]] = None,
    show_incoming: Optional[Callable[..., None]] = None,
) -> QWidget:
    """Debug → Alerts: fire test toasts and incoming-call takeover."""
    from PyQt5.QtWidgets import QSizePolicy

    from esp_handset import store

    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(4, 2, 4, 2)
    lay.setSpacing(4)
    status = QLabel("Test alerts")
    status.setAlignment(Qt.AlignCenter)
    status.setWordWrap(True)
    status.setFixedHeight(36)
    status.setStyleSheet(
        "font-size:12px; font-weight:700; color:#fff; background:#152030; padding:4px;"
    )
    lay.addWidget(status)

    def _btn(text: str) -> QPushButton:
        b = QPushButton(text)
        b.setFixedHeight(36)
        b.setStyleSheet("font-size:13px; font-weight:700;")
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return b

    sms_btn = _btn("Test SMS toast")
    lora_btn = _btn("Test LoRa toast")
    call_btn = _btn("Test call (unknown)")
    call_known_btn = _btn("Test call (contact)")
    lay.addWidget(sms_btn)
    lay.addWidget(lora_btn)
    lay.addWidget(call_btn)
    lay.addWidget(call_known_btn)
    tip = QLabel("Confirm=Answer · Back=Decline · ←→ switch")
    tip.setWordWrap(True)
    tip.setStyleSheet("color:#9ab;font-size:9px;")
    lay.addWidget(tip)
    lay.addStretch(1)

    def _toast(title: str, body: str, kind: str) -> None:
        store.push_notif(title, body, kind)
        status.setText(f"Toast: {title}")

    def do_sms() -> None:
        _toast("SMS", "+15551212: Test message from Debug", "sms")

    def do_lora() -> None:
        _toast("LoRa", "mesh-peer: hello from Debug", "lora")

    def _fire_call(number: str, name: str = "") -> None:
        if not callable(show_incoming):
            status.setText("Incoming overlay not wired")
            return
        status.setText("Incoming call UI…")

        def answered() -> None:
            status.setText("Answered (debug)")
            store.push_notif("Call", "Answered test call", "call")

        def declined() -> None:
            status.setText("Declined (debug)")
            store.push_notif("Call", "Declined test call", "call")

        show_incoming(
            number,
            name=name,
            on_answer=answered,
            on_decline=declined,
            subtitle="",
        )

    def do_call_unknown() -> None:
        _fire_call("+1 555 0199")

    def do_call_known() -> None:
        from esp_handset.pages import _contact_photo_file, _load_contacts

        contacts = _load_contacts()
        if not contacts:
            status.setText("No contacts — add one first")
            return
        c = contacts[0]
        phone = str(c.get("phone") or "")
        if not phone:
            status.setText("First contact has no phone")
            return
        photo = _contact_photo_file(c)
        if not callable(show_incoming):
            status.setText("Incoming overlay not wired")
            return
        status.setText("Incoming call UI…")

        def answered() -> None:
            status.setText("Answered (debug)")
            store.push_notif("Call", "Answered test call", "call")

        def declined() -> None:
            status.setText("Declined (debug)")
            store.push_notif("Call", "Declined test call", "call")

        show_incoming(
            phone,
            name=str(c.get("name") or ""),
            photo=str(photo) if photo else None,
            on_answer=answered,
            on_decline=declined,
            subtitle="",
        )

    sms_btn.clicked.connect(do_sms)
    lora_btn.clicked.connect(do_lora)
    call_btn.clicked.connect(do_call_unknown)
    call_known_btn.clicked.connect(do_call_known)
    return page_chrome("Debug · Alerts", body, on_back, scroll=False)


def make_debug_page(on_back: Callable[[], None]) -> QWidget:
    """Digivice Debug → Sound — beep, mic, USB, profile."""
    import struct
    import threading
    import wave
    from shutil import which

    from PyQt5.QtCore import QProcess, QTimer
    from PyQt5.QtWidgets import QSizePolicy

    from esp_handset import store
    from esp_handset.audio_out import AUDIO_BUILD

    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(4, 2, 4, 2)
    lay.setSpacing(4)

    prefs = store.load("sounds.json", {"profile": "Normal", "enabled": True})
    profiles = ["Silent", "Normal", "Loud", "Outdoor"]
    pref_state = {
        "profile": prefs.get("profile", "Normal"),
        "enabled": bool(prefs.get("enabled", True)),
    }
    if pref_state["profile"] not in profiles:
        pref_state["profile"] = "Normal"

    status = QLabel("Tap BEEP")
    status.setAlignment(Qt.AlignCenter)
    status.setWordWrap(True)
    status.setFixedHeight(44)
    status.setStyleSheet(
        "font-size:14px; font-weight:700; color:#fff;"
        "background:#152030; padding:4px;"
    )
    lay.addWidget(status)

    def _badge(title: str) -> QLabel:
        lab = QLabel(f"{title}\n—")
        lab.setAlignment(Qt.AlignCenter)
        lab.setFixedHeight(40)
        lab.setStyleSheet(
            "font-size:13px; font-weight:700;"
            "background:#1a2230; color:#cde;"
        )
        return lab

    spk_badge = _badge("SPK")
    mic_badge = _badge("MIC")
    badges = QHBoxLayout()
    badges.setSpacing(4)
    badges.addWidget(spk_badge, 1)
    badges.addWidget(mic_badge, 1)
    lay.addLayout(badges)

    def _big_btn(text: str) -> QPushButton:
        b = QPushButton(text)
        b.setFixedHeight(40)
        b.setStyleSheet("font-size:15px; font-weight:700;")
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return b

    spk_btn = _big_btn("BEEP")
    mic_btn = _big_btn("MIC")
    lay.addWidget(spk_btn)
    lay.addWidget(mic_btn)

    off = " · OFF" if not pref_state["enabled"] else ""
    sound_btn = QPushButton(f"Sound: {pref_state['profile']}{off}")
    sound_btn.setFixedHeight(28)
    sound_btn.setStyleSheet("font-size:11px;")
    lay.addWidget(sound_btn)

    wake_btn = QPushButton("FIX USB")
    wake_btn.setFixedHeight(32)
    wake_btn.setStyleSheet("font-size:13px; font-weight:700;")
    lay.addWidget(wake_btn)

    piezo_btn = QPushButton("PIEZO (GPIO)")
    piezo_btn.setFixedHeight(32)
    piezo_btn.setStyleSheet("font-size:13px; font-weight:700;")
    lay.addWidget(piezo_btn)

    yes_btn = _big_btn("YES")
    no_btn = _big_btn("NO")
    yes_btn.setStyleSheet("font-size:15px; font-weight:700; background:#1a5a2a;")
    no_btn.setStyleSheet("font-size:15px; font-weight:700; background:#5a1a1a;")
    hear = QHBoxLayout()
    hear.setSpacing(4)
    hear.addWidget(yes_btn, 1)
    hear.addWidget(no_btn, 1)
    lay.addLayout(hear)
    yes_btn.hide()
    no_btn.hide()

    tip = QLabel(f"{AUDIO_BUILD} · green=out · piezo pin 15")
    tip.setAlignment(Qt.AlignCenter)
    tip.setStyleSheet("font-size:10px; color:#789;")
    lay.addWidget(tip)
    lay.addStretch(1)

    procs: list = []
    test_wav = DATA / "debug_mic_test.wav"
    busy = {"on": False}
    pending = {"kind": None}
    state = {"spk_dev": False, "mic_dev": False, "spk": "?", "mic": "?"}

    def _which(name: str) -> Optional[str]:
        return which(name)

    def _set_status(msg: str) -> None:
        status.setText((msg or "")[:42])

    def _set_badge(lab: QLabel, title: str, verdict: str) -> None:
        colors = {
            "ok": ("#0d3d1f", "#7dffa0", "PASS"),
            "bad": ("#4a1010", "#ff8a8a", "FAIL"),
            "none": ("#3a2a10", "#ffcc66", "NONE"),
            "wait": ("#1a2230", "#cde", "…"),
            "ask": ("#1a3040", "#9cf", "?"),
            "?": ("#1a2230", "#cde", "—"),
        }
        bg, fg, word = colors.get(verdict, colors["?"])
        lab.setText(f"{title}\n{word}")
        lab.setStyleSheet(
            f"font-size:13px; font-weight:700;"
            f"background:{bg}; color:{fg}; border:1px solid {fg};"
        )

    def _kill_all() -> None:
        for p in list(procs):
            try:
                if isinstance(p, QProcess) and p.state() != QProcess.NotRunning:
                    p.kill()
                    p.waitForFinished(800)
            except Exception:
                pass
        procs.clear()

    def _set_busy(on: bool) -> None:
        busy["on"] = on
        spk_btn.setEnabled(not on)
        mic_btn.setEnabled(not on)
        sound_btn.setEnabled(not on)
        wake_btn.setEnabled(not on)

    def do_wake() -> None:
        if busy["on"]:
            return
        _set_busy(True)
        _set_status("Fixing USB…")

        from PyQt5.QtCore import QObject, pyqtSignal

        from esp_handset.audio_out import software_wake

        class _W(QObject):
            done = pyqtSignal(str)

        sig = getattr(body, "_wake_sig", None)
        if sig is None:
            sig = _W(body)
            body._wake_sig = sig

            def _done(msg: str) -> None:
                _set_busy(False)
                _set_status(msg)
                scan_hw()

            sig.done.connect(_done)

        def _work() -> None:
            try:
                software_wake()
                sig.done.emit("USB wake done")
            except Exception as e:
                sig.done.emit(str(e)[:40])

        threading.Thread(target=_work, daemon=True).start()

    def _ask_heard(kind: str) -> None:
        pending["kind"] = kind
        yes_btn.show()
        no_btn.show()
        yes_btn.setEnabled(True)
        no_btn.setEnabled(True)
        if kind == "speaker":
            _set_badge(spk_badge, "SPK", "ask")
            _set_status("Heard beep? YES / NO")
        else:
            _set_badge(mic_badge, "MIC", "ask")
            _set_status("Heard voice? YES / NO")

    def _clear_ask() -> None:
        pending["kind"] = None
        yes_btn.hide()
        no_btn.hide()
        yes_btn.setEnabled(False)
        no_btn.setEnabled(False)

    def on_yes() -> None:
        kind = pending.get("kind")
        _clear_ask()
        if kind == "speaker":
            state["spk"] = "ok"
            _set_badge(spk_badge, "SPK", "ok")
            _set_status("Speaker PASS")
        elif kind == "mic":
            state["mic"] = "ok"
            _set_badge(mic_badge, "MIC", "ok")
            _set_status("Mic PASS")

    def on_no() -> None:
        kind = pending.get("kind")
        _clear_ask()
        if kind == "speaker":
            state["spk"] = "bad"
            _set_badge(spk_badge, "SPK", "bad")
            _set_status("Speaker FAIL")
        elif kind == "mic":
            state["mic"] = "bad"
            _set_badge(mic_badge, "MIC", "bad")
            _set_status("Mic FAIL")

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
        if play_n <= 0 and cap_n <= 0:
            _set_status("No USB audio")
            _set_badge(spk_badge, "SPK", "none")
            _set_badge(mic_badge, "MIC", "none")
        else:
            tip.setText(f"{AUDIO_BUILD} · cards {play_n}/{cap_n}")

    def _wav_level(path: Path) -> tuple:
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
            return peak, 0.0
        except Exception:
            return 0.0, 0.0

    def cycle_sound() -> None:
        i = profiles.index(pref_state["profile"])
        i = (i + 1) % len(profiles)
        pref_state["profile"] = profiles[i]
        pref_state["enabled"] = pref_state["profile"] != "Silent"
        store.save(
            "sounds.json",
            {"profile": pref_state["profile"], "enabled": pref_state["enabled"]},
        )
        off2 = " · OFF" if not pref_state["enabled"] else ""
        sound_btn.setText(f"Sound: {pref_state['profile']}{off2}")
        _set_status(f"Saved {pref_state['profile']}")

    def speaker_test() -> None:
        if busy["on"]:
            return
        _clear_ask()
        if not state["spk_dev"] and _count_cards("aplay") == 0:
            _set_badge(spk_badge, "SPK", "none")
            _set_status("No playback device")
            return
        _set_busy(True)
        _set_badge(spk_badge, "SPK", "wait")
        _set_status("LOUD 5s — listen!")

        from PyQt5.QtCore import QObject, pyqtSignal

        from esp_handset.audio_out import play_test_tone_detail

        class _Sig(QObject):
            done = pyqtSignal(bool, str)

        sig = getattr(body, "_beep_sig", None)
        if sig is None:
            sig = _Sig(body)
            body._beep_sig = sig

            def _on_done(ok: bool, msg: str) -> None:
                _set_busy(False)
                short = (msg or "").replace("\n", " ")
                if not ok:
                    _set_status("Beep FAIL")
                else:
                    _set_status("Done — heard it?")
                tip.setText(short[:36])
                _ask_heard("speaker")

            sig.done.connect(_on_done)

        def _work() -> None:
            try:
                ok, msg = play_test_tone_detail(seconds=5.0)
            except Exception as e:
                ok, msg = False, str(e)[:40]
            sig.done.emit(ok, msg)

        threading.Thread(target=_work, daemon=True).start()

    def mic_test() -> None:
        if busy["on"]:
            return
        _clear_ask()
        if not _which("arecord"):
            _set_status("arecord missing")
            return
        if not state["mic_dev"] and _count_cards("arecord") == 0:
            _set_badge(mic_badge, "MIC", "none")
            _set_status("No mic device")
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
        _set_status("Speak now (3s)")
        card = "0"
        try:
            from esp_handset.audio_out import _usb_card as _live_card

            card = _live_card() or "0"
        except Exception:
            try:
                saved = Path("/etc/esp-handset/alsa-card").read_text().strip()
                if saved.isdigit():
                    card = saved
            except OSError:
                pass
        rec = _run_cmd(
            [
                "arecord",
                "-D",
                f"plughw:{card},0",
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
            peak, _rms = _wav_level(test_wav)
            pct = int(peak * 100)
            if peak < 0.02:
                _set_busy(False)
                state["mic"] = "bad"
                _set_badge(mic_badge, "MIC", "bad")
                _set_status(f"Mic quiet {pct}%")
                return
            play_cmd = None
            if _which("pasuspender") and _which("aplay"):
                play_cmd = [
                    "pasuspender",
                    "--",
                    "aplay",
                    "-D",
                    f"plughw:{card},0",
                    str(test_wav),
                ]
            elif _which("aplay"):
                play_cmd = ["aplay", "-D", f"plughw:{card},0", str(test_wav)]
            if not play_cmd:
                _set_busy(False)
                state["mic"] = "ok"
                _set_badge(mic_badge, "MIC", "ok")
                _set_status(f"Mic {pct}% OK")
                return
            _set_status("Playing mic…")
            play = _run_cmd(play_cmd, timeout_ms=8000)

            def _after_play(_c=0, _s=None) -> None:
                _set_busy(False)
                _ask_heard("mic")

            play.finished.connect(_after_play)

        rec.finished.connect(_after_rec)

    def piezo_test() -> None:
        if busy["on"]:
            return
        _clear_ask()
        _set_status("Piezo pin 15…")
        try:
            from esp_handset.buzzer import alert, available, status as bstatus
            from esp_handset.hw_pins import BUZZER_BCM

            if BUZZER_BCM is None:
                _set_status("Piezo disabled in config")
                return
            if not available():
                _set_status(bstatus()[:48])
                return
            ok = alert(force=True)
            if ok:
                _set_status("Piezo beeped · " + bstatus())
            else:
                _set_status("No tone · " + bstatus())
        except Exception as e:
            _set_status(str(e)[:48])

    sound_btn.clicked.connect(cycle_sound)
    wake_btn.clicked.connect(do_wake)
    piezo_btn.clicked.connect(piezo_test)
    spk_btn.clicked.connect(speaker_test)
    mic_btn.clicked.connect(mic_test)
    yes_btn.clicked.connect(on_yes)
    no_btn.clicked.connect(on_no)
    QTimer.singleShot(150, scan_hw)
    return page_chrome("Debug · Sound", body, on_back, scroll=False)

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
        "Type with CardKB or Bluetooth keyboard\n"
        "Back → previous screen\n"
        "Back×3 on Digivice home → desktop\n"
        "Home → Digivice home (never desktop)\n"
        "F12 / F10 / Ctrl+Q → desktop\n"
        "Settings → Linux → Exit\n"
        "Settings → Update → software only\n"
        "Settings → Mouse → desktop pointer speed\n"
        "Settings → Screen → orientation / flip\n"
        "Settings → Debug → Beep / mic\n"
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
    from pathlib import Path

    body = QWidget()
    body.setStyleSheet("background:#0e1620; color:#e8eef5;")
    lay = QVBoxLayout(body)
    lay.setContentsMargins(6, 4, 6, 6)
    lay.setSpacing(6)
    title = QLabel("Network")
    title.setStyleSheet("font-size:15px; font-weight:700;")
    tip = QLabel("SIM7600 modem · Wi‑Fi is system-managed")
    tip.setWordWrap(True)
    tip.setStyleSheet("font-size:10px; color:#7a8a9a;")
    lay.addWidget(title)
    lay.addWidget(tip)
    lab = QLabel("Tap refresh for modem")
    lab.setWordWrap(True)
    lab.setStyleSheet(
        "font-size:11px; padding:8px; background:#16202c; border-radius:8px;"
    )
    _btn_ss = (
        "QPushButton { font-size:12px; font-weight:700; padding:6px;"
        " background:#1e2a38; color:#e8eef5; border:1px solid #243040;"
        " border-radius:10px; }"
        'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
    )
    btn = QPushButton("Refresh status")
    scan = QPushButton("Scan ports")
    recon = QPushButton("Reconnect modem")
    uart_btn = QPushButton("Use GPIO UART")
    for b in (btn, scan, recon, uart_btn):
        b.setMinimumHeight(32)
        b.setStyleSheet(_btn_ss)
    recon.setStyleSheet(
        "QPushButton { font-size:12px; font-weight:700; color:#0a1218;"
        " background:#5ec4a8; border:none; border-radius:10px; }"
        'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
    )
    lay.addWidget(lab)
    lay.addWidget(btn)
    lay.addWidget(scan)
    lay.addWidget(recon)
    lay.addWidget(uart_btn)
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

    def do_uart_mode():
        import subprocess

        lab.setText("Setting GPIO UART mode…")
        try:
            subprocess.run(
                ["sudo", "-n", "digivice-modem-uart"],
                timeout=15,
                check=False,
                capture_output=True,
            )
        except Exception:
            try:
                Path("/etc/esp-handset").mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            try:
                Path("/etc/esp-handset/modem-backend").write_text(
                    "uart\n", encoding="utf-8"
                )
            except OSError:
                lab.setText(
                    "Need: sudo digivice-modem-uart\n"
                    "or: echo uart | sudo tee /etc/esp-handset/modem-backend"
                )
                return
        do_reconnect()

    def do_reconnect():
        from esp_handset.sim7600 import Sim7600

        lab.setText("Connecting…\nUSB + GPIO UART")
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
    uart_btn.clicked.connect(do_uart_mode)
    refresh()
    return page_chrome("Network", body, on_back)
