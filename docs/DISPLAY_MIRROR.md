# Mirror Digivice on SPI 2″ and HDMI

Same UI on both screens (clone / scale), not two different desktops.

## What the software does

On `handset-phone` / Digivice autostart, `mirror-displays.sh` runs:

1. **X11** (best): `xrandr --scale-from 240x320 --same-as <SPI>` so HDMI is a big zoom of the 240×320 Digivice view  
2. **Wayland**: best-effort (`wlr-randr` positions, optional `wl-mirror`)

## Prefer X11 for rock-solid mirror

Raspberry Pi OS Bookworm defaults to Wayland. For reliable clone:

```bash
sudo raspi-config
# Advanced Options → Wayland → X11
sudo reboot
```

Then re-run installer or:

```bash
handset-session mirror
handset-phone
```

## Manual

```bash
digivice-mirror-displays
# or
handset-session mirror
xrandr   # see connector names (SPI-1, HDMI-A-1, …)
```

## Still different content?

1. Confirm HDMI is on: `dtoverlay=vc4-kms-v3d` **without** `,nohdmi`  
2. Use **X11** as above  
3. In Screen Configuration GUI, set displays to **Mirror** if offered  

HDMI shows the same 240×320 layout scaled up, so Digivice will look large and blocky on the monitor — that is expected for a true mirror of the phone panel.
