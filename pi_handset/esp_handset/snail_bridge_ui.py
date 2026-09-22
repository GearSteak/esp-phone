"""Digivice UI — start Snail companion bridge and show LAN URL / QR."""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtWidgets import (
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from esp_handset import snail_bridge
from esp_handset.pages import page_chrome


def _qr_pixmap(text: str, size: int = 140) -> Optional[QPixmap]:
    try:
        import qrcode

        img = qrcode.make(text)
        if hasattr(img, "get_image"):
            pil = img.get_image().convert("RGB")
        else:
            pil = img.convert("RGB")
        data = pil.tobytes("raw", "RGB")
        qimg = QImage(data, pil.size[0], pil.size[1], QImage.Format_RGB888)
        return QPixmap.fromImage(qimg).scaled(
            size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
    except Exception:
        return None


class SnailLinkPage(QWidget):
    def __init__(self, on_back: Callable[[], None]) -> None:
        super().__init__()
        self._on_back = on_back
        self.setProperty("digiTitle", "Snail Link")

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 2, 4, 4)
        root.setSpacing(4)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-size:12px; color:#e8eef5;")
        root.addWidget(self._status)

        self._url = QLabel("")
        self._url.setWordWrap(True)
        self._url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._url.setStyleSheet(
            "font-size:11px; color:#FFE600; font-family:monospace;"
        )
        root.addWidget(self._url)

        self._qr = QLabel("QR")
        self._qr.setAlignment(Qt.AlignCenter)
        self._qr.setMinimumHeight(120)
        self._qr.setStyleSheet("background:#0a1018; border:1px solid #3a5068;")
        root.addWidget(self._qr, 1)

        self._hint = QLabel(
            "X3 + Snail OS: put digivice.lua on the SD card,\n"
            "set HOST to this URL, same Wi‑Fi as Digivice.\n"
            "Snail fetch is HTTPS — try HTTP first; see docs."
        )
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("font-size:10px; color:#8a9aaa;")
        root.addWidget(self._hint)

        self._btn = QPushButton("Start bridge")
        self._btn.setMinimumHeight(40)
        self._btn.setFocusPolicy(Qt.StrongFocus)
        self._btn.clicked.connect(self._toggle)
        self._btn.digi_confirm = self._toggle  # type: ignore[attr-defined]
        root.addWidget(self._btn)

        self._tick = QTimer(self)
        self._tick.setInterval(2000)
        self._tick.timeout.connect(self._refresh)
        self._refresh()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._tick.start()
        self._refresh()
        QTimer.singleShot(0, lambda: self._btn.setFocus(Qt.OtherFocusReason))

    def hideEvent(self, event) -> None:  # noqa: N802
        self._tick.stop()
        super().hideEvent(event)

    def _toggle(self) -> bool:
        if snail_bridge.is_running():
            snail_bridge.stop()
        else:
            try:
                # Prefer HTTP for LAN; TLS if certs already present and env wants it
                use_tls = snail_bridge.tls_ready() and False  # HTTP first
                snail_bridge.start(tls=use_tls)
            except Exception as e:
                self._status.setText(f"Start failed: {e}")
                return True
        self._refresh()
        return True

    def _refresh(self) -> None:
        running = snail_bridge.is_running()
        url = snail_bridge.base_url() if running else (
            f"http://{snail_bridge.lan_ip()}:{snail_bridge.DEFAULT_PORT}"
        )
        if running:
            self._status.setText("Bridge ON · X3 can fetch inbox/status")
            self._btn.setText("Stop bridge")
            n = len(snail_bridge.inbox_payload().get("items") or [])
            self._hint.setText(
                f"{n} notifs ready · HOST in digivice.lua =\n{url}"
            )
        else:
            self._status.setText("Bridge OFF · Confirm Start on Digivice")
            self._btn.setText("Start bridge")
        self._url.setText(url)
        pm = _qr_pixmap(url)
        if pm is not None:
            self._qr.setPixmap(pm)
            self._qr.setText("")
        else:
            self._qr.setPixmap(QPixmap())
            self._qr.setText("Install qrcode for QR\n(URL above is enough)")


def make_snail_link_page(on_back: Callable[[], None]) -> QWidget:
    body = SnailLinkPage(on_back)
    return page_chrome("Snail Link", body, on_back, scroll=False)
