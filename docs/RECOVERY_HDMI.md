# Recover HDMI / normal desktop (no OS reinstall)

If Digivice install left you with **no HDMI** or only a tiny SPI screen:

## Fix now (SSH or any working terminal)

```bash
# Prefer the shipped fixer after git pull / reinstall scripts:
sudo digivice-recover-hdmi
sudo reboot
```

If that command is missing, one-shot repair:

```bash
CFG=/boot/firmware/config.txt
[ -f "$CFG" ] || CFG=/boot/config.txt

# 1) HDMI on (remove nohdmi)
sudo sed -i -E 's/^dtoverlay=vc4-kms-v3d(|,.*)$/dtoverlay=vc4-kms-v3d/' "$CFG"

# 2) Do not auto-start Digivice
mkdir -p ~/.esp-handset
echo desktop > ~/.esp-handset/session_mode
echo desktop | sudo tee /etc/esp-handset/ui_mode >/dev/null

# 3) Kill Digivice UI if stuck
pkill -f handset_app.py || true

sudo reboot
```

Optional: **comment out** every line between  
`# --- ESP Digivice display` and `# --- END ESP Digivice display`  
in that same `config.txt` so only HDMI is used until you re-enable the 2″ later.

## After reboot

- Use **HDMI desktop** as usual.
- Digivice: `handset-phone`
- Leave Digivice: `handset-desktop` or **F12** / **Ctrl+Shift+D** in the app  
  · Settings → Linux

## Re-enable the 2″ panel later (HDMI stays on)

```bash
sudo bash /opt/esp-handset/display/install-display.sh
sudo reboot
```

Updated installers never set `nohdmi` and default session mode to **desktop**.
