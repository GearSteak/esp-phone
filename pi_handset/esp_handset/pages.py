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
    """Alphabetized contact list; ＋ Add stays under the list and moves down as you add."""
    from PyQt5.QtWidgets import QSizePolicy

    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(4)

    # Growing stack of contact rows — Maximum height so empty viewport
    # space is NOT between the list and Add (that was the "dead space").
    list_wrap = QWidget()
    list_wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
    list_lay = QVBoxLayout(list_wrap)
    list_lay.setContentsMargins(0, 0, 0, 0)
    list_lay.setSpacing(2)
    lay.addWidget(list_wrap, 0)

    add_btn = QPushButton("＋ Add contact")
    add_btn.setStyleSheet("font-weight:700; min-height:28px;")
    add_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    lay.addWidget(add_btn, 0)

    # Inline add form (shown under Add; stays at bottom of scroll content)
    form = QWidget()
    form.setVisible(False)
    form.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
    form_lay = QVBoxLayout(form)
    form_lay.setContentsMargins(0, 4, 0, 0)
    form_lay.setSpacing(4)
    name_ed = QLineEdit()
    name_ed.setPlaceholderText("Name")
    num_ed = QLineEdit()
    num_ed.setPlaceholderText("Number")
    row = QHBoxLayout()
    save_btn = QPushButton("Save")
    save_btn.setStyleSheet("font-weight:700;")
    cancel_btn = QPushButton("Cancel")
    row.addWidget(save_btn, 1)
    row.addWidget(cancel_btn, 1)
    form_lay.addWidget(name_ed)
    form_lay.addWidget(num_ed)
    form_lay.addLayout(row)
    lay.addWidget(form, 0)
    # Spare vertical room goes *below* Add, not between list and Add
    lay.addStretch(1)

    def _sort_key(c: dict):
        n = str(c.get("name") or "").strip()
        num = str(c.get("number") or "").strip()
        return (n.casefold() or num.casefold(), num)

    def _clear_list() -> None:
        while list_lay.count():
            item = list_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def refresh() -> None:
        _clear_list()
        raw = _load_json(CONTACTS, [])
        if not isinstance(raw, list):
            raw = []
        contacts = sorted(
            [c for c in raw if isinstance(c, dict) and c.get("number")],
            key=_sort_key,
        )
        # Persist sorted order so file stays alphabetical
        if contacts != raw:
            _save_json(CONTACTS, contacts)

        if not contacts:
            empty = QLabel("No contacts yet.")
            empty.setStyleSheet("color:#678;font-size:11px;")
            list_lay.addWidget(empty)

        last_letter = ""
        for c in contacts:
            name = str(c.get("name") or "").strip() or str(c.get("number") or "")
            number = str(c.get("number") or "").strip()
            letter = name[:1].upper() if name else "#"
            if not letter.isalpha():
                letter = "#"
            if letter != last_letter:
                hdr = QLabel(letter)
                hdr.setStyleSheet(
                    "color:#ffd700;font-size:11px;font-weight:700;"
                    "padding:2px 2px 0 2px;"
                )
                hdr.setFocusPolicy(Qt.NoFocus)
                list_lay.addWidget(hdr)
                last_letter = letter

            label = f"{name}  ·  {number}" if name != number else number
            btn = QPushButton(label)
            btn.setStyleSheet(
                "text-align:left; padding:5px 6px; min-height:24px;"
            )
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            num_capture = number

            def _dial(_checked=False, n=num_capture) -> None:
                if n:
                    open_dial(n)

            btn.clicked.connect(_dial)
            list_lay.addWidget(btn)

        body._contacts = contacts  # type: ignore[attr-defined]
        add_btn.raise_()

    def show_form() -> None:
        form.setVisible(True)
        add_btn.setVisible(False)
        name_ed.clear()
        num_ed.clear()
        name_ed.setFocus(Qt.OtherFocusReason)
        try:
            from esp_handset import digi_nav

            digi_nav.clear_highlights(body)
            digi_nav._highlight(name_ed, True)
        except Exception:
            pass

    def hide_form() -> None:
        form.setVisible(False)
        add_btn.setVisible(True)
        name_ed.clear()
        num_ed.clear()

    def do_save() -> None:
        n = name_ed.text().strip()
        number = num_ed.text().strip()
        if not number:
            num_ed.setFocus(Qt.OtherFocusReason)
            return
        contacts = _load_json(CONTACTS, [])
        if not isinstance(contacts, list):
            contacts = []
        contacts.append({"name": n or number, "number": number})
        contacts = sorted(
            [c for c in contacts if isinstance(c, dict) and c.get("number")],
            key=_sort_key,
        )
        _save_json(CONTACTS, contacts)
        hide_form()
        refresh()

    add_btn.clicked.connect(show_form)
    save_btn.clicked.connect(do_save)
    cancel_btn.clicked.connect(hide_form)
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
    """One button: git pull → install to /opt → restart Digivice.

    Software-only (no SPI/boot). Updater must not kill this UI mid-run;
    we restart only after a verified success exit code.
    """
    from PyQt5.QtCore import QProcess, QProcessEnvironment, QTimer

    body = QWidget()
    lay = QVBoxLayout(body)
    tip = QLabel(
        "Software only: pull → stage → restart.\n"
        "Does not overwrite Digivice while it is running."
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
    proc.setProcessEnvironment(env)

    watchdog = QTimer(body)
    watchdog.setSingleShot(True)

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
        """Exit UI, then apply staged /opt swap + safe relaunch."""
        import shlex
        import sys

        status.setText("Applying update & restarting…")
        log.append("\n--- exit → apply staged update ---\n")
        env2 = os.environ.copy()
        env2.setdefault("DISPLAY", ":0")
        home = str(Path.home())
        log_path = str(DATA / "apply-update.log")
        DATA.mkdir(parents=True, exist_ok=True)

        apply = None
        for p in (
            "/usr/local/bin/digivice-apply-update",
            "/opt/esp-handset/session/apply-update.sh",
            str(Path(__file__).resolve().parents[1] / "session" / "apply-update.sh"),
        ):
            if os.path.isfile(p):
                apply = p
                break
        # Prefer apply script from git repo (just pulled)
        try:
            rp = Path("/etc/esp-handset/repo.path")
            if rp.is_file():
                repo = rp.read_text(encoding="utf-8").strip()
                cand = Path(repo) / "pi_handset" / "session" / "apply-update.sh"
                if cand.is_file():
                    apply = str(cand)
        except OSError:
            pass
        for d in (Path.home() / "esp-phone",):
            cand = d / "pi_handset" / "session" / "apply-update.sh"
            if cand.is_file():
                apply = str(cand)
                break

        qlog = shlex.quote(log_path)
        if apply:
            qapply = shlex.quote(apply)
            script = (
                f"exec >>{qlog} 2>&1; "
                "echo \"=== apply $(date -Iseconds) ===\"; "
                "sleep 1.2; "
                f"sudo -n bash {qapply} || bash {qapply}; "
            )
        else:
            # Last resort: home relaunch only (no swap)
            script = (
                f"exec >>{qlog} 2>&1; "
                "sleep 1.2; "
                "digivice-home-relaunch || handset-phone || true; "
            )
        try:
            subprocess.Popen(
                ["bash", "-c", script],
                start_new_session=True,
                env=env2,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            status.setText(f"Apply spawn failed: {e}")
            update_btn.setEnabled(True)
            return
        # Clean exit — do NOT pkill ourselves (that raced SPI / crashed Pi Zero)
        def _quit() -> None:
            try:
                from PyQt5.QtWidgets import QApplication

                app = QApplication.instance()
                if app is not None:
                    app.quit()
            except Exception:
                pass
            sys.exit(0)

        QTimer.singleShot(400, _quit)

    def on_timeout() -> None:
        if proc.state() == QProcess.NotRunning:
            return
        log.append("\n--- TIMEOUT (10 min) — killing updater ---\n")
        proc.kill()
        update_btn.setEnabled(True)
        status.setText("Timed out — Digivice still running")

    def on_finished(code: int, _st) -> None:
        watchdog.stop()
        append_out()
        refresh_meta()
        if code == 0:
            status.setText("Staged. Restarting safely…")
            log.append("\n--- OK — applying after exit ---\n")
            QTimer.singleShot(500, restart_digivice)
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

    def _repo_gui_update() -> Optional[str]:
        """Prefer freshly pulled repo script so Settings Update self-heals."""
        candidates = []
        try:
            rp = Path("/etc/esp-handset/repo.path")
            if rp.is_file():
                candidates.append(
                    Path(rp.read_text(encoding="utf-8").strip())
                    / "pi_handset"
                    / "session"
                    / "gui-update.sh"
                )
        except OSError:
            pass
        candidates.append(Path.home() / "esp-phone" / "pi_handset" / "session" / "gui-update.sh")
        candidates.append(
            Path(__file__).resolve().parents[1] / "session" / "gui-update.sh"
        )
        for c in candidates:
            if c.is_file():
                return str(c)
        return None

    def _gui_update_bin() -> list:
        # 1) Repo copy (after user git pull below)
        repo_script = _repo_gui_update()
        if repo_script:
            return ["sudo", "-n", "bash", repo_script]
        for p in (
            "/usr/local/bin/digivice-gui-update",
            "/opt/esp-handset/session/gui-update.sh",
        ):
            if os.path.isfile(p):
                return ["sudo", "-n", p]
        return ["sudo", "-n", "/usr/local/bin/digivice-gui-update"]

    def _preflight() -> Optional[str]:
        """Return error string if update cannot run safely."""
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
        return None

    def _user_git_pull() -> None:
        """Pull into ~/esp-phone first so we can run the NEW gui-update.sh."""
        repo = None
        try:
            rp = Path("/etc/esp-handset/repo.path")
            if rp.is_file():
                repo = rp.read_text(encoding="utf-8").strip()
        except OSError:
            repo = None
        if not repo or not Path(repo, ".git").is_dir():
            for d in (Path.home() / "esp-phone", Path.home() / "esp phone"):
                if (d / ".git").is_dir():
                    repo = str(d)
                    break
        if not repo:
            log.append("(no local git repo for pre-pull)\n")
            return
        log.append(f"$ git -C {repo} pull\n")
        try:
            r = subprocess.run(
                ["git", "-C", repo, "fetch", "--prune", "origin", "main"],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            log.append((r.stdout or "") + (r.stderr or ""))
            r2 = subprocess.run(
                ["git", "-C", repo, "reset", "--hard", "origin/main"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            log.append((r2.stdout or "") + (r2.stderr or "") + "\n")
        except Exception as e:
            log.append(f"pre-pull: {e}\n")

    def do_update() -> None:
        if proc.state() != QProcess.NotRunning:
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
        status.setText("Pulling GitHub scripts…")
        update_btn.setEnabled(False)
        _user_git_pull()
        bin_cmd = _gui_update_bin()
        status.setText("Staging install (live Digivice untouched)…")
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
