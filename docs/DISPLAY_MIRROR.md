# Digivice display model — SPI primary canvas

## Why it looked “cut off”

With HDMI (1080p) as a big desktop and SPI as a **window into that desktop**, the 2″ panel only shows the **top-left ~240×320 of 1080p**. That is not Digivice drawing wrong — the whole X screen was still huge.

## Correct model

```
1) While Digivice runs:
   - HDMI off (or pure clone)
   - SPI = only display, mode 240×320 (or 320×240)
   - xrandr --fb 240x320   ← entire desktop IS phone-sized
   - Digivice fullscreen fills that world → no crop

2) Optional: HDMI back with
   --scale-from 240x320 --same-as SPI
   = big monitor shows the SAME phone UI zoomed
```

## Requirements

**Use X11** for reliable `xrandr --fb` / clone:

```bash
sudo raspi-config   # Advanced → Wayland → X11 → finish → reboot
```

## Commands

```bash
export DISPLAY=:0
digivice-layout          # shrink world to SPI; try HDMI mirror
# check:
xrandr
# Expect: Screen 0: minimum … current 240 x 320 …
# And SPI connected primary 240x320

handset-phone
```

Leave Digivice (restore HDMI for normal desktop):

```bash
handset-desktop
```

SPI only (HDMI stays black — always full UI on panel):

```bash
export ESP_HANDSET_MIRROR=0
digivice-layout
handset-phone
```

## Logs

```bash
handset-session log
# look for: xrandr --fb 240x320 OK  and  Digivice → … 240x320
```

If `Screen` still says `1920 x 1080`, layout never stuck — stay on X11 and paste `xrandr` output.
