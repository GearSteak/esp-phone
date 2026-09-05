"""Scan / eject Digivice paper (license) carts."""

from __future__ import annotations

import time
from typing import Callable, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QImage, QPixmap, QFont
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from esp_handset import license_cart, pi_camera
from esp_handset.pages import page_chrome
from esp_handset.ui_font import font_family


def decode_qr_rgb(rgb: bytes, width: int, height: int) -> Optional[str]:
    """Best-effort QR decode from RGB888 bytes."""
    if not rgb or width < 16 or height < 16:
        return None
    # pyzbar
    try:
        from pyzbar.pyzbar import decode as zbar_decode
        from PIL import Image

        img = Image.frombytes("RGB", (width, height), rgb)
        for obj in zbar_decode(img):
            data = obj.data.decode("utf-8", errors="replace").strip()
            if data:
                return data
    except Exception:
        pass
    # OpenCV
    try:
        import numpy as np
        import cv2

        arr = np.frombuffer(rgb, dtype=np.uint8).reshape((height, width, 3))
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        det = cv2.QRCodeDetector()
        text, _pts, _ = det.detectAndDecode(bgr)
        if text and str(text).strip():
            return str(text).strip()
    except Exception:
        pass
    return None


class _FrameBridge(QObject):
    frame = pyqtSignal(bytes, int, int)
    error = pyqtSignal(str)


class LicenseCartPage(QWidget):
    def __init__(self, on_back: Callable[[], None]) -> None:
        super().__init__()
        self._on_back = on_back
        self.setProperty("digiTitle", "Paper Cart")
        self._live: Optional[pi_camera.LivePreview] = None
        self._bridge = _FrameBridge(self)
        self._bridge.frame.connect(self._on_frame)
        self._bridge.error.connect(self._on_cam_error)
        self._last_decode_at = 0.0
        self._armed = True

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 2, 4, 4)
        root.setSpacing(4)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-size:12px; color:#e8eef5;")
        root.addWidget(self._status)

        self._preview = QLabel("Camera preview")
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setMinimumHeight(110)
        self._preview.setStyleSheet(
            "background:#0a1018; border:2px solid #3a5068; color:#9ab; font-size:11px;"
        )
        root.addWidget(self._preview, 1)

        self._code = QLineEdit()
        self._code.setPlaceholderText("Or type DIGIVICE-CARD:…")
        self._code.setFocusPolicy(Qt.StrongFocus)
        self._code.setFont(QFont(font_family(), 10))
        root.addWidget(self._code)

        row = QHBoxLayout()
        self._scan_btn = QPushButton("Scan / Insert")
        self._scan_btn.setFocusPolicy(Qt.StrongFocus)
        self._scan_btn.setMinimumHeight(36)
        self._scan_btn.clicked.connect(self._insert_typed)
        self._scan_btn.digi_confirm = self._insert_typed  # type: ignore[attr-defined]
        row.addWidget(self._scan_btn, 1)

        self._eject_btn = QPushButton("Eject")
        self._eject_btn.setFocusPolicy(Qt.StrongFocus)
        self._eject_btn.setMinimumHeight(36)
        self._eject_btn.clicked.connect(self._eject)
        self._eject_btn.digi_confirm = self._eject  # type: ignore[attr-defined]
        row.addWidget(self._eject_btn, 1)
        root.addLayout(row)

        self._hint = QLabel(
            "USB movie carts still plug into the case USB.\n"
            "Paper cards unlock local ROMs — eject to swap."
        )
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("font-size:10px; color:#7a8a9a;")
        root.addWidget(self._hint)

        self._refresh_status()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._refresh_status()
        QTimer.singleShot(80, self._start_camera)
        QTimer.singleShot(0, self._ensure_focus)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._stop_camera()
        super().hideEvent(event)

    def _ensure_focus(self) -> None:
        try:
            from esp_handset import digi_nav

            digi_nav.clear_highlights(self.window() if self.window() else self)
            target = self._eject_btn if license_cart.is_inserted() else self._scan_btn
            target.setFocus(Qt.OtherFocusReason)
            digi_nav._highlight(target, True)
        except Exception:
            self._scan_btn.setFocus(Qt.OtherFocusReason)

    def _refresh_status(self) -> None:
        act = license_cart.active()
        if act is None:
            self._status.setText("No paper cart · scan QR to insert")
            self._eject_btn.setEnabled(False)
        else:
            self._status.setText(f"Inserted: {act.title}\nEject before another card.")
            self._eject_btn.setEnabled(True)

    def _start_camera(self) -> None:
        if self._live is not None and self._live.running:
            return
        self._live = pi_camera.LivePreview(width=320, height=240, fps=5.0)

        def on_frame(rgb: bytes, w: int, h: int) -> None:
            self._bridge.frame.emit(rgb, int(w), int(h))

        def on_error(msg: str) -> None:
            self._bridge.error.emit(msg)

        ok = self._live.start(on_frame, on_error)
        if not ok:
            self._preview.setText(
                "No camera — type the card code below\n"
                "(demo payload is on the printout)."
            )

    def _stop_camera(self) -> None:
        if self._live is not None:
            try:
                self._live.stop()
            except Exception:
                pass
            self._live = None

    def _on_cam_error(self, msg: str) -> None:
        self._preview.setText(msg[:120])

    def _on_frame(self, rgb: bytes, w: int, h: int) -> None:
        try:
            img = QImage(rgb, w, h, w * 3, QImage.Format_RGB888)
            if not img.isNull():
                pm = QPixmap.fromImage(img)
                self._preview.setPixmap(
                    pm.scaled(
                        self._preview.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )
                self._preview.setText("")
        except Exception:
            pass
        now = time.time()
        if not self._armed or now - self._last_decode_at < 0.85:
            return
        self._last_decode_at = now
        text = decode_qr_rgb(rgb, w, h)
        if not text:
            return
        if license_cart.PAYLOAD_PREFIX not in text:
            return
        self._try_insert(text, from_camera=True)

    def _insert_typed(self) -> bool:
        text = self._code.text().strip()
        if not text:
            # Convenience: fill demo payload for first-time test
            text = license_cart.demo_payload()
            self._code.setText(text)
        return self._try_insert(text, from_camera=False)

    def _try_insert(self, text: str, *, from_camera: bool) -> bool:
        try:
            card = license_cart.insert_from_payload(text)
        except ValueError as e:
            self._status.setText(str(e))
            return True
        self._armed = False
        self._code.setText(license_cart.encode_payload(card.id, secret=card.secret))
        self._refresh_status()
        self._status.setText(
            f"Inserted: {card.title}\n"
            f"{len(card.games)} game(s) · Apps opens cart menu"
        )
        try:
            from esp_handset.buzzer import beep_async

            beep_async("ok")
        except Exception:
            pass
        # Re-arm after a beat so the same QR doesn't spam
        QTimer.singleShot(2500, lambda: setattr(self, "_armed", True))
        if from_camera:
            self._code.clear()
            self._code.setPlaceholderText(f"Active: {card.id}")
        return True

    def _eject(self) -> bool:
        if not license_cart.is_inserted():
            self._status.setText("Nothing to eject")
            return True
        title = license_cart.active_title()
        license_cart.eject()
        self._refresh_status()
        self._status.setText(f"Ejected: {title}")
        self._armed = True
        try:
            from esp_handset.buzzer import beep_async

            beep_async("nav")
        except Exception:
            pass
        return True


def make_license_cart_page(on_back: Callable[[], None]) -> QWidget:
    body = LicenseCartPage(on_back)
    return page_chrome("Paper Cart", body, on_back, scroll=False)
