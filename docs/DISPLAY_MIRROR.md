# Digivice SPI + HDMI

## Model (restored)

1. **`Unknown19-1`** (or SPI-*) = primary at **240×320** — real Digivice window fills it  
2. **HDMI** = xrandr clone of the panel when possible (`--scale-from` / `--same-as`)

KMS often names the 2″ panel `Unknown19-1`, not `SPI`. That is normal.

## If SPI is black again

```bash
cd ~/esp-phone && git pull
sudo bash pi_handset/install-handset.sh

export DISPLAY=:0
digivice-layout
xrandr | grep connected
# want: Unknown19-1 connected primary 240x320+0+0

pkill -f handset_app
handset-phone
tail -n 40 ~/.esp-handset/handset.log
```

Log should show:

```text
Digivice ON PANEL 'Unknown19-1' 240x320+0+0
```

If it says a huge HDMI geometry, layout failed to make the panel primary.
