# Digivice SPI + HDMI

## What you should see

| Display | Role |
|---------|------|
| **SPI 2″** | Real Digivice window at 240×320 (live UI, not a crop) |
| **HDMI** | Same UI, **scaled up** (software host, refreshes ~30 fps) |

## If HDMI is right but SPI is black

KMS names the panel **`Unknown19-1`** (normal). Digivice must put a **paint host** on that rect — the main window usually stays on HDMI.

```bash
cd ~/esp-phone && git pull
# reinstall or: sudo cp pi_handset/esp_handset/display_geom.py /opt/esp-handset/
#             sudo cp pi_handset/session/*.sh /opt/esp-handset/session/

export DISPLAY=:0
digivice-layout
# Must show active geometry, e.g. Unknown19-1 … 240x320+0+0  (not only "connected")
xrandr | grep -E 'connected|240x320'

pkill -f handset_app
handset-phone
tail -n 40 ~/.esp-handset/handset.log
```

Log should include **host lines for both** outputs:

```text
host → 'Unknown19-1' 240x320+0+0
host → 'HDMI-1' 1920x1080+240+0
hosts active: 2
```

Cyan flash test (proves hosts reach SPI):

```bash
ESP_HANDSET_SPI_TEST=1 handset-phone
# whole 2" should go cyan; if not → backlight/wiring/driver, not Qt layout
```

## Backlight

```bash
for d in /sys/class/backlight/*; do
  echo 0 | sudo tee $d/bl_power
  cat $d/max_brightness | sudo tee $d/brightness
done
```
