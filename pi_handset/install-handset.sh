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
  python3-picamera2 \
  rpicam-apps \
  linphone-cli \
  pipewire pipewire-audio wireplumber \
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

cat >/etc/udev/rules.d/99-esp-handset.rules <<'EOF'
# Espressif USB CDC — Heltec LoRa / notify bridge
SUBSYSTEM=="tty", ATTRS{idVendor}=="303a", SYMLINK+="esp-bridge", MODE="0666"
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", SYMLINK+="esp-bridge", MODE="0666"
# SimTech / SIMCom SIM7600 — USB AT
SUBSYSTEM=="tty", ATTRS{idVendor}=="1e0e", ATTRS{bInterfaceNumber}=="02", SYMLINK+="sim7600-at", MODE="0666"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1e0e", MODE="0666"
EOF
udevadm control --reload-rules || true
udevadm trigger || true

usermod -aG dialout,i2c "$USER_NAME" 2>/dev/null || usermod -aG dialout "$USER_NAME" 2>/dev/null || true
systemctl disable esp-handset-sim7600-link.service 2>/dev/null || true
rm -f /etc/systemd/system/esp-handset-sim7600-link.service \
  /usr/local/bin/esp-handset-sim7600-link
if [[ -L /dev/sim7600-at ]]; then
  real="$(readlink -f /dev/sim7600-at 2>/dev/null || true)"
  case "$real" in
    *serial0*|*ttyAMA0*|*ttyS0*) rm -f /dev/sim7600-at ;;
  esac
fi

if [[ ! -f /etc/esp-handset/sip.env ]]; then
  cat >/etc/esp-handset/sip.env <<'EOF'
SIP_SERVER=sip.example.com
SIP_USER=YOUR_USER
SIP_PASS=YOUR_PASS
SIP_DISPLAY=ESP Digivice
# Display: Waveshare 2" 240x320 SPI (docs/WAVESHARE_2INCH_LCD.md)
# Nav: 7 hard buttons → digi-buttons-inputd (docs/DIGI_BUTTONS.md)
# Cellular: SIM7600G-H USB /dev/sim7600-at
# LoRa: Heltec USB /dev/esp-bridge
EOF
fi

# SPI 2" as optional second panel — HDMI stays ON
cp -a "$ROOT/display" "$PREFIX/display"
chmod +x "$PREFIX/display/install-display.sh" "$PREFIX/display/mipi-dbi-cmd" \
  "$PREFIX/display/recover-hdmi.sh" "$PREFIX/display/set-panel-rotation.sh" 2>/dev/null || true
install -m 755 "$ROOT/display/recover-hdmi.sh" /usr/local/bin/digivice-recover-hdmi
install -m 755 "$ROOT/display/set-panel-rotation.sh" /usr/local/bin/digivice-set-rotation
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

cat >/etc/systemd/system/digi-buttons-inputd.service <<EOF
[Unit]
Description=Digivice hard buttons (D-pad + Confirm/Back/Home)
After=multi-user.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 $PREFIX/buttons_inputd.py
Restart=always
RestartSec=2

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
chown -R "$USER_NAME:$USER_NAME" "$USER_HOME/.config" \
  "$USER_HOME/.local" "$USER_HOME/Desktop" || true

if [[ -f /etc/default/zramswap ]]; then
  sed -i 's/^#\?PERCENT=.*/PERCENT=50/' /etc/default/zramswap || true
  systemctl enable zramswap.service 2>/dev/null || true
  systemctl restart zramswap.service 2>/dev/null || true
fi

systemctl daemon-reload
systemctl enable digi-buttons-inputd.service
systemctl restart digi-buttons-inputd.service || true
systemctl disable t9-keypad-inputd.service cardkb-inputd.service hat-inputd.service 2>/dev/null || true
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
exec /usr/local/bin/handset-session phone
EOF
chmod +x /usr/local/bin/handset-phone

cat >/usr/local/bin/handset-desktop <<'EOF'
#!/bin/bash
exec /usr/local/bin/handset-session desktop
EOF
chmod +x /usr/local/bin/handset-desktop

cat <<EOF

=== Digivice install complete ===
DEFAULT boot: Digivice UI (phone).
HDMI ON + SPI 2" — installer tries to MIRROR both (same Digivice picture).

Mirror help:
  handset-session mirror
  digivice-mirror-displays
  Best results: raspi-config → Advanced → Wayland → X11 (Openbox), then reboot

Leave Digivice:
  handset-desktop · F12 · Ctrl+Shift+D · Settings→Linux

Return: handset-phone

HDMI-only repair (keeps Digivice default with --keep-phone):
  sudo digivice-recover-hdmi --keep-phone

Wiring: docs/DIGIVICE_WIRING.md · docs/DIGI_BUTTONS.md · docs/DISPLAY_MIRROR.md
Panel sideways?  sudo digivice-set-rotation 180 && sudo reboot
  (try 0, 90, 270 until upright)
SIP: sudo nano /etc/esp-handset/sip.env
EOF
