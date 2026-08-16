"""Fullscreen incoming-call takeover (Answer / Decline)."""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class IncomingCallOverlay(QWidget):
    """Blocks Digivice until the user answers or declines."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._on_answer: Optional[Callable[[], None]] = None
        self._on_decline: Optional[Callable[[], None]] = None
        self.setObjectName("incomingCall")
        self.setStyleSheet(
            """
            #incomingCall {
                background: rgba(6, 10, 16, 0.97);
            }
            QLabel#incTitle {
                color: #9ab; font-size: 11px; font-weight: 700;
                background: transparent; border: none;
            }
            QLabel#incWho {
                color: #FFE600; font-size: 22px; font-weight: 800;
                background: transparent; border: none;
            }
            QLabel#incSub {
                color: #cde; font-size: 11px;
                background: transparent; border: none;
            }
            """
        )
        self.hide()
        self.setFocusPolicy(Qt.StrongFocus)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 24, 12, 16)
        lay.setSpacing(8)

        title = QLabel("Incoming call")
        title.setObjectName("incTitle")
        title.setAlignment(Qt.AlignCenter)
        self.who = QLabel("Unknown")
        self.who.setObjectName("incWho")
        self.who.setAlignment(Qt.AlignCenter)
        self.who.setWordWrap(True)
        self.sub = QLabel("")
        self.sub.setObjectName("incSub")
        self.sub.setAlignment(Qt.AlignCenter)
        self.sub.setWordWrap(True)

        lay.addStretch(1)
        lay.addWidget(title)
        lay.addWidget(self.who)
        lay.addWidget(self.sub)
        lay.addStretch(1)

        self.answer_btn = QPushButton("Answer")
        self.answer_btn.setFixedHeight(44)
        self.answer_btn.setStyleSheet(
            "font-size:16px; font-weight:800; background:#1a7a3a; color:#fff;"
        )
        self.answer_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.decline_btn = QPushButton("Decline")
        self.decline_btn.setFixedHeight(44)
        self.decline_btn.setStyleSheet(
            "font-size:16px; font-weight:800; background:#8a2020; color:#fff;"
        )
        self.decline_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        tip = QLabel("Confirm = Answer · Back = Decline")
        tip.setAlignment(Qt.AlignCenter)
        tip.setStyleSheet("color:#678; font-size:9px; background:transparent; border:none;")

        lay.addWidget(self.answer_btn)
        lay.addWidget(self.decline_btn)
        lay.addWidget(tip)

        self.answer_btn.clicked.connect(self._do_answer)
        self.decline_btn.clicked.connect(self._do_decline)

    def show_call(
        self,
        number: str,
        *,
        name: str = "",
        on_answer: Optional[Callable[[], None]] = None,
        on_decline: Optional[Callable[[], None]] = None,
        subtitle: str = "SIP / modem",
    ) -> None:
        self._on_answer = on_answer
        self._on_decline = on_decline
        display = (name or "").strip() or (number or "").strip() or "Unknown"
        self.who.setText(display)
        bits = []
        if name and number and name.strip() != number.strip():
            bits.append(number.strip())
        if subtitle:
            bits.append(subtitle)
        self.sub.setText(" · ".join(bits))
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.raise_()
        self.show()
        self.answer_btn.setFocus(Qt.OtherFocusReason)
        from esp_handset import digi_nav

        digi_nav.clear_highlights(self)
        digi_nav._highlight(self.answer_btn, True)

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

            dx = -1 if key == Qt.Key_Left else (1 if key == Qt.Key_Right else 0)
            dy = -1 if key == Qt.Key_Up else (1 if key == Qt.Key_Down else 0)
            if dx:
                digi_nav.move_focus_xy(self, dx, 0)
            if dy:
                digi_nav.move_focus_xy(self, 0, dy)
            event.accept()
            return
        super().keyPressEvent(event)
