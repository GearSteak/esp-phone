"""Fullscreen incoming-call takeover — iPhone-style Answer / Decline."""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class _CircleAction(QPushButton):
    """Round Answer (green phone) or Decline (red phone + slash)."""

    def __init__(self, kind: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._kind = kind  # "answer" | "decline"
        self.setFixedSize(56, 56)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        focused = self.property("digiFocus") == "1"
        r = self.rect().adjusted(3, 3, -3, -3)
        if self._kind == "answer":
            fill = QColor("#34C759")
        else:
            fill = QColor("#FF3B30")
        p.setBrush(fill)
        p.setPen(Qt.NoPen)
        p.drawEllipse(r)
        if focused:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor("#FFE600"), 3))
            p.drawEllipse(r.adjusted(-2, -2, 2, 2))
            p.setPen(QPen(QColor("#000000"), 2))
            p.drawEllipse(r)

        # Phone handset (simple vector)
        p.setPen(QPen(QColor("#ffffff"), 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        cx, cy = r.center().x(), r.center().y()
        # curved handset
        phone = QRectF(cx - 11, cy - 10, 22, 20)
        p.drawArc(phone, 40 * 16, 100 * 16)
        p.drawArc(phone, 220 * 16, 100 * 16)
        # ear / mouth caps
        p.drawLine(int(cx - 9), int(cy - 6), int(cx - 5), int(cy - 9))
        p.drawLine(int(cx + 5), int(cy + 9), int(cx + 9), int(cy + 6))

        if self._kind == "decline":
            p.setPen(QPen(QColor("#ffffff"), 3.2, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(int(cx - 12), int(cy + 12), int(cx + 12), int(cy - 12))


class IncomingCallOverlay(QWidget):
    """Opaque takeover until Answer or Decline."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._on_answer: Optional[Callable[[], None]] = None
        self._on_decline: Optional[Callable[[], None]] = None
        self.setObjectName("incomingCall")
        self.setStyleSheet(
            """
            #incomingCall { background: #000000; }
            QLabel {
                background: transparent; border: none;
            }
            QLabel#incLabel {
                color: #aeaeb2; font-size: 10px; font-weight: 600;
            }
            QLabel#incName {
                color: #ffffff; font-size: 18px; font-weight: 800;
            }
            QLabel#incNumber {
                color: #d1d1d6; font-size: 12px; font-weight: 600;
            }
            """
        )
        self.hide()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_StyledBackground, True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 28, 16, 20)
        lay.setSpacing(6)

        self.label = QLabel("incoming call")
        self.label.setObjectName("incLabel")
        self.label.setAlignment(Qt.AlignCenter)

        self.avatar = QLabel()
        self.avatar.setFixedSize(88, 88)
        self.avatar.setAlignment(Qt.AlignCenter)
        self.avatar.setScaledContents(False)

        self.name_lab = QLabel("")
        self.name_lab.setObjectName("incName")
        self.name_lab.setAlignment(Qt.AlignCenter)
        self.name_lab.setWordWrap(True)

        self.number_lab = QLabel("")
        self.number_lab.setObjectName("incNumber")
        self.number_lab.setAlignment(Qt.AlignCenter)
        self.number_lab.setWordWrap(True)

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

        lay.addLayout(top)
        lay.addStretch(1)

        self.decline_btn = _CircleAction("decline", self)
        self.answer_btn = _CircleAction("answer", self)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(36)
        btn_row.addStretch(1)
        btn_row.addWidget(self.decline_btn)
        btn_row.addWidget(self.answer_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        self.answer_btn.clicked.connect(self._do_answer)
        self.decline_btn.clicked.connect(self._do_decline)

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
                return
        # Initials circle via stylesheet
        from esp_handset.pages import _avatar_color

        color = _avatar_color(name or initial or "?")
        self.avatar.setPixmap(QPixmap())
        self.avatar.setText((initial or "?")[:1])
        self.avatar.setStyleSheet(
            f"background:{color}; color:#fff; border-radius:{size // 2}px;"
            f"font-size:32px; font-weight:800;"
        )

    def show_call(
        self,
        number: str,
        *,
        name: str = "",
        photo: Optional[str] = None,
        on_answer: Optional[Callable[[], None]] = None,
        on_decline: Optional[Callable[[], None]] = None,
        subtitle: str = "",
    ) -> None:
        del subtitle
        self._on_answer = on_answer
        self._on_decline = on_decline

        num = (number or "").strip()
        # Resolve contact if caller didn't pass name/photo
        resolved_name = (name or "").strip()
        resolved_photo = photo
        initial = "?"
        known = False
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
        except Exception:
            if resolved_name:
                initial = resolved_name[:1].upper()
            elif num:
                initial = num[:1]

        if known and resolved_name:
            self.name_lab.setText(resolved_name)
            self.name_lab.show()
            self.number_lab.setText(num)
            self.number_lab.setVisible(bool(num))
            self._set_avatar(resolved_name, initial, resolved_photo)
            self.avatar.show()
        else:
            # Unknown caller — number only, no contact chrome
            self.name_lab.setText(num or "Unknown")
            self.name_lab.show()
            self.number_lab.hide()
            self.avatar.hide()

        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.raise_()
        self.show()
        self.answer_btn.setFocus(Qt.OtherFocusReason)
        from esp_handset import digi_nav

        digi_nav.clear_highlights(self)
        digi_nav._highlight(self.answer_btn, True)
        self.answer_btn.update()
        self.decline_btn.update()

    def hide_call(self) -> None:
        self.hide()
        self._on_answer = None
        self._on_decline = None

    @property
    def active(self) -> bool:
        return self.isVisible()

    def _do_answer(self) -> None:
        cb = self._on_answer
        self.hide_call()
        if callable(cb):
            cb()

    def _do_decline(self) -> None:
        cb = self._on_decline
        self.hide_call()
        if callable(cb):
            cb()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._do_answer()
            event.accept()
            return
        if key == Qt.Key_Escape:
            self._do_decline()
            event.accept()
            return
        if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            from esp_handset import digi_nav

            # Only two buttons — L/R (and U/D) swap focus
            cur = digi_nav.digi_current(self)
            other = (
                self.answer_btn
                if cur is self.decline_btn
                else self.decline_btn
            )
            digi_nav.clear_highlights(self)
            other.setFocus(Qt.OtherFocusReason)
            digi_nav._highlight(other, True)
            self.answer_btn.update()
            self.decline_btn.update()
            event.accept()
            return
        super().keyPressEvent(event)
