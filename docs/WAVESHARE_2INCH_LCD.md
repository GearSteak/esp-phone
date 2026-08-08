# Waveshare 2inch LCD Module (ST7789 240×320 SPI)

Digivice main display. Official wiki:
https://www.waveshare.com/wiki/2inch_LCD_Module

| Spec | Value |
|------|--------|
| Size | 2" IPS |
| Resolution | **240 × 320** |
| Driver | ST7789V / ST7789VW |
| Bus | SPI (CE0) |

## Wiring to Raspberry Pi

| LCD | BCM | Board pin |
|-----|-----|-----------|
| VCC | 3.3V | 1 or 17 |
| GND | GND | 6 etc. |
| DIN | MOSI **10** | 19 |
| CLK | SCLK **11** | 23 |
| CS | CE0 **8** | 24 |
| DC | **25** | 22 |
| RST | **27** | 13 |
| BL | **18** | 12 |

Installer enables `mipi-dbi-spi` + `panel.bin` (`waveshare2inch`). After reboot the panel is primary DRM output (`vc4-kms-v3d,nohdmi`).

```bash
dmesg | grep panel-mipi-dbi
```

If the image is upside-down or sideways, on the Pi:

```bash
cd /path/to/esp-phone/pi_handset/display   # or /opt/esp-handset/display
sudo bash set-panel-rotation.sh c0         # try 180° first
# other tries: 00  60  a0
sudo reboot
```

Or edit `command 0x36 …` in `waveshare2inch.txt` and re-run `install-display.sh`.

## Navigation

This module has **no joystick**. Wire **7 hard buttons** — see [`DIGI_BUTTONS.md`](DIGI_BUTTONS.md).

Optional: keep Heltec for LoRa/steps (TFT optional).
