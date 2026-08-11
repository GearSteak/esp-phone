"""Userspace ST7789 (Waveshare 2\" 240×320) over SPI0 CE0.

Same model as the Instructables / fbcp approach:
  Digivice (or desktop) paints somewhere X can see → we push RGB565 frames
  over SPI to the panel, without mipi-dbi-spi DRM owning the bus.

Wiring (BCM): MOSI=10 SCLK=11 CE0=8 DC=25 RST=27 BL=18
Requires: python3-spidev, RPi.GPIO (or lgpio), spidev free
  (dtoverlay=mipi-dbi-spi must be OFF — it disables spidev@0)

Env:
  ESP_ST7789_SPI_BUS=0 ESP_ST7789_SPI_DEV=0 ESP_ST7789_SPEED=40000000
  ESP_ST7789_DC=25 ESP_ST7789_RST=27 ESP_ST7789_BL=18
"""

from __future__ import annotations

import os
import time
from typing import Optional, Tuple

# Lazy hardware — import fails gracefully off-Pi
_spi = None
_gpio = None
_ok = False
_wh: Tuple[int, int] = (240, 320)
_lockf = None  # exclusive flock so two processes never garble SPI


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _rotation_madctl() -> int:
    """MADCTL from /etc/esp-handset/panel-rotation or ESP_PANEL_ROTATION."""
    env = os.environ.get("ESP_PANEL_ROTATION", "").strip()
    if not env:
        try:
            env = open("/etc/esp-handset/panel-rotation", encoding="utf-8").read().strip()
        except OSError:
            env = "180"
    # ST7789 MADCTL values (common Waveshare mappings)
    return {
        "0": 0x00,
        "90": 0x60,
        "180": 0xC0,
        "270": 0xA0,
    }.get(env, 0xC0)


def _gpio_setup(dc: int, rst: int, bl: int) -> bool:
    global _gpio
    try:
        import RPi.GPIO as GPIO  # type: ignore

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for p in (dc, rst, bl):
            GPIO.setup(p, GPIO.OUT)
            GPIO.output(p, 0)
        _gpio = GPIO
        return True
    except Exception as e:
        print(f"[st7789] RPi.GPIO failed: {e}", flush=True)
        return False


def _cmd(dc: int, b: int) -> None:
    _gpio.output(dc, 0)
    _spi.xfer2([b & 0xFF])


def _data(dc: int, buf) -> None:
    _gpio.output(dc, 1)
    # chunk large buffers
    if isinstance(buf, (bytes, bytearray)):
        mv = memoryview(buf)
        n = len(mv)
        step = 4096
        for i in range(0, n, step):
            _spi.xfer2(list(mv[i : i + step]))
    else:
        _spi.xfer2(list(buf) if not isinstance(buf, list) else buf)


def _data_bytes(dc: int, data: bytes) -> None:
    _gpio.output(dc, 1)
    step = 4096
    for i in range(0, len(data), step):
        _spi.writebytes2(data[i : i + step])


