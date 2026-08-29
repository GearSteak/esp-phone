#!/usr/bin/env python3
"""Mirror the Linux desktop onto Waveshare 2\" ST7789 SPI.

Capture stack (first that yields non-black frames wins):
  1. mss (X11)
  2. Pillow ImageGrab (X11)
  3. ImageMagick `import -window root`
  4. grim (Wayland)
  5. ffmpeg x11grab
  6. Qt QScreen.grabWindow (often solid black on Bookworm Wayland)

Env:
  DISPLAY=:0
  ESP_ST7789_FPS_MS=100
  ESP_MIRROR_KEEP_ASPECT=0   # stretch fill (default)
  ESP_MIRROR_INIT_RETRIES=12
"""

from __future__ import annotations

import glob
import os
import signal
import subprocess
import sys
import time
from typing import Callable, List, Optional, Tuple


def _path_setup() -> None:
    for p in (
        "/opt/esp-handset",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ):
        if p not in sys.path and os.path.isdir(os.path.join(p, "esp_handset")):
            sys.path.insert(0, p)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isdir(os.path.join(repo, "esp_handset")) and repo not in sys.path:
        sys.path.insert(0, repo)


def _avg_luma_qimage(img) -> float:
    try:
        from PyQt5.QtCore import Qt

        sample = img.scaled(12, 12, Qt.IgnoreAspectRatio, Qt.FastTransformation)
        bits = sample.constBits()
        bits.setsize(sample.byteCount())
        raw = bytes(bits)
        if len(raw) < 4:
            return 0.0
        total = 0
        n = 0
        step = 4 if sample.depth() >= 24 else 2
        for i in range(0, min(len(raw), 576), step):
            if step == 4:
                total += raw[i] + raw[i + 1] + raw[i + 2]
                n += 3
            else:
                total += raw[i] + raw[i + 1]
                n += 2
        return total / max(n, 1)
    except Exception:
        return 0.0


def _pil_to_qimage(pil_img):
    from PyQt5.QtGui import QImage

    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")
    w, h = pil_img.size
    data = pil_img.tobytes("raw", "RGB")
    qimg = QImage(data, w, h, w * 3, QImage.Format_RGB888)
    return qimg.copy()


def _png_bytes_to_qimage(data: bytes):
    from PyQt5.QtGui import QImage

    q = QImage()
    if not q.loadFromData(data):
        return None
    return q


