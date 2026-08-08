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
digivice-layout          # turns panel on, keeps HDMI
xrandr | grep connected  # often: Unknown19-1 (not "SPI-…") — that *is* the 2" panel
handset-desktop; pkill -f handset_app; handset-phone
```

KMS names the mipi-dbi panel **`Unknown19-1`** (or similar). Digivice treats that as the phone surface.

Log should include:

```text
Digivice LIVE on panel 'Unknown19-1' 240x320
scale-host (HDMI) → 'HDMI-…'
```

## Backlight

```bash
for d in /sys/class/backlight/*; do
  echo 0 | sudo tee $d/bl_power
  cat $d/max_brightness | sudo tee $d/brightness
done
```
