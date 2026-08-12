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

    # Growing stack of contact rows (not a fixed viewport list)
    list_wrap = QWidget()
    list_lay = QVBoxLayout(list_wrap)
    list_lay.setContentsMargins(0, 0, 0, 0)
    list_lay.setSpacing(3)
    lay.addWidget(list_wrap)

    add_btn = QPushButton("＋ Add contact")
    add_btn.setStyleSheet("font-weight:700; min-height:32px;")
    lay.addWidget(add_btn)

    # Inline add form (shown under Add; stays at bottom of scroll content)
    form = QWidget()
    form.setVisible(False)
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
    lay.addWidget(form)

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
                    "padding:4px 2px 0 2px;"
                )
                hdr.setFocusPolicy(Qt.NoFocus)
                list_lay.addWidget(hdr)
                last_letter = letter

            label = f"{name}  ·  {number}" if name != number else number
            btn = QPushButton(label)
            btn.setStyleSheet(
                "text-align:left; padding:8px 8px; min-height:30px;"
            )
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            num_capture = number

            def _dial(_checked=False, n=num_capture) -> None:
                if n:
                    open_dial(n)

            btn.clicked.connect(_dial)
            list_lay.addWidget(btn)

        body._contacts = contacts  # type: ignore[attr-defined]
        # Keep Add under the list in the scroll content
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

    No Yes/No dialogs (hard buttons can't confirm them).
    Updater must not kill this UI mid-run; we restart only after success.
    """
    from PyQt5.QtCore import QProcess, QProcessEnvironment, QTimer

    body = QWidget()
    lay = QVBoxLayout(body)
    tip = QLabel(
        "One press: check GitHub, install, restart Digivice."
    )
    tip.setWordWrap(True)
    tip.setStyleSheet("color:#9ab;font-size:10px;")
    status = QLabel("Ready.")
    status.setWordWrap(True)
    log = QTextEdit()
    log.setReadOnly(True)
    log.setMinimumHeight(120)
    log.setStyleSheet("font-size:9px; font-family: monospace;")
    update_btn = QPushButton("Update Digivice")
    update_btn.setStyleSheet("font-weight:700; min-height:36px;")
    lay.addWidget(tip)
    lay.addWidget(status)
    lay.addWidget(log, 1)
    lay.addWidget(update_btn)

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

    def restart_digivice() -> None:
        status.setText("Restarting Digivice…")
        log.append("\n--- restarting ---\n")
        env2 = os.environ.copy()
        env2.setdefault("DISPLAY", ":0")
        try:
            subprocess.Popen(
                [
                    "bash",
                    "-c",
                    "sleep 0.6; "
                    "pkill -f handset_app.py 2>/dev/null || true; "
                    "sleep 0.3; "
                    "/usr/local/bin/handset-phone || handset-phone || true",
                ],
                start_new_session=True,
                env=env2,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            status.setText(f"Restart failed: {e}")
            update_btn.setEnabled(True)
            return
        QTimer.singleShot(400, lambda: os._exit(0))

    def on_finished(code: int, _st) -> None:
        append_out()
        if code == 0:
            status.setText("Installed. Restarting…")
            log.append("\n--- OK — restarting Digivice ---\n")
            # brief pause so last log lines paint before we exit
            QTimer.singleShot(700, restart_digivice)
        else:
            update_btn.setEnabled(True)
            status.setText(f"Failed (exit {code})")
            log.append(
                "\n--- FAILED ---\n"
                "If sudo denied, seed once from HDMI terminal:\n"
                "  sudo digivice-full-update\n"
            )

    def on_error(err) -> None:
        update_btn.setEnabled(True)
        status.setText(f"Start error: {err}")
        log.append(f"\nQProcess error: {err}\n")

    proc.readyReadStandardOutput.connect(append_out)
    proc.finished.connect(on_finished)
    try:
        proc.errorOccurred.connect(on_error)
    except Exception:
        pass

    def do_update() -> None:
        if proc.state() != QProcess.NotRunning:
            status.setText("Already running…")
            return
        bin_cmd = _gui_update_bin()
        log.clear()
        status.setText("Checking GitHub → install…")
        update_btn.setEnabled(False)
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

    update_btn.clicked.connect(do_update)
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
        "Home → Digivice home (never desktop)\n"
        "F12 / F10 / Ctrl+Q → desktop\n"
        "Settings → Linux → Exit\n"
        "Settings → Update → download\n"
        "Settings → Power → Off/Restart (x2)\n"
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
