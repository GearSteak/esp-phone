#!/usr/bin/env bash
# Single installer for ESP Digivice handset on Raspberry Pi OS (Bookworm).
# Waveshare 2" 240×320 SPI + 7 hard buttons + SIM7600 USB + Heltec USB LoRa.
# 2" SPI panel + HDMI both on. Default session = Digivice (handset-desktop to leave).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${PREFIX:-/opt/esp-handset}"
USER_NAME="${SUDO_USER:-$USER}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"

echo "=== ESP Digivice installer (Digivice default · HDMI kept on) ==="
echo "Install prefix: $PREFIX"
echo "User: $USER_NAME ($USER_HOME)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Re-run with sudo: sudo ./install-handset.sh"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  python3 python3-pip python3-pyqt5 python3-serial \
  python3-uinput \
  python3-smbus \
  i2c-tools \
  python3-rpi.gpio \
  python3-lgpio \
  python3-spidev \
  python3-pil \
  python3-mss \
  imagemagick \
  xdotool \
  python3-picamera2 \
  rpicam-apps \
  linphone-cli \
  pipewire pipewire-audio wireplumber \
  alsa-utils \
  bluez \
  network-manager \
  modemmanager \
  fonts-dejavu-core \
  zram-tools \
  wmctrl \
  x11-xserver-utils \
  wlr-randr || true

# Optional Wayland mirror tool (bookworm may or may not package it)
apt-get install -y wl-mirror 2>/dev/null || true

apt-get install -y midori || apt-get install -y epiphany-browser || true

