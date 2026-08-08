# Digivice display model

## Correct direction

```
┌──────────── SPI 2" 240×320 ────────────┐     ┌──────── HDMI (big) ────────┐
│  Digivice UI (true pixels)             │ ──► │  Same picture, scaled up   │
│  PRIMARY                               │mirror│  (debug / desk monitor)   │
└────────────────────────────────────────┘     └────────────────────────────┘
```

| Role | Display |
|------|---------|
| **Primary / app canvas** | Waveshare SPI panel |
| **Mirror** | HDMI (clone of SPI, zoomed) |

**Wrong way (causes crop):** Digivice fullscreen on HDMI 1080p → SPI only shows the top-left corner.

**Right way:** Digivice fullscreen on SPI → `xrandr --output HDMI… --scale-from 240x320 --same-as SPI…`

`digivice-layout.sh` + `ESP_HANDSET_TARGET=panel` implement this.

## Requirements for solid mirror

X11 is much more reliable than Wayland labwc for clone:

```bash
sudo raspi-config
# Advanced Options → Wayland → X11
sudo reboot
```

Then:

```bash
export DISPLAY=:0
digivice-layout          # SPI primary, HDMI = scale-from SPI
handset-phone            # Digivice on SPI canvas
```

## Env

| Variable | Default | Meaning |
|----------|---------|---------|
| `ESP_HANDSET_TARGET` | `panel` | Qt window on SPI |
| `ESP_HANDSET_MIRROR` | `1` | Enable HDMI clone of SPI |
| `ESP_HANDSET_TARGET=primary` | | Debug only: put UI on HDMI |

## Debug

```bash
xrandr
handset-session log
# look for: PRIMARY(SPI)=…  HDMI = scaled mirror
# and: Digivice canvas → 'SPI…' 240x320
```
