"""Userspace ST7789 (Waveshare 2\" 240×320) over SPI0 CE0.

Wiring (BCM): MOSI=10 SCLK=11 CE0=8 DC=25 RST=27 BL=18
Requires: python3-spidev, RPi.GPIO, free /dev/spidev0.0
  (dtoverlay=mipi-dbi-spi must be OFF)

Env:
  ESP_ST7789_SPI_BUS=0 ESP_ST7789_SPI_DEV=0
  ESP_ST7789_SPEED=16000000   # 16MHz default — 40MHz causes static/snow on Pi Zero
  ESP_ST7789_DC=25 ESP_ST7789_RST=27 ESP_ST7789_BL=18
  ESP_ST7789_SWAP=1           # byte-swap RGB565 (1=default for ST7789)
  ESP_ST7789_INVERT=1         # 0x21 inversion ON (Waveshare needs this)
"""

from __future__ import annotations

import os
import time
from typing import Optional, Tuple

_spi = None
_gpio = None
_ok = False
_wh: Tuple[int, int] = (240, 320)
_speed = 16_000_000


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if not v:
        return default
    return v not in ("0", "false", "no", "off")


def _rotation_madctl() -> int:
    env = os.environ.get("ESP_PANEL_ROTATION", "").strip()
    if not env:
        try:
            env = open("/etc/esp-handset/panel-rotation", encoding="utf-8").read().strip()
        except OSError:
            env = "180"
    # Waveshare 2" ST7789 common MADCTL
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
            GPIO.setup(p, GPIO.OUT, initial=GPIO.LOW)
        _gpio = GPIO
        return True
    except Exception as e:
        print(f"[st7789] RPi.GPIO failed: {e}", flush=True)
        return False


def _cmd(dc: int, b: int) -> None:
    _gpio.output(dc, 0)
    _spi.xfer2([b & 0xFF])


def _data8(dc: int, *params: int) -> None:
    if not params:
        return
    _gpio.output(dc, 1)
    _spi.xfer2([p & 0xFF for p in params])


def init(*, force: bool = False) -> bool:
    """Open SPI + GPIO and run ST7789 init. force=True re-inits even if already ok."""
    global _spi, _ok, _wh, _speed
    if _ok and not force:
        return True
    if _ok and force:
        close(blank_panel=False)

    bus = _env_int("ESP_ST7789_SPI_BUS", 0)
    dev = _env_int("ESP_ST7789_SPI_DEV", 0)
    # 40MHz works on Pi4 sometimes but Pi Zero 2 W + jumper wires → static/snow
    speed = _env_int("ESP_ST7789_SPEED", 16_000_000)
    if speed > 24_000_000:
        print(f"[st7789] clamping SPI {speed} → 24MHz (static/snow above this)", flush=True)
        speed = 24_000_000
    dc = _env_int("ESP_ST7789_DC", 25)
    rst = _env_int("ESP_ST7789_RST", 27)
    bl = _env_int("ESP_ST7789_BL", 18)

    madctl = _rotation_madctl()
    if madctl in (0x60, 0xA0):
        _wh = (320, 240)
    else:
        _wh = (240, 320)

    if not _gpio_setup(dc, rst, bl):
        return False

    try:
        import spidev  # type: ignore

        _spi = spidev.SpiDev()
        try:
            _spi.open(bus, dev)
        except OSError as e:
            print(f"[st7789] SPI open busy ({e}); retry…", flush=True)
            time.sleep(0.8)
            try:
                _spi.close()
            except Exception:
                pass
            _spi = spidev.SpiDev()
            _spi.open(bus, dev)

        # Try requested speed then safer fallbacks if kernel rejects
        for try_hz in (speed, 16_000_000, 12_000_000, 8_000_000):
            try:
                _spi.max_speed_hz = try_hz
                _speed = try_hz
                break
            except Exception:
                continue
        _spi.mode = 0b00  # SPI mode 0 (CPOL=0 CPHA=0) — Waveshare
        _spi.lsbfirst = False
        _spi.bits_per_word = 8
        try:
            _spi.no_cs = False
        except Exception:
            pass
        if not hasattr(_spi, "writebytes2"):
            _spi.writebytes2 = lambda b: _spi.xfer2(list(b))  # type: ignore
    except Exception as e:
        print(
            f"[st7789] SPI open failed ({e}). "
            "Need /dev/spidev0.0 (mipi-dbi-spi OFF + dtparam=spi=on).",
            flush=True,
        )
        return False

    # Hard reset (longer dwell — leaves sleep/static states)
    _gpio.output(bl, 0)
    _gpio.output(rst, 1)
    time.sleep(0.01)
    _gpio.output(rst, 0)
    time.sleep(0.12)
    _gpio.output(rst, 1)
    time.sleep(0.15)

    def c(cmd: int, *params: int) -> None:
        _cmd(dc, cmd)
        if params:
            _data8(dc, *params)

    # Waveshare-style init (PORCTRL/gamma) — incomplete init = snow
    c(0x01)  # SWRESET
    time.sleep(0.15)
    c(0x11)  # SLPOUT
    time.sleep(0.12)
    c(0x3A, 0x05)  # COLMOD RGB565
    c(0x36, madctl)  # MADCTL
    c(0xB2, 0x0C, 0x0C, 0x00, 0x33, 0x33)  # PORCTRL
    c(0xB7, 0x35)  # GCTRL
    c(0xBB, 0x19)  # VCOMS
    c(0xC0, 0x2C)  # LCMCTRL
    c(0xC2, 0x01)  # VDVVRHEN
    c(0xC3, 0x12)  # VRHS
    c(0xC4, 0x20)  # VDVS
    c(0xC6, 0x0F)  # FRCTRL2
    c(0xD0, 0xA4, 0xA1)  # PWCTRL1
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
    # Full window before display on — avoid garbage RAM snow
    w, h = _wh
    c(0x2A, 0x00, 0x00, (w - 1) >> 8, (w - 1) & 0xFF)
    c(0x2B, 0x00, 0x00, (h - 1) >> 8, (h - 1) & 0xFF)
    if _env_bool("ESP_ST7789_INVERT", True):
        c(0x21)  # INVON — Waveshare 2" needs this
    else:
        c(0x20)
    c(0x13)  # NORON
    c(0x29)  # DISPON
    time.sleep(0.05)

    _ok = True
    # Clear snow (uninitialized GRAM) to solid dark
    try:
        fill(8, 12, 20)
    except Exception as e:
        print(f"[st7789] clear fill: {e}", flush=True)
    _gpio.output(bl, 1)

    print(
        f"[st7789] ready SPI{bus}.{dev}@{_speed // 1_000_000}MHz "
        f"{_wh[0]}x{_wh[1]} MADCTL=0x{madctl:02x} DC={dc} RST={rst} BL={bl}",
        flush=True,
    )
    return True