mkdir -p "$PREFIX" "$PREFIX/session" /etc/esp-handset /etc/udev/rules.d
cp -a "$ROOT/esp_handset" "$PREFIX/"
cp -a "$ROOT/session/." "$PREFIX/session/"
install -m 755 "$ROOT/esp_handset/hat_inputd.py" "$PREFIX/hat_inputd.py"
install -m 755 "$ROOT/esp_handset/buttons_inputd.py" "$PREFIX/buttons_inputd.py"
install -m 755 "$ROOT/esp_handset/cardkb_inputd.py" "$PREFIX/cardkb_inputd.py"
install -m 755 "$ROOT/esp_handset/t9_keypad_inputd.py" "$PREFIX/t9_keypad_inputd.py"
install -m 755 "$ROOT/esp_handset/handset_app.py" "$PREFIX/handset_app.py"
install -m 755 "$ROOT/esp_handset/esp_keyd.py" "$PREFIX/esp_keyd.py"
install -m 755 "$ROOT/session/handset-session.sh" "$PREFIX/session/handset-session.sh"
install -m 755 "$ROOT/session/handset-session.sh" /usr/local/bin/handset-session
install -m 755 "$ROOT/session/mirror-displays.sh" "$PREFIX/session/mirror-displays.sh"
install -m 755 "$ROOT/session/mirror-displays.sh" /usr/local/bin/digivice-mirror-displays
install -m 755 "$ROOT/session/digivice-layout.sh" "$PREFIX/session/digivice-layout.sh"
install -m 755 "$ROOT/session/digivice-layout.sh" /usr/local/bin/digivice-layout
install -m 755 "$ROOT/session/restore-desktop-displays.sh" "$PREFIX/session/restore-desktop-displays.sh"
install -m 755 "$ROOT/session/restore-desktop-displays.sh" /usr/local/bin/digivice-restore-desktop
install -m 755 "$ROOT/session/fix-cursor.sh" "$PREFIX/session/fix-cursor.sh"
install -m 755 "$ROOT/session/fix-cursor.sh" /usr/local/bin/digivice-fix-cursor
install -m 755 "$ROOT/session/unfuck-displays.sh" "$PREFIX/session/unfuck-displays.sh"
install -m 755 "$ROOT/session/unfuck-displays.sh" /usr/local/bin/digivice-unfuck-displays
install -m 755 "$ROOT/session/spi-test.sh" "$PREFIX/session/spi-test.sh"
install -m 755 "$ROOT/session/spi-test.sh" /usr/local/bin/digivice-spi-test
install -m 755 "$ROOT/session/spi-prove.sh" "$PREFIX/session/spi-prove.sh"
install -m 755 "$ROOT/session/spi-prove.sh" /usr/local/bin/digivice-spi-prove
install -m 755 "$ROOT/session/spi-blank.sh" "$PREFIX/session/spi-blank.sh"
install -m 755 "$ROOT/session/spi-blank.sh" /usr/local/bin/digivice-spi-blank
install -m 755 "$ROOT/session/desktop-spi-mirror.sh" "$PREFIX/session/desktop-spi-mirror.sh"
install -m 755 "$ROOT/session/desktop-spi-mirror.sh" /usr/local/bin/digivice-desktop-mirror
install -m 755 "$ROOT/session/update-handset.sh" "$PREFIX/session/update-handset.sh"
install -m 755 "$ROOT/session/update-handset.sh" /usr/local/bin/digivice-update
install -m 755 "$ROOT/session/full-update.sh" "$PREFIX/session/full-update.sh"
install -m 755 "$ROOT/session/full-update.sh" /usr/local/bin/digivice-full-update
install -m 755 "$ROOT/session/gui-update.sh" "$PREFIX/session/gui-update.sh"
install -m 755 "$ROOT/session/gui-update.sh" /usr/local/bin/digivice-gui-update
install -m 755 "$ROOT/session/home-relaunch.sh" "$PREFIX/session/home-relaunch.sh"
install -m 755 "$ROOT/session/home-relaunch.sh" /usr/local/bin/digivice-home-relaunch
install -m 755 "$ROOT/session/apply-update.sh" "$PREFIX/session/apply-update.sh"
install -m 755 "$ROOT/session/apply-update.sh" /usr/local/bin/digivice-apply-update
install -m 755 "$ROOT/session/digivice-gb.sh" "$PREFIX/session/digivice-gb.sh"
install -m 755 "$ROOT/session/digivice-gb.sh" /usr/local/bin/digivice-gb
install -m 755 "$ROOT/session/digivice-stop-gb.sh" "$PREFIX/session/digivice-stop-gb.sh"
install -m 755 "$ROOT/session/digivice-stop-gb.sh" /usr/local/bin/digivice-stop-gb
install -m 755 "$ROOT/session/ensure-gb-wrappers.sh" "$PREFIX/session/ensure-gb-wrappers.sh"
install -m 755 "$ROOT/session/ensure-gb-wrappers.sh" /usr/local/bin/digivice-ensure-gb
bash "$ROOT/session/ensure-gb-wrappers.sh" 2>/dev/null || true
install -m 755 "$ROOT/session/ensure-gb-roms.sh" "$PREFIX/session/ensure-gb-roms.sh"
install -m 755 "$ROOT/session/ensure-gb-roms.sh" /usr/local/bin/digivice-gb-roms-dir
bash "$ROOT/session/ensure-gb-roms.sh" 2>/dev/null || true
touch "$USER_HOME/.esp-handset/gb-disabled" 2>/dev/null || true
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset/gb-disabled" 2>/dev/null || true
install -m 755 "$ROOT/session/install-home-request.sh" "$PREFIX/session/install-home-request.sh"
bash "$ROOT/session/install-home-request.sh" 2>/dev/null || true
install -m 755 "$ROOT/session/ensure-buttons.sh" "$PREFIX/session/ensure-buttons.sh"
install -m 755 "$ROOT/session/ensure-buttons.sh" /usr/local/bin/digivice-ensure-buttons
# Seed binary only — do NOT enable udev auto HDMI (breaks 2\" SPI)
install -m 755 "$ROOT/session/hdmi-hotplug.sh" "$PREFIX/session/hdmi-hotplug.sh"
install -m 755 "$ROOT/session/hdmi-hotplug.sh" /usr/local/bin/digivice-hdmi-hotplug
install -m 755 "$ROOT/session/fix-screens.sh" "$PREFIX/session/fix-screens.sh" 2>/dev/null || true
install -m 755 "$ROOT/session/fix-screens.sh" /usr/local/bin/digivice-fix-screens 2>/dev/null || true
install -m 755 "$ROOT/session/power.sh" "$PREFIX/session/power.sh"
install -m 755 "$ROOT/session/power.sh" /usr/local/bin/digivice-power

