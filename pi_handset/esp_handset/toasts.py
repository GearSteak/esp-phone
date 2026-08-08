"""Top-of-screen toast notifications."""

from __future__ import annotations

from typing import List, Optional

from PyQt5.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QTimer,
    Qt,
)
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class ToastBanner(QFrame):
    def __init__(self, parent: QWidget, title: str, body: str):
        super().__init__(parent)
        self.setObjectName("toastBanner")
        self.setStyleSheet(
            """
            #toastBanner {
                background: rgba(22, 32, 48, 0.96);
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 8px;
            }
            QLabel#toastTitle {
                color: #f2f6fb;
                font-weight: 700;
                font-size: 10px;
                background: transparent;
                border: none;
            }
            QLabel#toastBody {
                color: #b8c5d6;
                font-size: 9px;
                background: transparent;
                border: none;
            }
            """
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("toastTitle")
        b = QLabel(body)
        b.setObjectName("toastBody")
        b.setWordWrap(True)
        lay.addWidget(t)
        lay.addWidget(b)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, _e):  # noqa: N802
        host = self.parent()
        if hasattr(host, "dismiss_toast"):
            host.dismiss_toast(self)  # type: ignore[attr-defined]


class ToastHost(QWidget):
    """Floating stack of toasts anchored under the top edge."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._toasts: List[ToastBanner] = []
        self._anims: List[QPropertyAnimation] = []
        self.hide()

    def show_toast(self, title: str, body: str, ms: int = 3500) -> None:
        parent = self.parent()
        if not isinstance(parent, QWidget):
            return
        self.raise_()
        self.show()

        banner = ToastBanner(self, title, body[:120])
        banner.adjustSize()
        parent_w = parent.width()
        width = min(parent_w - 8, parent_w - 4 if parent_w < 280 else 420)
        banner.setFixedWidth(max(width, 100))
        banner.adjustSize()
        h = max(banner.sizeHint().height(), 36)
        banner.resize(banner.width(), h)

        # Host only covers the toast stack region (clicks pass elsewhere)
        self._sync_host_geometry(parent)
        x = (self.width() - width) // 2
        banner.move(x, -h - 8)
        banner.show()
        self._toasts.insert(0, banner)
        self._relayout(animate_new=banner)

        QTimer.singleShot(ms, lambda b=banner: self.dismiss_toast(b))

    def _sync_host_geometry(self, parent: QWidget) -> None:
        # Tall enough for a few stacked toasts under the status bar
        height = 44
        for b in self._toasts:
            height += b.height() + 8
        height = max(height, 160)
        self.setGeometry(0, 0, parent.width(), height)

    def dismiss_toast(self, banner: ToastBanner) -> None:
        if banner not in self._toasts:
            return
        self._toasts.remove(banner)
        end = QPoint(banner.x(), -banner.height() - 12)
        anim = QPropertyAnimation(banner, b"pos", self)
        anim.setDuration(220)
        anim.setStartValue(banner.pos())
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.InCubic)
        anim.finished.connect(banner.deleteLater)
        anim.start()
        self._anims.append(anim)
        parent = self.parent()
        if isinstance(parent, QWidget):
            self._sync_host_geometry(parent)
        self._relayout(animate_new=None)
        if not self._toasts:
            QTimer.singleShot(250, self.hide)

    def _relayout(self, animate_new: Optional[ToastBanner]) -> None:
        y = 22  # below Digivice status bar
        gap = 4
        for banner in self._toasts:
            x = (self.width() - banner.width()) // 2
            target = QPoint(x, y)
            anim = QPropertyAnimation(banner, b"pos", self)
            anim.setDuration(280)
            anim.setStartValue(banner.pos())
            anim.setEndValue(target)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start()
            self._anims.append(anim)
            y += banner.height() + gap

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        parent = self.parent()
        if isinstance(parent, QWidget) and self.isVisible():
            self._sync_host_geometry(parent)
            self._relayout(animate_new=None)
