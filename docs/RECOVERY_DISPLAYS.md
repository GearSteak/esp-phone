# Both screens black (HDMI + SPI)

Usually caused by a broken xrandr layout (`--scale-from` / SPI-only primary).
**HDMI is restored first** now; Digivice stays off until you opt in.

## Right now (SSH or terminal before Digivice starts)

```bash
export DISPLAY=:0
pkill -9 -f handset_app
echo desktop > ~/.esp-handset/session_mode

# If you have already pulled/installed latest:
digivice-unfuck-displays
# or:
sudo digivice-recover-hdmi --now
sudo reboot
```

Without the new scripts yet:

```bash
export DISPLAY=:0
pkill -9 -f handset_app
echo desktop > ~/.esp-handset/session_mode
xrandr --auto
# replace HDMI-1 with the name from: xrandr | grep connected
xrandr --output HDMI-1 --auto --primary --on
# if your panel is Unknown19-1:
xrandr --output Unknown19-1 --auto --right-of HDMI-1 --on
```

Then:

```bash
cd ~/esp-phone && git pull
sudo bash pi_handset/install-handset.sh
sudo digivice-recover-hdmi --now
sudo reboot
```

After reboot you should get **desktop on HDMI**, not Digivice.

## SD card recovery (no display at all)

1. Power off, remove microSD, open the **boot** partition on a PC.  
2. Create empty file: `digivice-desktop`  
3. Optional: edit `config.txt` — line must be exactly:
   `dtoverlay=vc4-kms-v3d`
   (not `vc4-kms-v3d,nohdmi`)  
   And add if missing:
   ```
   hdmi_force_hotplug=1
   hdmi_drive=2
   ```
4. Reinsert SD, boot — Linux desktop, Digivice off.

## When vision is back

Do **not** run `handset-phone` until HDMI is stable. SPI can wait.