# Settings → Update can run without a password prompt on the handset
cat >/etc/sudoers.d/esp-handset-update <<EOF
# Digivice full + GUI update (no password)
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-full-update
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-update
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-gui-update
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-apply-update
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-power
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-set-rotation
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/full-update.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/update-handset.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/gui-update.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/power.sh
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-ensure-buttons
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/ensure-buttons.sh
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-fix-cursor
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/bash $PREFIX/session/gui-update.sh
$USER_NAME ALL=(root) NOPASSWD: /bin/bash $PREFIX/session/gui-update.sh
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/bash $PREFIX/session/power.sh
$USER_NAME ALL=(root) NOPASSWD: /bin/bash $PREFIX/session/power.sh
EOF
chmod 440 /etc/sudoers.d/esp-handset-update

# Remember git checkout for digivice-update (if installer was run from a clone)
if [[ -d "$ROOT/../.git" ]]; then
  REPO_ROOT="$(cd "$ROOT/.." && pwd)"
  echo "$REPO_ROOT" >/etc/esp-handset/repo.path
fi

cat >/etc/udev/rules.d/99-esp-handset.rules <<'EOF'
# Espressif USB CDC — Heltec LoRa / notify bridge
SUBSYSTEM=="tty", ATTRS{idVendor}=="303a", SYMLINK+="esp-bridge", MODE="0666"
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", SYMLINK+="esp-bridge", MODE="0666"
# SimTech / SIMCom SIM7600 — USB AT (GPIO UART also via digivice-modem-uart)
SUBSYSTEM=="tty", ATTRS{idVendor}=="1e0e", ATTRS{bInterfaceNumber}=="02", SYMLINK+="sim7600-at", MODE="0666"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1e0e", MODE="0666"
EOF
udevadm control --reload-rules || true
udevadm trigger || true

usermod -aG dialout,i2c "$USER_NAME" 2>/dev/null || usermod -aG dialout "$USER_NAME" 2>/dev/null || true
systemctl disable esp-handset-sim7600-link.service 2>/dev/null || true
rm -f /etc/systemd/system/esp-handset-sim7600-link.service \
  /usr/local/bin/esp-handset-sim7600-link
# Keep UART /dev/sim7600-at if present (GPIO HAT mode) — do not delete
if [[ -f "$ROOT/session/digivice-modem-uart.sh" ]]; then
  install -m 755 "$ROOT/session/digivice-modem-uart.sh" "$PREFIX/session/digivice-modem-uart.sh"
  install -m 755 "$ROOT/session/digivice-modem-uart.sh" /usr/local/bin/digivice-modem-uart
fi
if [[ -f "$ROOT/session/digivice-modem-doctor.sh" ]]; then
  install -m 755 "$ROOT/session/digivice-modem-doctor.sh" "$PREFIX/session/digivice-modem-doctor.sh"
  install -m 755 "$ROOT/session/digivice-modem-doctor.sh" /usr/local/bin/digivice-modem-doctor
fi
if [[ -f "$ROOT/session/digivice-audio-doctor.sh" ]]; then
  install -m 755 "$ROOT/session/digivice-audio-doctor.sh" "$PREFIX/session/digivice-audio-doctor.sh"
  install -m 755 "$ROOT/session/digivice-audio-doctor.sh" /usr/local/bin/digivice-audio-doctor
fi
if [[ -f "$ROOT/session/digivice-audio-usb.sh" ]]; then
  install -m 755 "$ROOT/session/digivice-audio-usb.sh" "$PREFIX/session/digivice-audio-usb.sh"
  install -m 755 "$ROOT/session/digivice-audio-usb.sh" /usr/local/bin/digivice-audio-usb
fi

if [[ -f "$ROOT/sip.env" ]]; then
  install -m 600 "$ROOT/sip.env" /etc/esp-handset/sip.env
else
  cat >/etc/esp-handset/sip.env <<'EOF'
