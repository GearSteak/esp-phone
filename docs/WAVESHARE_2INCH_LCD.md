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

Same pins whether you use the **8‑wire harness** or seat the module on a **GPIO / passthrough** stack (LCD still hits these BCM numbers):

| LCD | BCM | Board pin |
|-----|-----|-----------|
| VCC | 3.3V | 1 or 17 |
| GND | GND | 6 / 9 etc. |
| DIN | MOSI **10** | 19 |
| CLK | SCLK **11** | 23 |
| CS | CE0 **8** | 24 |
| DC | **25** | 22 |
| RST | **27** | 13 |
| BL | **18** | 12 |

On a passthrough header: LCD owns those pins; buttons + CardKB use the free pins on top — full map [`DIGIVICE_WIRING.md`](DIGIVICE_WIRING.md).

Installer enables `mipi-dbi-spi` + `panel.bin` (`waveshare2inch`). After reboot the panel is primary DRM output (`vc4-kms-v3d,nohdmi`).

```bash
dmesg | grep panel-mipi-dbi
```

If sideways/upside-down:

```bash
sudo digivice-set-rotation 180   # try first
sudo reboot
# still wrong? try: 0   then 90   then 270
sudo digivice-set-rotation 0 && sudo reboot
```

Default after install is **180°** (common for this Waveshare module).

Or edit `command 0x36 …` in `waveshare2inch.txt` and re-run `install-display.sh`.


## Navigation

This module has **no joystick**. Wire **7 hard buttons** — see [`DIGI_BUTTONS.md`](DIGI_BUTTONS.md).

Optional: keep Heltec for LoRa/steps (TFT optional).
