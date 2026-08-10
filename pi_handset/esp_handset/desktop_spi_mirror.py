#!/usr/bin/env python3
"""Mirror the Linux desktop (X11) onto Waveshare 2\" ST7789 SPI.

Same idea as Instructables ST7789 desktop mirror / fbcp:
  capture primary (or best) screen → scale KeepAspectRatio → SPI RGB565.

Used while Digivice is NOT running (handset-desktop). Digivice owns SPI
while phone UI is up; this takes over when you leave for the desktop.

  digivice-desktop-mirror          # run in foreground
  digivice-desktop-mirror --daemon # background

Env:
  DISPLAY=:0
  ESP_ST7789_FPS_MS=80
  ESP_MIRROR_KEEP_ASPECT=1   # letterbox (default); 0 = stretch fill
  ESP_MIRROR_INIT_RETRIES=8
"""

from __future__ import annotations

import os
import signal
import sys
import time


def main() -> int:
    os.environ.setdefault("DISPLAY", ":0")
    for p in (
        "/opt/esp-handset",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ):
        if p not in sys.path and os.path.isdir(os.path.join(p, "esp_handset")):
            sys.path.insert(0, p)

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isdir(os.path.join(repo, "esp_handset")) and repo not in sys.path:
        sys.path.insert(0, repo)

    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QGuiApplication, QPainter, QImage, QColor
    from PyQt5.QtWidgets import QApplication

    from esp_handset import st7789_spi as st

    app = QApplication(sys.argv)

    retries = int(os.environ.get("ESP_MIRROR_INIT_RETRIES", "8"))
    ok = False
    for i in range(max(1, retries)):
        # Force re-open SPI if previous Digivice process died mid-handoff
        try:
            if st.ready():
                st.close(blank_panel=False)
        except Exception:
            pass
        if st.init():
            ok = True
            break
        print(f"[desktop-mirror] ST7789 init retry {i + 1}/{retries}", flush=True)
        time.sleep(0.5)
    if not ok:
        print(
            "[desktop-mirror] ST7789 init failed — need spidev userspace path "
            "(sudo digivice-install-spi-userspace)",
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
        f"[desktop-mirror] {pw}x{ph} every {interval}ms keep_aspect={keep_aspect} "
        f"DISPLAY={os.environ.get('DISPLAY', '?')}",
        flush=True,
    )

    running = True

    def stop(*_a) -> None:
        nonlocal running
        running = False
        app.quit()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def pick_screen():
        """Prefer large HDMI head over tiny SPI DRM panel if both exist."""
        screens = list(QGuiApplication.screens() or [])
        if not screens:
            return QGuiApplication.primaryScreen()
        best = None
        best_score = -1
        for s in screens:
            try:
                g = s.geometry()
                area = max(0, g.width()) * max(0, g.height())
            except Exception:
                continue
            if area < 100:
                continue
            name = (s.name() or "").upper()
            score = float(area)
            if "HDMI" in name or "DISPLAYPORT" in name or name.startswith("DP"):
                score += 50_000_000
            # Deprioritize tiny panel-like DRM heads (userspace SPI shouldn't appear)
            if area < 120_000:
                score -= 40_000_000
            if "SPI" in name or "UNKNOWN" in name or "DSI" in name:
                score -= 20_000_000
            if score > best_score:
                best_score = score
                best = s
        return best or QGuiApplication.primaryScreen()

    _last_log = [0.0]
    _blank_streak = [0]

    def tick() -> None:
        if not running:
            return
        scr = pick_screen()
        if scr is None:
            return
        try:
            pix = scr.grabWindow(0)
        except Exception as e:
            now = time.time()
            if now - _last_log[0] > 5:
                print(f"[desktop-mirror] grab failed: {e}", flush=True)
                _last_log[0] = now
            return
        if pix.isNull():
            _blank_streak[0] += 1
            if _blank_streak[0] == 10 or _blank_streak[0] % 50 == 0:
                print(
                    f"[desktop-mirror] null grab screen={scr.name()} "
                    f"geo={scr.geometry().width()}x{scr.geometry().height()}",
                    flush=True,
                )
            return
        src = pix.toImage()
        if src.isNull():
            return
        # Detect near-black captures (HDMI not modeset yet) — still blit so panel wakes
        try:
            sample = src.scaled(8, 8, Qt.IgnoreAspectRatio, Qt.FastTransformation)
            # average luminance rough
            bits = sample.constBits()
            bits.setsize(sample.byteCount())
            raw = bytes(bits)
            if len(raw) >= 4:
                # RGB32 samples
                total = 0
                n = 0
                for i in range(0, min(len(raw), 256), 4):
                    total += raw[i] + raw[i + 1] + raw[i + 2]
                    n += 1
                avg = total / max(n, 1)
                if avg < 8:
                    _blank_streak[0] += 1
                    if _blank_streak[0] in (15, 60):
                        print(
                            f"[desktop-mirror] near-black desktop "
                            f"screen={scr.name()} — is X drawing? xrandr --auto?",
                            flush=True,
                        )
                else:
                    if _blank_streak[0] > 10:
                        print("[desktop-mirror] content OK", flush=True)
                    _blank_streak[0] = 0
        except Exception:
            pass

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

    # Log screens once
    for s in QGuiApplication.screens() or []:
        g = s.geometry()
        print(
            f"[desktop-mirror] screen name={s.name()!r} "
            f"{g.width()}x{g.height()}@{g.x()},{g.y()} "
            f"primary={s is QGuiApplication.primaryScreen()}",
            flush=True,
        )

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(interval)
    tick()

    code = app.exec_()
    try:
        st.close(blank_panel=False)
    except Exception:
        pass
    return int(code or 0)


if __name__ == "__main__":
    sys.exit(main())
