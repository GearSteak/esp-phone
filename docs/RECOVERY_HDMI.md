# HDMI + Digivice (no reinstall)

**Goal:** Digivice boots by default **and** HDMI works.

| Setting | Value |
|---------|--------|
| Boot UI | Digivice (`session_mode=phone`) |
| HDMI | ON (`vc4-kms-v3d` **without** `nohdmi`) |
| 2″ SPI | Optional second panel (same config block) |

Leave Digivice: `handset-desktop` · **F12** · **Ctrl+Shift+D** · Settings → Linux  
Return: `handset-phone` (and stay default with `handset-session set-phone`)

## Late HDMI plug (cable after boot)

Pi only modesets HDMI at X start if a monitor is present. Plugging in later
needs `xrandr --auto` (or reboot). Digivice installs:

```bash
sudo digivice-hdmi-hotplug --install   # also done by digivice-full-update
# then plug HDMI — should light in ~2s
# manual:
digivice-hdmi-hotplug
```

`hdmi_force_hotplug=1` in config.txt helps some monitors but does **not** replace
hotplug modesetting; the udev → digivice-hdmi-hotplug path does.

## Fix HDMI only (keep Digivice default)

```bash
# One-shot if you don't have the script yet:
CFG=/boot/firmware/config.txt
[ -f "$CFG" ] || CFG=/boot/config.txt
sudo sed -i -E 's/^dtoverlay=vc4-kms-v3d(|,.*)$/dtoverlay=vc4-kms-v3d/' "$CFG"
# Digivice default:
mkdir -p ~/.esp-handset
echo phone > ~/.esp-handset/session_mode
echo phone | sudo tee /etc/esp-handset/ui_mode >/dev/null
sudo reboot
```

Or after `git pull`:

```bash
sudo bash /path/to/esp-phone/pi_handset/display/recover-hdmi.sh --keep-phone
sudo reboot
```

`--keep-phone` sets Digivice as login default.  
Default recover **does not** switch you to desktop-only.

## Comment

Old installs used `nohdmi`, so HDMI died. Current `install-display.sh` never does that.