def size() -> Tuple[int, int]:
    return _wh


def ready() -> bool:
    return _ok


def _set_window(dc: int, x0: int, y0: int, x1: int, y1: int) -> None:
    _cmd(dc, 0x2A)
    _data8(dc, (x0 >> 8) & 0xFF, x0 & 0xFF, (x1 >> 8) & 0xFF, x1 & 0xFF)
    _cmd(dc, 0x2B)
    _data8(dc, (y0 >> 8) & 0xFF, y0 & 0xFF, (y1 >> 8) & 0xFF, y1 & 0xFF)
    _cmd(dc, 0x2C)


def _rgb565_bytes(img) -> bytes:
    """Pack QImage → ST7789 big-endian RGB565 (high byte first)."""
    from PyQt5.QtGui import QImage
    from PyQt5.QtCore import Qt

    w, h = _wh
    if img.width() != w or img.height() != h:
        img = img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    # RGB32 is reliable across Qt builds (avoid Format_RGB16 endian surprises)
    img = img.convertToFormat(QImage.Format_RGB32)
    ptr = img.bits()
    ptr.setsize(img.byteCount())
    raw = bytes(ptr)
    bpl = img.bytesPerLine()
    swap = _env_bool("ESP_ST7789_SWAP", True)
    out = bytearray(w * h * 2)
    o = 0
    for y in range(h):
        row = y * bpl
        for x in range(w):
            i = row + x * 4
            # Qt RGB32 little-endian memory: B G R A on little-endian hosts
            b = raw[i]
            g = raw[i + 1]
            r = raw[i + 2]
            pix = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            if swap:
                out[o] = (pix >> 8) & 0xFF
                out[o + 1] = pix & 0xFF
            else:
                out[o] = pix & 0xFF
                out[o + 1] = (pix >> 8) & 0xFF
            o += 2
    return bytes(out)


def blit_qimage(img) -> None:
    """Push a QImage (any format) scaled to panel as RGB565 SPI write."""
    if not _ok or _spi is None:
        return
    from PyQt5.QtGui import QImage

    if img is None or img.isNull():
        return
    dc = _env_int("ESP_ST7789_DC", 25)
    w, h = _wh
    try:
        ba = _rgb565_bytes(img)
    except Exception as e:
        print(f"[st7789] pack: {e}", flush=True)
        return

    try:
        _set_window(dc, 0, 0, w - 1, h - 1)
        _gpio.output(dc, 1)
        step = 4096  # spidev default buffer
        for i in range(0, len(ba), step):
            _spi.writebytes2(ba[i : i + step])
    except Exception as e:
        print(f"[st7789] blit: {e}", flush=True)


def fill(r: int, g: int, b: int) -> None:
    if not _ok:
        return
    from PyQt5.QtGui import QImage

    w, h = _wh
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill((0xFF << 24) | ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF))
    blit_qimage(img)


def blank(*, backlight_off: bool = True) -> None:
    if not _ok:
        if not init():
            return
    try:
        fill(0, 0, 0)
    except Exception as e:
        print(f"[st7789] blank fill: {e}", flush=True)
    dc = _env_int("ESP_ST7789_DC", 25)
    bl = _env_int("ESP_ST7789_BL", 18)
    try:
        _cmd(dc, 0x28)
        time.sleep(0.02)
        _cmd(dc, 0x10)
    except Exception:
        pass
    if backlight_off and _gpio is not None:
        try:
            _gpio.output(bl, 0)
        except Exception:
            pass
    print("[st7789] blanked", flush=True)


def close(*, blank_panel: bool = False) -> None:
    global _spi, _ok
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


def wake_display() -> None:
    if not _ok and not init():
        return
    dc = _env_int("ESP_ST7789_DC", 25)
    bl = _env_int("ESP_ST7789_BL", 18)
    try:
        _cmd(dc, 0x11)
        time.sleep(0.08)
        _cmd(dc, 0x29)
    except Exception:
        pass
    if _gpio is not None:
        try:
            _gpio.output(bl, 1)
        except Exception:
            pass


def reinit() -> bool:
    """Force full re-init (use after static/snow or bus fight)."""
    return init(force=True)