SIP_SERVER=sip.zadarma.com
SIP_USER=440892
SIP_PASS=Ping927Ld
SIP_DISPLAY=SIP
SIP_DID=+17788000889
EOF
  chmod 600 /etc/esp-handset/sip.env
fi
install -m 600 /etc/esp-handset/sip.env "$USER_HOME/.esp-handset/sip.env" 2>/dev/null || true
chown "$USER_NAME:$USER_NAME" /etc/esp-handset/sip.env "$USER_HOME/.esp-handset/sip.env" 2>/dev/null || true
chown -R "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset" 2>/dev/null || true

# SPI 2" as optional second panel — HDMI stays ON
cp -a "$ROOT/display" "$PREFIX/display"
chmod +x "$PREFIX/display/install-display.sh" "$PREFIX/display/mipi-dbi-cmd" \
  "$PREFIX/display/recover-hdmi.sh" "$PREFIX/display/set-panel-rotation.sh" 2>/dev/null || true
install -m 755 "$ROOT/display/recover-hdmi.sh" /usr/local/bin/digivice-recover-hdmi
install -m 755 "$ROOT/display/set-panel-rotation.sh" /usr/local/bin/digivice-set-rotation
install -m 755 "$ROOT/display/spi-doctor.sh" /usr/local/bin/digivice-spi-doctor
install -m 755 "$ROOT/display/spi-doctor.sh" "$PREFIX/display/spi-doctor.sh"
install -m 755 "$ROOT/display/install-spi-userspace.sh" /usr/local/bin/digivice-install-spi-userspace
install -m 755 "$ROOT/display/install-spi-userspace.sh" "$PREFIX/display/install-spi-userspace.sh"
install -m 755 "$ROOT/display/install-instructables-mirror.sh" /usr/local/bin/digivice-install-instructables
install -m 755 "$ROOT/display/install-instructables-mirror.sh" "$PREFIX/display/install-instructables-mirror.sh"
install -m 755 "$ROOT/session/spi-drm-activate.sh" /usr/local/bin/digivice-spi-drm-activate

# Convenience
cat >/usr/local/bin/handset-spi <<'EOF'
#!/bin/bash
# Digivice with SPI sole head (HDMI off) — use when dual-head leaves SPI black
export ESP_HANDSET_SPI_ONLY=1
export ESP_HANDSET_PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
exec /usr/local/bin/handset-session spi-phone
EOF
chmod +x /usr/local/bin/handset-spi
bash "$ROOT/display/install-display.sh"

mkdir -p "$USER_HOME/.esp-handset" "$USER_HOME/Pictures/phone" \
  "$USER_HOME/.local/share/applications" "$USER_HOME/Desktop" \
  "$USER_HOME/.config/autostart"
# Default: Digivice on boot. HDMI stays enabled next to SPI panel.
echo phone >"$USER_HOME/.esp-handset/session_mode"
echo phone >/etc/esp-handset/ui_mode
chown "$USER_NAME:$USER_NAME" /etc/esp-handset/ui_mode
chmod 664 /etc/esp-handset/ui_mode
chown -R "$USER_NAME:$USER_NAME" "$USER_HOME/Pictures/phone" "$USER_HOME/.esp-handset"

cat >/etc/udev/rules.d/99-digivice-buttons.rules <<'EOF'
# Digivice hard buttons — seat/X can read the virtual keyboard
KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"
SUBSYSTEM=="input", KERNEL=="event*", ATTRS{name}=="Digivice-Buttons", \
  MODE="0666", GROUP="input", \
  ENV{ID_INPUT}="1", ENV{ID_INPUT_KEYBOARD}="1", \
  ENV{ID_INPUT_KEY}="1", TAG+="uaccess", TAG+="seat"
EOF

cat >/etc/modules-load.d/uinput.conf <<'EOF'
uinput
EOF
modprobe uinput 2>/dev/null || true
usermod -aG input,gpio "$USER_NAME" 2>/dev/null || usermod -aG input "$USER_NAME" 2>/dev/null || true

cat >/etc/systemd/system/digi-buttons-inputd.service <<EOF
[Unit]
Description=Digivice hard buttons (GPIO → keys)
After=multi-user.target systemd-udev-settle.service
Wants=multi-user.target

