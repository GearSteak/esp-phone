#!/usr/bin/env python3
"""Always-visible pointer overlay for Digivice desktops.

Pi vc4 hardware cursor is often invisible, especially with SPI dual-head /
cloned ST7789. This draws a bright amber arrow at the mouse position.

  digivice-pointer              # foreground
  digivice-pointer --daemon     # background
"""

from __future__ import annotations

import os
import signal
import sys


def main() -> int:
    os.environ.setdefault("DISPLAY", ":0")
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    if not os.environ.get("XAUTHORITY"):
        for cand in (
            os.path.expanduser("~/.Xauthority"),
            "/home/pi/.Xauthority",
        ):
            if os.path.isfile(cand):
                os.environ["XAUTHORITY"] = cand
                break

    from PyQt5.QtCore import Qt, QTimer, QPoint
    from PyQt5.QtGui import QColor, QPainter, QPolygon, QGuiApplication, QCursor, QPen
    from PyQt5.QtWidgets import QApplication, QWidget

    class Pointer(QWidget):
        def __init__(self) -> None:
            super().__init__(
                None,
                Qt.Tool
                | Qt.FramelessWindowHint
                | Qt.WindowStaysOnTopHint
                | Qt.WindowTransparentForInput
                | Qt.X11BypassWindowManagerHint,
            )
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WA_ShowWithoutActivating, True)
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            # Big enough to see on mirrored 240×320
            self.setFixedSize(40, 48)
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._follow)
            self._timer.start(16)
            self._follow()
            self.show()
            self.raise_()

        def _follow(self) -> None:
            p = QCursor.pos()
            # Hotspot near tip of arrow
            self.move(p.x() - 1, p.y() - 1)
            if not self.isVisible():
                self.show()
            self.raise_()

        def paintEvent(self, _e) -> None:  # noqa: N802
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            tip = QPolygon(
                [
                    QPoint(2, 2),
                    QPoint(2, 38),
                    QPoint(12, 28),
                    QPoint(18, 44),
                    QPoint(24, 41),
                    QPoint(16, 26),
                    QPoint(34, 26),
                ]
            )
            # Thick black outline for contrast / color-vision friendly
            p.setPen(QPen(QColor(0, 0, 0, 255), 3))
            p.setBrush(QColor(255, 230, 0, 255))  # bright yellow
            p.drawPolygon(tip)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    win = Pointer()
    win.show()
    print(
        f"[pointer] software cursor on DISPLAY={os.environ.get('DISPLAY')} "
        f"XAUTH={os.environ.get('XAUTHORITY', '?')}",
        flush=True,
    )

    def stop(*_a) -> None:
        app.quit()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    return int(app.exec_() or 0)


if __name__ == "__main__":
    # Optional background wrapper
    if "--daemon" in sys.argv:
        if os.fork():
            sys.exit(0)
    sys.exit(main())
