# Instructables ST7789 desktop path (canonical)

Guide: [How to Mirror the Desktop of RPI OS on Any ST7789 SPI Display](https://www.instructables.com/How-to-Mirror-the-Desktop-of-RPI-OS-on-Any-St7789-/)

## What that guide actually does

It does **not** grab X11 in Python and bitbang frames to SPI.

It uses [Adafruit’s `adafruit-pitft.py`](https://github.com/adafruit/Raspberry-Pi-Installer-Scripts):

1. Pick **ST7789 2.0"** (or similar)
2. Install type **mirror** / desktop
3. Loads ST7789 as a **real DRM panel** (`mipi-dbi-spi` / tinydrm family)
4. Raspberry Pi OS draws the desktop on that head

On modern Bookworm:

- Legacy **fbcp** (also listed in old Adafruit “mirror” code) is unreliable
- The Pi sees SPI as a **second display** → enable it (we run `digivice-spi-drm-activate` at login)

## Digivice equivalent (Waveshare 2″ pins)

| Item | Value |
|------|--------|
| SPI | SPI0 CE0 |
| DC | BCM 25 |
| RST | BCM 27 |
| BL | BCM 18 (Adafruit default is 22 — we override) |
| Size | 240×320 |

```bash
cd ~/esp-phone && git pull
sudo digivice-full-update          # installs Instructables DRM path + reboot
# or only:
sudo digivice-install-instructables
sudo reboot
```

After reboot on desktop:

```bash
digivice-spi-drm-activate
# If still blank: Preferences → Screen Configuration → enable SPI/Unknown output
```

Digivice phone UI uses `ESP_HANDSET_SPI_BACKEND=drm` (fullscreen hosts on the SPI QScreen).

## What we got wrong earlier

Treating the guide as “copy framebuffer with userspace `st7789_spi.py`” (fbcp *idea*). That works for **Digivice→panel** when it has a canvas, but **desktop black/green** happened when grabs failed. The Instructables path makes the **OS own the panel**.

## Files

| Script | Role |
|--------|------|
| `display/install-instructables-mirror.sh` | `digivice-install-instructables` |
| `display/install-display.sh` | mipi-dbi firmware + `config.txt` |
| `session/spi-drm-activate.sh` | enable/clone SPI head after login |

Do **not** re-run `digivice-install-spi-userspace` unless you intentionally leave DRM.
