#!/usr/bin/env python3
"""Mirror the Linux desktop (X11) onto Waveshare 2\" ST7789 SPI.

Same idea as Instructables ST7789 desktop mirror / fbcp:
  capture primary (or full) screen → scale KeepAspectRatio → SPI RGB565.

Used while Digivice is NOT running (handset-desktop). Digivice owns SPI
while phone UI is up; this takes over when you leave for the desktop.

  digivice-desktop-mirror          # run in foreground
  digivice-desktop-mirror --daemon # background

Env:
  DISPLAY=:0
  ESP_ST7789_FPS_MS=80
  ESP_MIRROR_KEEP_ASPECT=1   # letterbox (default); 0 = stretch fill
"""

from __future__ import annotations

import os
import signal
import sys
import time


def main() -> int:
    os.environ.setdefault("DISPLAY", ":0")
    # PYTHONPATH: installed tree or repo
    for p in (
        "/opt/esp-handset",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ):
        if p not in sys.path and os.path.isdir(os.path.join(p, "esp_handset")):
            sys.path.insert(0, p)
        elif p not in sys.path and os.path.isdir(p) and os.path.isdir(
            os.path.join(p, "esp_handset")
        ):
            sys.path.insert(0, p)

    # Resolve package root when running from session/
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isdir(os.path.join(repo, "esp_handset")) and repo not in sys.path:
        sys.path.insert(0, repo)

    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QGuiApplication, QPainter, QImage, QColor
    from PyQt5.QtWidgets import QApplication

    from esp_handset import st7789_spi as st

    app = QApplication(sys.argv)
    if not st.init():
        print(
            "[desktop-mirror] ST7789 init failed — need spidev userspace path",
            flush=True,
        )
        return 1
    st.wake_display()

    keep_aspect = os.environ.get("ESP_MIRROR_KEEP_ASPECT", "1").strip() not in (
        "0",
        "false",
        "no",
    )
    interval = int(os.environ.get("ESP_ST7789_FPS_MS", "80"))
    pw, ph = st.size()
    print(
        f"[desktop-mirror] {pw}x{ph} every {interval}ms keep_aspect={keep_aspect}",
        flush=True,
    )

    running = True

    def stop(*_a) -> None:
        nonlocal running
        running = False
        app.quit()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def tick() -> None:
        if not running:
            return
        scr = QGuiApplication.primaryScreen()
        if scr is None:
            return
        # Full primary desktop capture (HDMI workspace)
        pix = scr.grabWindow(0)
        if pix.isNull():
            return
        src = pix.toImage()
        if src.isNull():
            return
        if keep_aspect:
            scaled = src.scaled(
                pw, ph, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            out = QImage(pw, ph, QImage.Format_RGB32)
            out.fill(QColor(0, 0, 0))
            p = QPainter(out)
            x = (pw - scaled.width()) // 2
            y = (ph - scaled.height()) // 2
            p.drawImage(x, y, scaled)
            p.end()
            st.blit_qimage(out)
        else:
            scaled = src.scaled(
                pw, ph, Qt.IgnoreAspectRatio, Qt.SmoothTransformation
            )
            st.blit_qimage(scaled)

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(interval)
    tick()  # first frame immediately

    code = app.exec_()
    try:
        st.close(blank_panel=False)
    except Exception:
        pass
    return int(code) if code else 0


if __name__ == "__main__":
    raise SystemExit(main())