[Service]
Type=simple
User=root
Environment=DISPLAY=:0
Environment=XAUTHORITY=$USER_HOME/.Xauthority
Environment=ESP_HANDSET_PREFIX=$PREFIX
ExecStartPre=-/sbin/modprobe uinput
ExecStart=/usr/bin/python3 $PREFIX/buttons_inputd.py
Restart=always
RestartSec=1

[Install]
WantedBy=multi-user.target
EOF

# Optional alternate inputs (disabled by default)
cat >/etc/systemd/system/t9-keypad-inputd.service <<EOF
[Unit]
Description=Optional Digivice 4x4 T9 keypad
After=multi-user.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 $PREFIX/t9_keypad_inputd.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/cardkb-inputd.service <<EOF
[Unit]
Description=Optional CardKB I2C
After=multi-user.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 $PREFIX/cardkb_inputd.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

# Slower I2C helps CardKB on Pi Zero (clock stretch after first key)
for cfg in /boot/firmware/config.txt /boot/config.txt; do
  if [[ -f "$cfg" ]] && ! grep -q 'i2c_arm_baudrate' "$cfg" 2>/dev/null; then
    echo "" >>"$cfg"
    echo "# Digivice CardKB" >>"$cfg"
    echo "dtparam=i2c_arm_baudrate=50000" >>"$cfg"
    break
  fi
done

cat >/etc/systemd/system/hat-inputd.service <<EOF
[Unit]
Description=Optional LCD HAT joystick/keys
After=multi-user.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 $PREFIX/hat_inputd.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/esp-keyd.service <<EOF
[Unit]
Description=ESP KEY bridge → uinput (Heltec CardKB path)
After=dev-esp\\x2dbridge.device multi-user.target
Wants=dev-esp\\x2dbridge.device

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 $PREFIX/esp_keyd.py
Restart=always
RestartSec=2
Environment=ESP_HANDSET_PREFIX=$PREFIX

[Install]
WantedBy=multi-user.target
EOF

rm -f "$USER_HOME/.config/autostart/esp-handset.desktop"
install -m 644 "$ROOT/session/autostart-phone.desktop" \
  "$USER_HOME/.config/autostart/esp-handset-phone.desktop"
install -m 644 "$ROOT/session/return-to-phone.desktop" \
  "$USER_HOME/.local/share/applications/return-to-phone.desktop"
install -m 644 "$ROOT/session/return-to-phone.desktop" \
  "$USER_HOME/Desktop/return-to-phone.desktop" || true
chmod +x "$USER_HOME/Desktop/return-to-phone.desktop" 2>/dev/null || true
if command -v gio >/dev/null 2>&1; then
  sudo -u "$USER_NAME" gio set "$USER_HOME/Desktop/return-to-phone.desktop" \
    metadata::trusted true 2>/dev/null || true
fi
chown -R "$USER_NAME:$USER_NAME" "$USER_HOME/.config" \
  "$USER_HOME/.local" "$USER_HOME/Desktop" || true

if [[ -f /etc/default/zramswap ]]; then
  sed -i 's/^#\?PERCENT=.*/PERCENT=50/' /etc/default/zramswap || true
  systemctl enable zramswap.service 2>/dev/null || true
  systemctl restart zramswap.service 2>/dev/null || true
fi

# Force software mouse cursor (hardware plane often invisible after dual-head)
mkdir -p /etc/X11/xorg.conf.d
cat >/etc/X11/xorg.conf.d/20-digivice-swcursor.conf <<'EOF'
# Digivice: force software mouse cursor (vc4 HW cursor often blank)
Section "Device"
    Identifier "Digivice modesetting"
    Driver "modesetting"
    Option "SWcursor" "true"
EndSection
EOF
apt-get install -y xbitmaps x11-xserver-utils xdotool 2>/dev/null || true

systemctl daemon-reload
systemctl enable digi-buttons-inputd.service
systemctl restart digi-buttons-inputd.service || true
if [[ -x /usr/local/bin/digivice-ensure-buttons ]]; then
  bash /usr/local/bin/digivice-ensure-buttons || true
