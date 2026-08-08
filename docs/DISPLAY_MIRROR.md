# Digivice SPI + HDMI

## What you should see

| Display | Role |
|---------|------|
| **SPI 2″** | Real Digivice window at 240×320 (live UI, not a crop) |
| **HDMI** | Same UI, **scaled up** (software host, refreshes ~30 fps) |

## If HDMI is right but SPI is black

Qt often never saw the SPI screen. Turn SPI on, then relaunch:

```bash
export DISPLAY=:0
digivice-layout          # turns SPI on, keeps HDMI
xrandr | grep connected  # SPI-… must appear
handset-desktop; pkill -f handset_app; handset-phone
```

Log should include:

```text
Digivice LIVE on panel 'SPI-…' 240x320
scale-host (HDMI) → 'HDMI-…'
```

If log only has one screen and no SPI name, the panel is not active in X — check wiring, `dmesg | grep -i mipi`, backlight.

## Backlight

```bash
for d in /sys/class/backlight/*; do
  echo 0 | sudo tee $d/bl_power
  cat $d/max_brightness | sudo tee $d/brightness
done
```
