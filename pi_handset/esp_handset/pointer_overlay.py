#!/usr/bin/env python3
"""Always-visible pointer overlay for Digivice desktops.

Pi vc4 hardware cursor is often completely invisible. This draws a bright
arrow at the real mouse position (X11 / Qt). Started by handset-desktop.

  digivice-pointer              # foreground
  digivice-pointer --daemon     # background
"""

from __future__ import annotations

import os
import signal
import sys


def main() -> int:
    os.environ.setdefault("DISPLAY", ":0")
    # Prefer X11 so this works as an overlay on the desk
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

    from PyQt5.QtCore import Qt, QTimer, QPoint
    from PyQt5.QtGui import QColor, QPainter, QPolygon, QGuiApplication, QCursor
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
            self.setFixedSize(28, 32)
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._follow)
            self._timer.start(16)
            self._follow()
            self.show()

        def _follow(self) -> None:
            p = QCursor.pos()
            # Hotspot near tip of arrow
            self.move(p.x(), p.y())

        def paintEvent(self, _e) -> None:  # noqa: N802
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            # Bright high-contrast “cursor” shape
            tip = QPolygon(
                [
                    QPoint(1, 1),
                    QPoint(1, 26),
                    QPoint(8, 20),
                    QPoint(14, 30),
                    QPoint(18, 28),
                    QPoint(12, 18),
                    QPoint(22, 18),
                ]
            )
            p.setPen(QColor(0, 0, 0, 220))
            p.setBrush(QColor(255, 220, 40, 245))  # amber
            p.drawPolygon(tip)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    win = Pointer()
    win.show()

    def stop(*_a) -> None:
        app.quit()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    return int(app.exec_())


if __name__ == "__main__":
    # daemonize?
    if "--daemon" in sys.argv:
        if os.fork() != 0:
            raise SystemExit(0)
        os.setsid()
        if os.fork() != 0:
            raise SystemExit(0)
        sys.argv = [a for a in sys.argv if a != "--daemon"]
    raise SystemExit(main())