elif [[ -f "$ROOT/session/ensure-buttons.sh" ]]; then
  bash "$ROOT/session/ensure-buttons.sh" || true
fi
if [[ -x /usr/local/bin/digivice-hdmi-hotplug ]]; then
  bash /usr/local/bin/digivice-hdmi-hotplug --disable || true
elif [[ -f "$ROOT/session/hdmi-hotplug.sh" ]]; then
  bash "$ROOT/session/hdmi-hotplug.sh" --disable || true
fi
systemctl disable t9-keypad-inputd.service hat-inputd.service 2>/dev/null || true
# CardKB on Digivice (I2C) — enable; retries quietly if unplugged
systemctl enable cardkb-inputd.service 2>/dev/null || true
systemctl restart cardkb-inputd.service || true
systemctl enable esp-keyd.service
systemctl restart esp-keyd.service || true
systemctl enable ModemManager.service || true
systemctl start ModemManager.service || true

cat >/usr/local/bin/esp-handset <<EOF
#!/bin/bash
export ESP_HANDSET_PREFIX=$PREFIX
exec /usr/local/bin/handset-session phone
EOF
chmod +x /usr/local/bin/esp-handset

cat >/usr/local/bin/handset-phone <<'EOF'
#!/bin/bash
export DISPLAY="${DISPLAY:-:0}"
if [[ -z "${XAUTHORITY:-}" && -f "${HOME}/.Xauthority" ]]; then
  export XAUTHORITY="${HOME}/.Xauthority"
fi
export ESP_HANDSET_PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
export PYTHONPATH="${ESP_HANDSET_PREFIX}${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/local/bin/handset-session phone
EOF
chmod +x /usr/local/bin/handset-phone

cat >/usr/local/bin/handset-desktop <<'EOF'
#!/bin/bash
export DISPLAY="${DISPLAY:-:0}"
if [[ -z "${XAUTHORITY:-}" && -f "${HOME}/.Xauthority" ]]; then
  export XAUTHORITY="${HOME}/.Xauthority"
fi
export ESP_HANDSET_PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
export PYTHONPATH="${ESP_HANDSET_PREFIX}${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/local/bin/handset-session desktop
EOF
chmod +x /usr/local/bin/handset-desktop

cat >/usr/local/bin/digivice-leave <<'EOF'
#!/bin/bash
# Emergency: leave Digivice from SSH or a TTY when the UI is stuck.
export DISPLAY="${DISPLAY:-:0}"
if [[ -z "${XAUTHORITY:-}" && -f "${HOME}/.Xauthority" ]]; then
  export XAUTHORITY="${HOME}/.Xauthority"
fi
exec /usr/local/bin/handset-session force-desktop
EOF
chmod +x /usr/local/bin/digivice-leave
install -m 755 "$ROOT/session/digivice-start.sh" /usr/local/bin/digivice-start
install -m 755 "$ROOT/session/digivice-start.sh" "$PREFIX/session/digivice-start.sh"

cat <<EOF

=== Digivice install complete ===
DEFAULT boot: Digivice UI (phone).
HDMI + SPI: layout is HDMI-first (never --scale-from). If both black:
  digivice-unfuck-displays
  sudo digivice-recover-hdmi --now
  sudo reboot

Leave Digivice:
  handset-desktop · F12 · Ctrl+Shift+D · Settings→Linux
  (2\" SPI mirrors the full Linux desktop when you leave)

Return: handset-phone

FULL software update (git + install everything that matters):
  sudo digivice-full-update
  # first time from a clone:
  #   cd ~/esp-phone && git pull && sudo bash pi_handset/session/full-update.sh

HDMI-only repair (keeps Digivice default with --keep-phone):
  sudo digivice-recover-hdmi --keep-phone

Wiring: docs/DIGIVICE_WIRING.md · docs/DIGI_BUTTONS.md · docs/DISPLAY_MIRROR.md
Panel sideways?  sudo digivice-set-rotation 180 && sudo reboot
  (try 0, 90, 270 until upright)
SIP: sudo nano /etc/esp-handset/sip.env
EOF
