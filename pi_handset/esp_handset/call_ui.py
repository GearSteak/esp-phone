"""Active-call takeover UI + outbound call controller + call log page."""
from __future__ import annotations

import re
import time
import threading
from typing import Callable, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from esp_handset import call_log as clog
from esp_handset import sip_call
from esp_handset.incoming_call import _CircleAction
from esp_handset.pages import page_chrome


def _screen_detail(msg: str, *, max_chars: int = 72) -> str:
    """Fit failure text on the 240px call overlay."""
    s = re.sub(r"\s+", " ", (msg or "").strip())
    if not s:
        return ""
    # Prefer short known phrases
    low = s.lower()
    if "balance" in low or "402" in low:
        return "Add Zadarma balance"
    if "locked" in low or "blocked for incorrect" in low:
        return "SIP locked — wait / support"
    if "403" in low:
        return "Call blocked (403)"
    if "404" in low or "bad number" in low:
        return "Bad number"
    if "not registered" in low:
        return "SIP not registered"
    if "no ringback" in low or "no call progress" in low:
        return "No ringback"
    if "dropped before" in low:
        return "Dropped before ring"
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1] + "…"


class CallOverlay(QWidget):
    """Fullscreen call UI: ringing / in-call / ended (outbound + shared hangup)."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._on_hangup: Optional[Callable[[], None]] = None
        self._on_dismiss: Optional[Callable[[], None]] = None
        self._mode = "idle"  # ringing | active | ended
        self.setObjectName("activeCall")
        self.setStyleSheet(
            """
            #activeCall { background: #000000; }
            QLabel { background: transparent; border: none; }
            QLabel#acLabel { color: #aeaeb2; font-size: 10px; font-weight: 600; }
            QLabel#acName { color: #ffffff; font-size: 18px; font-weight: 800; }
            QLabel#acNumber { color: #d1d1d6; font-size: 12px; font-weight: 600; }
            QLabel#acTimer { color: #34C759; font-size: 12px; font-weight: 700; }
            """
        )
        self.hide()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_StyledBackground, True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 28, 16, 20)
        lay.setSpacing(6)

        self.label = QLabel("calling…")
        self.label.setObjectName("acLabel")
        self.label.setAlignment(Qt.AlignCenter)

        self.avatar = QLabel()
        self.avatar.setFixedSize(88, 88)
        self.avatar.setAlignment(Qt.AlignCenter)

        self.name_lab = QLabel("")
        self.name_lab.setObjectName("acName")
        self.name_lab.setAlignment(Qt.AlignCenter)
        self.name_lab.setWordWrap(True)

        self.number_lab = QLabel("")
        self.number_lab.setObjectName("acNumber")
        self.number_lab.setAlignment(Qt.AlignCenter)

        self.timer_lab = QLabel("")
        self.timer_lab.setObjectName("acTimer")
        self.timer_lab.setAlignment(Qt.AlignCenter)
        self.timer_lab.setWordWrap(True)
        self.timer_lab.setMaximumWidth(208)

        top = QVBoxLayout()
        top.setSpacing(8)
        top.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        top.addWidget(self.label)
        top.addSpacing(12)
        av_row = QHBoxLayout()
        av_row.addStretch(1)
        av_row.addWidget(self.avatar)
        av_row.addStretch(1)
        top.addLayout(av_row)
        top.addWidget(self.name_lab)
        top.addWidget(self.number_lab)
        top.addWidget(self.timer_lab)
        lay.addLayout(top)
        lay.addStretch(1)

        self.hangup_btn = _CircleAction("decline", self)
        self.hangup_btn.setAutoDefault(False)
        self.hangup_btn.setDefault(False)
        self.ok_btn = QPushButton("OK")
        self.ok_btn.setFixedHeight(36)
        self.ok_btn.setAutoDefault(False)
        self.ok_btn.setDefault(False)
        self.ok_btn.setFocusPolicy(Qt.StrongFocus)
        self.ok_btn.setStyleSheet(
            "QPushButton { font-size:13px; font-weight:800; color:#0a1218;"
            " background:#5ec4a8; border:none; border-radius:12px; padding:6px 18px; }"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
        self.ok_btn.hide()

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self.hangup_btn)
        btn_row.addWidget(self.ok_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        self.hint = QLabel("Confirm · Hang up")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setStyleSheet("color:#636366; font-size:8px;")
        lay.addSpacing(8)
        lay.addWidget(self.hint)

        self.hangup_btn.clicked.connect(self._do_hangup)
        self.ok_btn.clicked.connect(self._do_dismiss)

        self._pulse = QTimer(self)
        self._pulse.timeout.connect(self._tick_pulse)
        self._pulse_n = 0
        # Ignore Confirm key-release that follows the key that opened this overlay
        self._input_ready_at = 0.0

    def _arm_input(self) -> None:
        self._input_ready_at = time.time() + 0.5

    def _input_ready(self) -> bool:
        return time.time() >= float(self._input_ready_at or 0.0)

    def _set_avatar(self, name: str, initial: str, photo: Optional[str]) -> None:
        size = 88
        if photo:
            pix = QPixmap(photo)
            if not pix.isNull():
                scaled = pix.scaled(
                    size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )
                x = max(0, (scaled.width() - size) // 2)
                y = max(0, (scaled.height() - size) // 2)
                cropped = scaled.copy(x, y, size, size)
                out = QPixmap(size, size)
                out.fill(Qt.transparent)
                p = QPainter(out)
                p.setRenderHint(QPainter.Antialiasing)
                from PyQt5.QtGui import QPainterPath

                path = QPainterPath()
                path.addEllipse(0, 0, size, size)
                p.setClipPath(path)
                p.drawPixmap(0, 0, cropped)
                p.end()
                self.avatar.setPixmap(out)
                self.avatar.setText("")
                self.avatar.setStyleSheet("background: transparent; border: none;")
                self.avatar.show()
                return
        from esp_handset.pages import _avatar_color

        color = _avatar_color(name or initial or "?")
        self.avatar.setPixmap(QPixmap())
        self.avatar.setText((initial or "?")[:1].upper())
        self.avatar.setStyleSheet(
            f"background:{color}; color:#fff; border-radius:{size // 2}px;"
            f"font-size:32px; font-weight:800;"
        )
        self.avatar.show()

    def _resolve(self, number: str, name: str = "", photo: Optional[str] = None):
        num = (number or "").strip()
        resolved_name = (name or "").strip()
        resolved_photo = photo
        initial = "?"
        try:
            from esp_handset.pages import _contact_display, _lookup_contact

            known = _lookup_contact(phone=num) is not None
            disp, initial, ph = _contact_display(phone=num, fallback=num or "Unknown")
            if not resolved_name and known:
                resolved_name = disp
            if not resolved_photo:
                resolved_photo = ph
            if not initial:
                initial = (resolved_name or num or "?")[:1].upper()
            if known and resolved_name:
                self.name_lab.setText(resolved_name)
                self.number_lab.setText(num)
                self.number_lab.setVisible(bool(num))
                self._set_avatar(resolved_name, initial, resolved_photo)
                return resolved_name
        except Exception:
            pass
        self.name_lab.setText(resolved_name or num or "Unknown")
        self.number_lab.hide()
        if resolved_name:
            self._set_avatar(resolved_name, resolved_name[:1], resolved_photo)
        else:
            self.avatar.hide()
        return resolved_name or num

    def show_ringing(
        self,
        number: str,
        *,
        name: str = "",
        photo: Optional[str] = None,
        on_hangup: Optional[Callable[[], None]] = None,
    ) -> None:
        self._mode = "ringing"
        self._on_hangup = on_hangup
        self._on_dismiss = None
        self._resolve(number, name, photo)
        self.label.setText("calling…")
        self.timer_lab.setText("Ringing")
        self.timer_lab.show()
        self.hangup_btn.show()
        self.ok_btn.hide()
        self.hint.setText("Confirm · Hang up")
        self._arm_input()
        self._show_and_focus(self.hangup_btn)
        self._pulse_n = 0
        self._pulse.start(400)

    def show_active(
        self,
        number: str,
        *,
        name: str = "",
        photo: Optional[str] = None,
        on_hangup: Optional[Callable[[], None]] = None,
        elapsed_s: int = 0,
    ) -> None:
        self._mode = "active"
        self._on_hangup = on_hangup
        self._on_dismiss = None
        self._resolve(number, name, photo)
        self.label.setText("on call")
        self.set_elapsed(elapsed_s)
        self.timer_lab.show()
        self.hangup_btn.show()
        self.ok_btn.hide()
        self.hint.setText("Confirm · Hang up")
        self._arm_input()
        self._show_and_focus(self.hangup_btn)
        self._pulse.stop()

    def show_ended(
        self,
        number: str,
        *,
        name: str = "",
        status_line: str = "Call ended",
        detail: str = "",
        on_dismiss: Optional[Callable[[], None]] = None,
    ) -> None:
        self._mode = "ended"
        self._on_hangup = None
        self._on_dismiss = on_dismiss
        self._resolve(number, name)
        self.label.setText(status_line)
        self.timer_lab.setText(_screen_detail(detail) if detail else "")
        self.timer_lab.setVisible(bool(detail))
        # Errors use a softer color than the green talk timer
        if detail and not re.match(r"^\d+:\d{2}$", detail.strip()):
            self.timer_lab.setStyleSheet("color:#FF9F0A; font-size:11px; font-weight:700;")
        else:
            self.timer_lab.setStyleSheet("")
        self.hangup_btn.hide()
        self.ok_btn.show()
        self.hint.setText("Confirm · OK")
        self._arm_input()
        self._show_and_focus(self.ok_btn)
        self._pulse.stop()

    def set_elapsed(self, seconds: int) -> None:
        s = max(0, int(seconds))
        m, r = divmod(s, 60)
        self.timer_lab.setText(f"{m}:{r:02d}")

    def set_ringing_hint(self, text: str) -> None:
        if self._mode == "ringing":
            self.timer_lab.setText(text)

    def _show_and_focus(self, widget: QWidget) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.raise_()
        self.show()
        widget.setFocus(Qt.OtherFocusReason)
        from esp_handset import digi_nav

        digi_nav.clear_highlights(self)
        digi_nav._highlight(widget, True)
        widget.update()

    def hide_call(self) -> None:
        self._pulse.stop()
        self.hide()
        self._on_hangup = None
        self._on_dismiss = None
        self._mode = "idle"

    @property
    def active(self) -> bool:
        return self.isVisible()

    @property
    def mode(self) -> str:
        return self._mode

    def _do_hangup(self) -> None:
        if not self._input_ready():
            return
        cb = self._on_hangup
        if callable(cb):
            cb()

    def _do_dismiss(self) -> None:
        if not self._input_ready():
            return
        cb = self._on_dismiss
        self.hide_call()
        if callable(cb):
            cb()

    def _tick_pulse(self) -> None:
        if self._mode != "ringing":
            return
        self._pulse_n = (self._pulse_n + 1) % 3
        cur = (self.timer_lab.text() or "")
        # Don't overwrite Calling… with Ringing — that caused the flicker.
        if cur.startswith("Connecting") or cur.startswith("Calling"):
            base = "Calling" if cur.startswith("Calling") else "Connecting"
            self.timer_lab.setText(base + "." * (self._pulse_n + 1))
        elif cur.startswith("Ringing") or not cur.strip():
            self.timer_lab.setText("Ringing" + "." * (self._pulse_n + 1))
        # else leave a custom status alone

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if not self._input_ready():
            event.accept()
            return
        if self._mode == "ended":
            if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
                self._do_dismiss()
                event.accept()
                return
        else:
            if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
                self._do_hangup()
                event.accept()
                return
        super().keyPressEvent(event)


class CallController(QObject):
    """Outbound (and light inbound watch) call state machine."""

    state_changed = pyqtSignal(str)  # ringing|active|ended|idle
    _dial_finished = pyqtSignal(int, bool, str)  # gen, ok, reason

    def __init__(self, shell, on_status: Optional[Callable[[str], None]] = None):
        super().__init__(shell)
        self.shell = shell
        self.on_status = on_status or (lambda _m: None)
        self._entry_id = ""
        self._number = ""
        self._name = ""
        self._phase = "idle"
        self._answered = False
        self._user_hangup = False
        self._talk_started = 0.0
        self._ring_started = 0.0
        self._ring_timeout_s = 45.0
        self._saw_progress = False  # True once linphone reports dialing/ringing
        self._saw_remote_ring = False  # True only on OutgoingRinging
        self._dial_gen = 0
        self._awaiting_dial = False
        self._poll = QTimer(self)
        self._poll.timeout.connect(self._tick)
        self._poll.start(500)
        self._incoming_prompted = False
        self._inbound_entry_id = ""
        self._dial_finished.connect(self._on_dial_finished)

    @property
    def busy(self) -> bool:
        return self._phase in ("dialing", "ringing", "active")

    def start_outbound(self, number: str) -> bool:
        try:
            return self._start_outbound_inner(number)
        except Exception as e:
            print(f"[call] start_outbound crashed: {e}", flush=True)
            self._phase = "idle"
            try:
                self.on_status("Call failed")
            except Exception:
                pass
            return False

    def _start_outbound_inner(self, number: str) -> bool:
        num = (number or "").strip()
        if not num:
            self.on_status("Enter a number")
            return False
        if self.busy:
            self.on_status("Already in a call")
            return False
        if not sip_call.available():
            hint = sip_call.missing_hint() or "Installing VoIP…"
            self.on_status(hint)

        name = ""
        try:
            from esp_handset.pages import _contact_display, _lookup_contact

            if _lookup_contact(phone=num):
                name, _, _ = _contact_display(phone=num, fallback=num)
        except Exception:
            pass

        self._number = num
        self._name = name
        self._answered = False
        self._user_hangup = False
        self._talk_started = 0.0
        self._ring_started = time.time()
        self._saw_progress = False
        self._saw_remote_ring = False
        self._active_idle_hits = 0
        self._phase = "dialing"
        self._awaiting_dial = True
        self._dial_gen += 1
        gen = self._dial_gen

        entry = clog.start(
            direction="out", number=num, name=name, status="dialing"
        )
        self._entry_id = str(entry.get("id") or "")

        # Show UI immediately — SIP register/dial runs in a worker thread
        self._show_ringing()
        ov = getattr(self.shell, "_active_call", None)
        if ov is not None:
            ov.set_ringing_hint(
                "Installing VoIP…" if not sip_call.available() else "Calling…"
            )
        self.on_status(f"Calling {num}")
        self.state_changed.emit("dialing")

        def work() -> None:
            try:
                ok, reason = sip_call.dial_ex(num)
            except Exception as e:
                print(f"[call] dial_ex failed: {e}", flush=True)
                ok, reason = False, str(e) or "Dial failed"
            self._dial_finished.emit(gen, bool(ok), str(reason or ""))

        threading.Thread(target=work, name="sip-dial", daemon=True).start()
        return True

    def _on_dial_finished(self, gen: int, ok: bool, reason: str) -> None:
        if gen != self._dial_gen:
            return
        self._awaiting_dial = False
        if self._user_hangup or self._phase not in ("dialing", "ringing"):
            return
        if not ok:
            detail = _screen_detail(
                reason or sip_call.last_error() or "Check SIP / Wi‑Fi"
            )
            clog.finish(self._entry_id, status="failed", duration_s=0)
            self._phase = "ended"
            title = "Could not dial"
            low = detail.lower()
            if "not registered" in low:
                title = "Not registered"
            elif "balance" in low:
                title = "No balance"
            elif "locked" in low:
                title = "SIP locked"
            elif "voip" in low or "linphone" in low:
                title = "VoIP not ready"
            self._show_ended(title, detail)
            self.on_status(detail)
            self.state_changed.emit("ended")
            return
        self._phase = "ringing"
        clog.update(self._entry_id, status="dialing")
        ov = getattr(self.shell, "_active_call", None)
        if ov is not None:
            ov.set_ringing_hint("Calling…")
        self.on_status(f"Calling {self._number}")
        self.state_changed.emit("ringing")

    def hangup(self) -> None:
        if not self.busy and self._phase != "ended":
            sip_call.hangup()
            return
        self._user_hangup = True
        self._awaiting_dial = False
        self._dial_gen += 1  # ignore in-flight dial result
        sip_call.hangup()
        if self._phase in ("dialing", "ringing"):
            self._finish("canceled")
        elif self._phase == "active":
            dur = int(time.time() - self._talk_started) if self._talk_started else 0
            clog.finish(self._entry_id, status="ended", duration_s=dur)
            # keep answered=True via finish logic
            clog.update(self._entry_id, answered=True, status="ended")
            self._phase = "ended"
            self._show_ended("Call ended", self._fmt_dur(dur))
            self.state_changed.emit("ended")
            self._clear_soon()
        else:
            self._clear()

    def dismiss_ended(self) -> None:
        self._clear()

    def _fmt_dur(self, sec: int) -> str:
        m, s = divmod(max(0, sec), 60)
        return f"{m}:{s:02d}"

    def _show_ringing(self) -> None:
        ov = getattr(self.shell, "_active_call", None)
        if ov is None:
            return
        ov.show_ringing(
            self._number,
            name=self._name,
            on_hangup=self.hangup,
        )

    def _show_active(self) -> None:
        ov = getattr(self.shell, "_active_call", None)
        if ov is None:
            return
        elapsed = int(time.time() - self._talk_started) if self._talk_started else 0
        ov.show_active(
            self._number,
            name=self._name,
            on_hangup=self.hangup,
            elapsed_s=elapsed,
        )

    def _show_ended(self, title: str, detail: str = "") -> None:
        ov = getattr(self.shell, "_active_call", None)
        if ov is None:
            return
        ov.show_ended(
            self._number,
            name=self._name,
            status_line=title,
            detail=_screen_detail(detail) if detail else "",
            on_dismiss=self.dismiss_ended,
        )

    def _finish(self, status: str, detail: str = "") -> None:
        dur = 0
        if self._answered and self._talk_started:
            dur = int(time.time() - self._talk_started)
        clog.finish(self._entry_id, status=status, duration_s=dur)
        self._phase = "ended"
        titles = {
            "no_answer": ("No answer", "They didn’t pick up"),
            "canceled": ("Canceled", "You hung up"),
            "busy": ("Busy", "Line was busy"),
            "failed": ("Call failed", "Check SIP / number / Wi‑Fi"),
            "declined": ("Declined", ""),
            "missed": ("Missed call", ""),
            "ended": ("Call ended", self._fmt_dur(dur) if dur else ""),
        }
        title, default_detail = titles.get(status, ("Call ended", ""))
        self._show_ended(title, detail or default_detail)
        self.on_status(title)
        self.state_changed.emit("ended")

    def _clear_soon(self) -> None:
        QTimer.singleShot(1600, self._clear)

    def _clear(self) -> None:
        ov = getattr(self.shell, "_active_call", None)
        if ov is not None:
            ov.hide_call()
        self._phase = "idle"
        self._entry_id = ""
        self._number = ""
        self._name = ""
        self._answered = False
        self._user_hangup = False
        self._incoming_prompted = False
        self._inbound_entry_id = ""
        self._saw_progress = False
        self._saw_remote_ring = False
        self._awaiting_dial = False
        self.state_changed.emit("idle")

    def _tick(self) -> None:
        # Connecting (register/dial still running): don't kill a live INVITE
        if self._awaiting_dial:
            if self._phase in ("dialing", "ringing"):
                if time.time() - self._ring_started > 90.0:
                    self._awaiting_dial = False
                    self._dial_gen += 1
                    sip_call.hangup()
                    why = sip_call.last_error() or "SIP took too long"
                    self._finish("failed", why)
            return
        try:
            info = sip_call.poll()
        except Exception:
            return

        # Watch for inbound when idle
        if self._phase == "idle":
            if info.phase == "incoming" and not self._incoming_prompted:
                self._incoming_prompted = True
                remote = sip_call.remote_number(info.remote) or info.remote or "Unknown"
                self._prompt_incoming(remote)
            elif info.phase == "idle" and self._incoming_prompted:
                # Remote hung up before we answered
                if self._inbound_entry_id:
                    clog.finish(self._inbound_entry_id, status="missed", duration_s=0)
                    self._inbound_entry_id = ""
                try:
                    self.shell.hide_incoming_call()
                except Exception:
                    pass
                self._incoming_prompted = False
                self.on_status("Missed call")
            return

        if self._phase in ("dialing", "ringing"):
            elapsed = time.time() - self._ring_started
            if info.phase in ("dialing", "ringing", "early", "active"):
                self._saw_progress = True
            if info.phase == "ringing":
                self._saw_remote_ring = True
                self._phase = "ringing"
                clog.update(self._entry_id, status="ringing")
                ov = getattr(self.shell, "_active_call", None)
                if ov is not None:
                    ov.set_ringing_hint("Ringing")
            # Only real answer → Connected. "Call out" is still dialing/ringing.
            if info.phase == "active":
                self._answered = True
                self._talk_started = time.time()
                self._phase = "active"
                self._awaiting_dial = False
                clog.update(self._entry_id, status="answered", answered=True)
                self._show_active()
                self.on_status("Connected")
                self.state_changed.emit("active")
                return
            if info.phase == "dialing":
                ov = getattr(self.shell, "_active_call", None)
                # Latch: once we've been ringing, don't flicker back to Calling
                if ov is not None:
                    if self._saw_remote_ring:
                        ov.set_ringing_hint("Ringing")
                    else:
                        ov.set_ringing_hint("Calling…")
            if info.phase == "error":
                raw = (info.raw or "").lower()
                self._awaiting_dial = False
                if "busy" in raw or "486" in raw:
                    self._finish("busy")
                else:
                    why = sip_call.last_error() or ""
                    if not why:
                        why = sip_call.last_call_error()
                    if not why:
                        lines = [ln.strip() for ln in (info.raw or "").splitlines() if ln.strip()]
                        why = lines[-1][:80] if lines else "SIP rejected call"
                    self._finish("failed", _screen_detail(why))
                return
            if info.phase in ("ending", "idle"):
                if self._user_hangup:
                    return
                raw = (info.raw or "").lower()
                if re.search(
                    r"call out|duration=\d+|hook=sip:|StreamsRunning|OutgoingRinging",
                    raw,
                ):
                    return
                # Ignore brief idle blips (answer / media renegotiation)
                if elapsed < 20.0:
                    return
                if not self._saw_progress and elapsed > 25.0:
                    why = _screen_detail(
                        sip_call.last_error()
                        or sip_call.last_call_error()
                        or "No ringback"
                    )
                    self._finish("failed", why)
                    return
                if self._saw_remote_ring:
                    self._finish("no_answer")
                    return
                if self._saw_progress:
                    why = _screen_detail(
                        sip_call.last_error()
                        or sip_call.last_call_error()
                        or "Call ended"
                    )
                    self._finish("failed", why)
                    return
                return
            # Still dialing/ringing according to linphone
            if elapsed >= self._ring_timeout_s:
                raw = (info.raw or "").lower()
                # Still on the wire (answered or still ringing) — do not kill it
                if re.search(
                    r"call out|duration=\d+|hook=sip:|StreamsRunning|OutgoingRinging",
                    raw,
                ):
                    return
                sip_call.hangup()
                if self._saw_remote_ring:
                    self._finish("no_answer")
                else:
                    self._finish(
                        "failed",
                        _screen_detail(
                            sip_call.last_call_error() or "No ringback"
                        ),
                    )
                return
            return
        if self._phase == "active":
            ov = getattr(self.shell, "_active_call", None)
            if ov is not None and ov.mode == "active" and self._talk_started:
                ov.set_elapsed(int(time.time() - self._talk_started))
            raw = (info.raw or "").lower()
            still_live = bool(
                re.search(
                    r"call out|duration=\d+|hook=sip:|StreamsRunning|hook=offhook",
                    raw,
                )
            )
            if still_live:
                self._active_idle_hits = 0
                return
            if info.phase in ("idle", "ending", "error"):
                if self._user_hangup:
                    return
                # Don't tear down on a single idle poll right after answer
                idle_hits = getattr(self, "_active_idle_hits", 0) + 1
                self._active_idle_hits = idle_hits
                if idle_hits < 4:
                    return
                self._active_idle_hits = 0
                dur = int(time.time() - self._talk_started) if self._talk_started else 0
                clog.finish(self._entry_id, status="ended", duration_s=dur)
                clog.update(self._entry_id, answered=True, status="ended")
                self._phase = "ended"
                self._show_ended("Call ended", self._fmt_dur(dur))
                self.state_changed.emit("ended")
                self._clear_soon()
            else:
                self._active_idle_hits = 0

    def _prompt_incoming(self, number: str) -> None:
        name = ""
        try:
            from esp_handset.pages import _contact_display, _lookup_contact

            if _lookup_contact(phone=number):
                name, _, _ = _contact_display(phone=number, fallback=number)
        except Exception:
            pass
        entry = clog.start(
            direction="in", number=number, name=name, status="ringing"
        )
        entry_id = str(entry.get("id") or "")
        self._inbound_entry_id = entry_id

        def answered() -> None:
            sip_call.answer()
            self._entry_id = entry_id
            self._inbound_entry_id = ""
            self._number = number
            self._name = name
            self._answered = True
            self._user_hangup = False
            self._talk_started = time.time()
            self._phase = "active"
            clog.update(entry_id, status="answered", answered=True)
            # Hide incoming overlay then show in-call
            try:
                self.shell.hide_incoming_call()
            except Exception:
                pass
            self._show_active()
            self.state_changed.emit("active")

        def declined() -> None:
            sip_call.hangup()
            clog.finish(entry_id, status="declined", duration_s=0)
            self._inbound_entry_id = ""
            self._incoming_prompted = False
            self._phase = "idle"

        try:
            self.shell.show_incoming_call(
                number,
                name=name,
                on_answer=answered,
                on_decline=declined,
                subtitle="Incoming",
            )
        except Exception:
            pass


def make_call_log_page(
    on_back: Callable[[], None],
    *,
    on_redial: Optional[Callable[[str], bool]] = None,
) -> QWidget:
    body = QWidget()
    body.setStyleSheet("background:#0e1620; color:#e8eef5;")
    lay = QVBoxLayout(body)
    lay.setContentsMargins(4, 2, 4, 4)
    lay.setSpacing(4)

    tip = QLabel("Confirm = call again")
    tip.setStyleSheet("font-size:10px; color:#7a8a9a;")
    lay.addWidget(tip)

    lst = QListWidget()
    lst.setStyleSheet(
        "QListWidget { background:#0e1620; color:#e8eef5; border:none;"
        " font-size:11px; outline:none; }"
        "QListWidget::item { padding:8px 6px; border-bottom:1px solid #1a2430; }"
        'QListWidget::item:selected { background:#1e2a38; }'
        'QListWidget::item[digiFocus="1"] { border:2px solid #FFE600; }'
    )
    lst.setFocusPolicy(Qt.StrongFocus)
    empty = QLabel("No calls yet.\nPlace a call from Phone.")
    empty.setAlignment(Qt.AlignCenter)
    empty.setStyleSheet("font-size:12px; color:#7a8a9a;")
    empty.setWordWrap(True)

    lay.addWidget(lst, 1)
    lay.addWidget(empty)

    def refresh() -> None:
        lst.clear()
        entries = clog.list_entries()
        empty.setVisible(len(entries) == 0)
        lst.setVisible(len(entries) > 0)
        for e in entries:
            direction = e.get("dir") or "?"
            arrow = "↙" if direction == "in" else "↗"
            who = (e.get("name") or e.get("number") or "Unknown").strip()
            num = (e.get("number") or "").strip()
            when = clog.display_when(e)
            st = clog.display_status(e)
            line1 = f"{arrow}  {who}"
            line2 = st
            if num and num != who:
                line2 = f"{num} · {st}"
            text = f"{line1}\n{when} · {line2}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, num)
            # Soft color by outcome
            st_key = str(e.get("status") or "")
            if e.get("answered") or st_key in ("answered", "ended"):
                item.setForeground(QColor("#c8e6d0"))
            elif st_key in ("missed", "no_answer"):
                item.setForeground(QColor("#f0c0c0"))
            elif st_key == "canceled":
                item.setForeground(QColor("#9aa8b8"))
            lst.addItem(item)

    def redial_selected(_item: Optional[QListWidgetItem] = None) -> None:
        if not on_redial:
            return
        item = _item if isinstance(_item, QListWidgetItem) else lst.currentItem()
        if item is None:
            return
        num = str(item.data(Qt.UserRole) or "").strip()
        if not num:
            return
        # Digi Confirm emits itemClicked + itemActivated; also defer so the
        # Confirm key-release cannot immediately hit Hang up on the overlay.
        if pending["num"]:
            return
        pending["num"] = num

        def go() -> None:
            n = pending["num"]
            pending["num"] = ""
            if not n:
                return
            try:
                on_redial(n)
            except Exception as e:
                print(f"[call_log] redial failed: {e}", flush=True)

        QTimer.singleShot(80, go)

    pending = {"num": ""}
    lst.itemActivated.connect(redial_selected)
    lst.itemClicked.connect(redial_selected)

    page = page_chrome("Call Log", body, on_back, scroll=False)
    page.refresh_call_log = refresh  # type: ignore[attr-defined]
    refresh()
    return page


def make_phone_page(
    on_back,
    on_status,
    *,
    on_call_log: Optional[Callable[[], None]] = None,
    start_call: Optional[Callable[[str], bool]] = None,
    hangup_call: Optional[Callable[[], None]] = None,
) -> QWidget:
    """T9 dial pad — Call hands off to CallController overlay."""
    from PyQt5.QtWidgets import (
        QGridLayout,
        QLineEdit,
        QPushButton,
        QSizePolicy,
        QVBoxLayout,
        QHBoxLayout,
    )

    del on_back
    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(1, 0, 1, 0)
    lay.setSpacing(3)

    dial = QLineEdit()
    dial.setObjectName("dialDisplay")
    dial.setReadOnly(True)
    dial.setFocusPolicy(Qt.NoFocus)
    dial.setAlignment(Qt.AlignCenter)
    dial.setPlaceholderText("number")
    dial.setFixedHeight(28)
    dial.setStyleSheet(
        "font-size: 18px; font-weight: 700; font-family: monospace;"
        "padding: 2px 4px; letter-spacing: 1px;"
    )
    lay.addWidget(dial)

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
        dial.setText(dial.text() + ch)
        dial.setCursorPosition(len(dial.text()))

    def backspace() -> None:
        dial.setText(dial.text()[:-1])

    def do_call() -> None:
        num = dial.text().strip()
        if not num:
            on_status("Enter a number")
            return
        if callable(start_call):
            # Defer so Confirm key-release does not hang up the new overlay
            QTimer.singleShot(80, lambda n=num: start_call(n))
            return
        # Fallback without controller
        from esp_handset import sip_call as sc

        sc.dial(num)
        clog.start(direction="out", number=num, status="dialing")
        on_status(f"Dialing {num}")

    def do_end() -> None:
        if callable(hangup_call):
            hangup_call()
            return
        sip_call.hangup()
        on_status("Call ended")

    grid = QGridLayout()
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(3)
    grid.setVerticalSpacing(3)
    for i, (digit, letters) in enumerate(keys):
        label = digit if not letters else f"{digit}\n{letters}"
        btn = QPushButton(label)
        btn.setMinimumHeight(0)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        btn.setStyleSheet("font-size: 13px; font-weight: 800; padding: 0px;")
        btn.clicked.connect(lambda _=False, c=digit: append_digit(c))
        grid.addWidget(btn, i // 3, i % 3)
    lay.addLayout(grid, 1)

    actions = QHBoxLayout()
    actions.setSpacing(3)
    del_btn = QPushButton("⌫")
    del_btn.setFixedHeight(28)
    del_btn.clicked.connect(backspace)
    plus_btn = QPushButton("+")
    plus_btn.setFixedHeight(28)
    plus_btn.clicked.connect(lambda: append_digit("+"))
    call = QPushButton("Call")
    call.setFixedHeight(28)
    call.setStyleSheet("font-weight:800; background:#1a7a3a; padding:0px;")
    call.clicked.connect(do_call)
    end = QPushButton("End")
    end.setFixedHeight(28)
    end.setStyleSheet("font-weight:800; background:#8a2020; padding:0px;")
    end.clicked.connect(do_end)
    actions.addWidget(del_btn, 1)
    actions.addWidget(plus_btn, 1)
    actions.addWidget(call, 2)
    actions.addWidget(end, 2)
    lay.addLayout(actions)

    if on_call_log:
        log_btn = QPushButton("Call log")
        log_btn.setFixedHeight(22)
        log_btn.setStyleSheet("font-size:11px; padding:0px;")
        log_btn.clicked.connect(on_call_log)
        lay.addWidget(log_btn)

    page = page_chrome("Phone", body, None, scroll=False)

    def set_dial_number(number: str) -> None:
        dial.setText(str(number or "").strip())
        dial.setCursorPosition(len(dial.text()))

    page.set_dial_number = set_dial_number  # type: ignore[attr-defined]
    page.start_call_number = do_call  # type: ignore[attr-defined]
    return page