def init() -> bool:
    """Open SPI + GPIO and run ST7789 init. Returns True if ready."""
    global _spi, _ok, _wh, _lockf
    if _ok:
        return True

    bus = _env_int("ESP_ST7789_SPI_BUS", 0)
    dev = _env_int("ESP_ST7789_SPI_DEV", 0)
    speed = _env_int("ESP_ST7789_SPEED", 40_000_000)
    dc = _env_int("ESP_ST7789_DC", 25)
    rst = _env_int("ESP_ST7789_RST", 27)
    bl = _env_int("ESP_ST7789_BL", 18)

    madctl = _rotation_madctl()
    if madctl in (0x60, 0xA0):
        _wh = (320, 240)
    else:
        _wh = (240, 320)

    # One owner of the SPI panel — dual Digivice/mirror = static snow
    # Prefer /tmp (user-writable); /run often root-only on stock Pi OS.
    try:
        import fcntl

        lock_path = os.environ.get("ESP_ST7789_LOCK", "").strip()
        if not lock_path:
            for cand in ("/tmp/digivice-st7789.lock", "/run/digivice-st7789.lock"):
                try:
                    _lockf = open(cand, "w")
                    lock_path = cand
                    break
                except OSError:
                    _lockf = None
        else:
            _lockf = open(lock_path, "w")
        if _lockf is not None:
            try:
                fcntl.flock(_lockf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print(
                    "[st7789] SPI already owned by another process "
                    "(kill other handset_app / desktop_spi_mirror)",
                    flush=True,
                )
                try:
                    _lockf.close()
                except Exception:
                    pass
                _lockf = None
                return False
            _lockf.write(f"{os.getpid()}\n")
            _lockf.flush()
    except Exception as e:
        print(f"[st7789] lock warn: {e}", flush=True)
        _lockf = None

    if not _gpio_setup(dc, rst, bl):
        return False

    try:
        import spidev  # type: ignore

        _spi = spidev.SpiDev()
        try:
            _spi.open(bus, dev)
        except OSError as e:
            # Busy after Digivice kill — brief wait and re-open once
            print(f"[st7789] SPI open busy ({e}); retry…", flush=True)
            time.sleep(0.6)
            try:
                _spi.close()
            except Exception:
                pass
            _spi = spidev.SpiDev()
            _spi.open(bus, dev)
        _spi.max_speed_hz = speed
        _spi.mode = 0
        _spi.lsbfirst = False
        # Prefer writebytes2 when available
        if not hasattr(_spi, "writebytes2"):
            _spi.writebytes2 = lambda b: _spi.xfer2(list(b))  # type: ignore
    except Exception as e:
        print(
            f"[st7789] SPI open failed ({e}). "
            "Is dtoverlay=mipi-dbi-spi disabled so /dev/spidev0.0 exists?",
            flush=True,
        )
        return False

    # Hardware reset
    _gpio.output(rst, 0)
    time.sleep(0.05)
    _gpio.output(rst, 1)
    time.sleep(0.12)

    def c(cmd: int, *params: int) -> None:
        _cmd(dc, cmd)
        if params:
            _gpio.output(dc, 1)
            _spi.xfer2(list(params))

    c(0x01)
    time.sleep(0.15)
    c(0x11)
    time.sleep(0.12)
    c(0x36, madctl)
    c(0x3A, 0x05)  # RGB565 — Instructables / Waveshare SPI path
    c(0xB2, 0x0C, 0x0C, 0x00, 0x33, 0x33)
    c(0xB7, 0x35)
    c(0xBB, 0x19)
    c(0xC0, 0x2C)
    c(0xC2, 0x01)
    c(0xC3, 0x12)
    c(0xC4, 0x20)
    c(0xC6, 0x0F)
    c(0xD0, 0xA4, 0xA1)
    c(
        0xE0,
        0xD0,
        0x04,
        0x0D,
        0x11,
        0x13,
        0x2B,
        0x3F,
        0x54,
        0x4C,
        0x18,
        0x0D,
        0x0B,
        0x1F,
        0x23,
    )
    c(
        0xE1,
        0xD0,
        0x04,
        0x0C,
        0x11,
        0x13,
        0x2C,
        0x3F,
        0x44,
        0x51,
        0x2F,
        0x1F,
        0x1F,
        0x20,
        0x23,
    )
    c(0x21)
    c(0x13)
    c(0x29)
    time.sleep(0.05)

    _gpio.output(bl, 1)
    _ok = True
    print(
        f"[st7789] userspace ready SPI{bus}.{dev} {_wh[0]}x{_wh[1]} "
        f"MADCTL=0x{madctl:02x} DC={dc} RST={rst} BL={bl}",
        flush=True,
    )
    return True


def size() -> Tuple[int, int]:
    return _wh


def ready() -> bool:
    return _ok


def _set_window(dc: int, x0: int, y0: int, x1: int, y1: int) -> None:
    def c(cmd: int, *params: int) -> None:
        _cmd(dc, cmd)
        if params:
            _gpio.output(dc, 1)
            _spi.xfer2(list(params))

    c(0x2A, (x0 >> 8) & 0xFF, x0 & 0xFF, (x1 >> 8) & 0xFF, x1 & 0xFF)
    c(0x2B, (y0 >> 8) & 0xFF, y0 & 0xFF, (y1 >> 8) & 0xFF, y1 & 0xFF)
    c(0x2C)


def blit_qimage(img) -> None:
    """Push a QImage (any format) scaled to panel as RGB565 SPI DMA-ish write."""
    if not _ok:
        return
    from PyQt5.QtGui import QImage
    from PyQt5.QtCore import Qt

    dc = _env_int("ESP_ST7789_DC", 25)
    w, h = _wh
    if img.isNull():
        return
    if img.width() != w or img.height() != h:
        img = img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    img = img.convertToFormat(QImage.Format_RGB16)
    # Qt RGB16 is RGB565 little-endian host; ST7789 wants big-endian on wire often
    ptr = img.bits()
    ptr.setsize(img.byteCount())
    raw = bytes(ptr)
    # Swap bytes for SPI ST7789 (high byte first)
    ba = bytearray(len(raw))
    for i in range(0, len(raw), 2):
        ba[i] = raw[i + 1]
        ba[i + 1] = raw[i]

    _set_window(dc, 0, 0, w - 1, h - 1)
    _gpio.output(dc, 1)
    step = 4096
    for i in range(0, len(ba), step):
        _spi.writebytes2(ba[i : i + step])


def fill(r: int, g: int, b: int) -> None:
    if not _ok:
        return
    from PyQt5.QtGui import QImage

    w, h = _wh
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill((0xFF << 24) | ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF))
    blit_qimage(img)