def _build_capturers() -> List[Tuple[str, Callable]]:
    from PyQt5.QtGui import QGuiApplication

    caps: List[Tuple[str, Callable]] = []

    def cap_mss():
        try:
            import mss
            from PIL import Image
        except Exception:
            return None
        try:
            with mss.mss() as sct:
                mons = sct.monitors
                if len(mons) < 2:
                    return None
                best = max(mons[1:], key=lambda m: m["width"] * m["height"])
                shot = sct.grab(best)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                return _pil_to_qimage(img)
        except Exception as e:
            print(f"[desktop-mirror] mss: {e}", flush=True)
            return None

    caps.append(("mss", cap_mss))

    def cap_pillow():
        try:
            from PIL import ImageGrab
        except Exception:
            return None
        try:
            img = ImageGrab.grab()
            if img is None:
                return None
            return _pil_to_qimage(img)
        except Exception as e:
            print(f"[desktop-mirror] pillow: {e}", flush=True)
            return None

    caps.append(("pillow", cap_pillow))

    def cap_import():
        for cmd in (
            ["import", "-window", "root", "png:-"],
            ["convert", "x:root", "png:-"],
        ):
            try:
                data = subprocess.check_output(
                    cmd,
                    stderr=subprocess.DEVNULL,
                    timeout=3,
                    env=os.environ.copy(),
                )
                if data:
                    return _png_bytes_to_qimage(data)
            except Exception:
                continue
        return None

    caps.append(("import", cap_import))

    def cap_grim():
        try:
            data = subprocess.check_output(
                ["grim", "-t", "png", "-"],
                stderr=subprocess.DEVNULL,
                timeout=3,
                env=os.environ.copy(),
            )
            if data:
                return _png_bytes_to_qimage(data)
        except Exception:
            return None
        return None

    caps.append(("grim", cap_grim))

    def cap_ffmpeg():
        disp = os.environ.get("DISPLAY", ":0")
        tmp = "/tmp/digivice-mirror-frame.png"
        try:
            # First ask xrandr for real size
            size = os.environ.get("ESP_MIRROR_X11_SIZE", "").strip()
            if not size:
                try:
                    out = subprocess.check_output(
                        ["xrandr", "--current"],
                        stderr=subprocess.DEVNULL,
                        timeout=2,
                        text=True,
                    )
                    for line in out.splitlines():
                        if " connected" in line and " primary " in line:
                            # e.g. HDMI-1 connected primary 1920x1080+0+0
                            parts = line.split()
                            for p in parts:
                                if "x" in p and "+" in p:
                                    size = p.split("+")[0]
                                    break
                        if size:
                            break
                    if not size:
                        for line in out.splitlines():
                            if " connected" in line:
                                for p in line.split():
                                    if "x" in p and "+" in p:
                                        size = p.split("+")[0]
                                        break
                            if size:
                                break
                except Exception:
                    size = "1920x1080"
            if not size:
                size = "1920x1080"
            subprocess.check_call(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-f",
                    "x11grab",
                    "-video_size",
                    size,
                    "-i",
                    f"{disp}.0+0,0",
                    "-frames:v",
                    "1",
                    tmp,
                ],
                timeout=5,
                env=os.environ.copy(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            from PyQt5.QtGui import QImage

            q = QImage(tmp)
            if q.isNull():
                return None
            return q
        except Exception:
            return None

    caps.append(("ffmpeg", cap_ffmpeg))

    def pick_screen():
        screens = list(QGuiApplication.screens() or [])
        if not screens:
            return QGuiApplication.primaryScreen()
        best = None
        best_score = -1.0
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
            if area < 120_000:
                score -= 40_000_000
            if "SPI" in name or "DSI" in name:
                score -= 20_000_000
            if score > best_score:
                best_score = score
                best = s
        return best or QGuiApplication.primaryScreen()

    def cap_qt():
        scr = pick_screen()
        if scr is None:
            return None
        try:
            pix = scr.grabWindow(0)
        except Exception:
            return None
        if pix.isNull():
            return None
        return pix.toImage()

    caps.append(("qt", cap_qt))
    return caps


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
        else:
            for cand in glob.glob("/home/*/.Xauthority"):
                os.environ["XAUTHORITY"] = cand
                break

    _path_setup()

    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QGuiApplication, QPainter, QImage, QColor
    from PyQt5.QtWidgets import QApplication

    from esp_handset import st7789_spi as st

    app = QApplication(sys.argv)

    retries = int(os.environ.get("ESP_MIRROR_INIT_RETRIES", "12"))
    ok = False
    for i in range(max(1, retries)):
        try:
            if st.ready():
                st.close(blank_panel=False)
        except Exception:
            pass
        if st.init():
            ok = True
            break
        print(f"[desktop-mirror] ST7789 init retry {i + 1}/{retries}", flush=True)
        time.sleep(0.4)
    if not ok:
        print("[desktop-mirror] ST7789 init failed", flush=True)
        return 1

    st.wake_display()
    # Blue = SPI works; waiting for a non-black desktop grab
    try:
        st.fill(0, 80, 160)
        time.sleep(0.2)
    except Exception:
        pass

    keep_aspect = os.environ.get("ESP_MIRROR_KEEP_ASPECT", "0").strip() in (
        "1",
        "true",
        "yes",
    )
    interval = int(os.environ.get("ESP_ST7789_FPS_MS", "100"))
    pw, ph = st.size()
    print(
        f"[desktop-mirror] {pw}x{ph} every {interval}ms keep_aspect={keep_aspect} "
        f"DISPLAY={os.environ.get('DISPLAY')} XAUTH={os.environ.get('XAUTHORITY', '?')}",
        flush=True,
    )

    for s in QGuiApplication.screens() or []:
        g = s.geometry()
        print(
            f"[desktop-mirror] qt-screen {s.name()!r} "
            f"{g.width()}x{g.height()} primary={s is QGuiApplication.primaryScreen()}",
            flush=True,
        )

    capturers = _build_capturers()
    state = {"fn": None, "name": None}  # type: ignore

    for name, fn in capturers:
        try:
            img = fn()
        except Exception as e:
            print(f"[desktop-mirror] probe {name}: {e}", flush=True)
            continue
        if img is None or img.isNull():
            print(f"[desktop-mirror] probe {name}: no image", flush=True)
            continue
        luma = _avg_luma_qimage(img)
        print(
            f"[desktop-mirror] probe {name}: {img.width()}x{img.height()} luma≈{luma:.0f}",
            flush=True,
        )
        if luma >= 12:
            state["name"], state["fn"] = name, fn
            break
        if state["fn"] is None:
            state["name"], state["fn"] = name, fn

    if state["fn"] is None:
        print(
            "[desktop-mirror] NO capture backend — "
            "sudo apt install -y python3-mss python3-pil imagemagick",
            flush=True,
        )
        for _ in range(6):
            st.fill(160, 40, 40)
            time.sleep(0.3)
            st.fill(40, 40, 160)
            time.sleep(0.3)
        st.close(blank_panel=False)
        return 1

    print(f"[desktop-mirror] using capture={state['name']}", flush=True)

    running = True
    spi_retry_at = [0.0]

    def stop(*_a) -> None:
        nonlocal running
        running = False
        app.quit()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    frames_ok = [0]
    frames_dark = [0]
    rotate_idx = [0]
    last_log = [0.0]

    def recover_spi() -> None:
        now = time.monotonic()
        if now < spi_retry_at[0]:
            return
        spi_retry_at[0] = now + 1.0
        try:
            if st.recover():
                spi_retry_at[0] = 0.0
                print("[desktop-mirror] SPI recovered", flush=True)
        except Exception as e:
            print(f"[desktop-mirror] SPI recovery failed: {e}", flush=True)

    def paint_frame(src: QImage) -> None:
        if not st.ready():
            recover_spi()
            return
        if keep_aspect:
            scaled = src.scaled(pw, ph, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            out = QImage(pw, ph, QImage.Format_RGB32)
            out.fill(QColor(0, 0, 0))
            p = QPainter(out)
            x = (pw - scaled.width()) // 2
            y = (ph - scaled.height()) // 2
            p.drawImage(x, y, scaled)
            p.end()
            try:
                st.blit_qimage(out)
            except Exception as e:
                print(f"[desktop-mirror] SPI frame: {e}", flush=True)
                st.close(blank_panel=False)
        else:
            scaled = src.scaled(pw, ph, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            try:
                st.blit_qimage(scaled)
            except Exception as e:
                print(f"[desktop-mirror] SPI frame: {e}", flush=True)
                st.close(blank_panel=False)

    def tick() -> None:
        if not running:
            return
        img = None
        try:
            img = state["fn"]()
        except Exception as e:
            now = time.time()
            if now - last_log[0] > 4:
                print(f"[desktop-mirror] capture error: {e}", flush=True)
                last_log[0] = now

        if img is None or img.isNull():
            frames_dark[0] += 1
            if frames_dark[0] % 30 == 0:
                rotate_idx[0] = (rotate_idx[0] + 1) % len(capturers)
                state["name"] = capturers[rotate_idx[0]][0]
                state["fn"] = capturers[rotate_idx[0]][1]
                print(
                    f"[desktop-mirror] rotate capture → {state['name']}",
                    flush=True,
                )
            if frames_dark[0] % 15 == 1:
                st.fill(120, 0, 120)  # magenta = no frame
            return

        luma = _avg_luma_qimage(img)
        if luma < 8:
            frames_dark[0] += 1
            if frames_dark[0] % 40 == 1:
                print(
                    f"[desktop-mirror] dark frame luma={luma:.0f} "
                    f"via {state['name']} — still painting",
                    flush=True,
                )
                rotate_idx[0] = (rotate_idx[0] + 1) % len(capturers)
                state["name"] = capturers[rotate_idx[0]][0]
                state["fn"] = capturers[rotate_idx[0]][1]
            paint_frame(img)
            return

        frames_dark[0] = 0
        frames_ok[0] += 1
        if frames_ok[0] == 1 or frames_ok[0] % 100 == 0:
            print(
                f"[desktop-mirror] content OK via {state['name']} "
                f"luma={luma:.0f} frames={frames_ok[0]}",
                flush=True,
            )
        paint_frame(img)

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