def blank(*, backlight_off: bool = True) -> None:
    """Clear last Digivice frame (ST7789 keeps RAM until overwritten)."""
    if not _ok:
        # try init just to blank (desktop exit may have closed already)
        if not init():
            return
    try:
        fill(0, 0, 0)
    except Exception as e:
        print(f"[st7789] blank fill: {e}", flush=True)
    # Display off + sleep optional; then backlight
    dc = _env_int("ESP_ST7789_DC", 25)
    bl = _env_int("ESP_ST7789_BL", 18)
    try:
        _cmd(dc, 0x28)  # DISPOFF
        time.sleep(0.02)
        _cmd(dc, 0x10)  # SLPIN
    except Exception:
        pass
    if backlight_off and _gpio is not None:
        try:
            _gpio.output(bl, 0)
        except Exception:
            pass
    print("[st7789] blanked (black + backlight off)", flush=True)


def close(*, blank_panel: bool = False) -> None:
    """Release SPI. blank_panel=True only when you want a black/off panel (not desktop hand-off)."""
    global _spi, _ok, _lockf
    if blank_panel and _ok:
        try:
            blank(backlight_off=True)
        except Exception:
            pass
    try:
        if _spi is not None:
            _spi.close()
    except Exception:
        pass
    _spi = None
    _ok = False
    if _lockf is not None:
        try:
            import fcntl

            fcntl.flock(_lockf.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            _lockf.close()
        except Exception:
            pass
        _lockf = None


def wake_display() -> None:
    """Ensure display on + backlight after blank or cold init."""
    if not _ok and not init():
        return
    dc = _env_int("ESP_ST7789_DC", 25)
    bl = _env_int("ESP_ST7789_BL", 18)
    try:
        _cmd(dc, 0x11)  # SLPOUT
        time.sleep(0.05)
        _cmd(dc, 0x29)  # DISPON
    except Exception:
        pass
    if _gpio is not None:
        try:
            _gpio.output(bl, 1)
        except Exception:
            pass
