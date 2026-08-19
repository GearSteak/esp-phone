#!/usr/bin/env bash
# Ensure Digivice CardKB (I2C @ 0x5F) daemon is healthy.
#   sudo digivice-ensure-cardkb
#   sudo digivice-ensure-cardkb --doctor
set -euo pipefail

UNIT=/etc/systemd/system/cardkb-inputd.service
PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
SCRIPT="$PREFIX/cardkb_inputd.py"
ROOT="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd || true)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[ensure-cardkb] need root (or passwordless sudo)" >&2
  exit 1
fi

if [[ ! -f "$SCRIPT" && -n "$ROOT" && -f "$ROOT/esp_handset/cardkb_inputd.py" ]]; then
  install -m 755 "$ROOT/esp_handset/cardkb_inputd.py" "$SCRIPT"
fi
if [[ ! -f "$SCRIPT" ]]; then
  echo "[ensure-cardkb] missing $SCRIPT" >&2
  exit 1
fi

doctor() {
  echo "=== CardKB doctor ==="
  echo "--- packages ---"
  python3 -c "import uinput; print('uinput OK')" 2>&1 || true
  python3 -c "import smbus2; print('smbus2 OK')" 2>&1 \
    || python3 -c "import smbus; print('smbus OK')" 2>&1 || true
  command -v i2cdetect >/dev/null && echo "i2cdetect OK" || echo "i2c-tools MISSING"
  echo "(desktop uses uinput, not xdotool)"
  echo "--- i2c ---"
  ls -l /dev/i2c-1 2>&1 || echo "no /dev/i2c-1 — enable I2C (raspi-config)"
  if command -v i2cdetect >/dev/null 2>&1 && [[ -e /dev/i2c-1 ]]; then
    i2cdetect -y 1 2>&1 || true
    echo "(want '5f' in the grid — CardKB)"
  fi
  echo "--- baudrate ---"
  grep -n 'i2c_arm' /boot/firmware/config.txt /boot/config.txt 2>/dev/null || true
  echo "--- service ---"
  systemctl is-enabled cardkb-inputd 2>&1 || true
  systemctl is-active cardkb-inputd 2>&1 || true
  systemctl cat cardkb-inputd 2>&1 | head -n 25 || true
  echo "--- linux keyboard ---"
  grep -A6 -i 'Digivice-Buttons' /proc/bus/input/devices 2>/dev/null \
    || echo "(no Digivice-Buttons — pad daemon down; CardKB types through it)"
  if [[ -S /run/digivice/type.sock ]]; then
    echo "type socket OK /run/digivice/type.sock"
  else
    echo "NO type socket — start digi-buttons-inputd (CardKB has nothing to type through)"
  fi
  grep -A6 -i 'Digivice-CardKB' /proc/bus/input/devices 2>/dev/null \
    && echo "(fallback Digivice-CardKB present — Bluetooth may glitch; reboot after update)" \
    || echo "(no Digivice-CardKB fallback device — good)"
  echo "--- pause ---"
  paused=0
  for pf in /run/digivice/cardkb.pause /tmp/digivice-cardkb.pause; do
    if [[ -f "$pf" ]]; then
      echo "PAUSE FILE present: $pf  (ls: $(ls -l "$pf" 2>/dev/null))"
      paused=1
    fi
  done
  if [[ "$paused" -eq 0 ]]; then
    echo "no pause file — daemon should type into Linux"
  else
    echo "I2C is paused for Digivice — on Linux desktop this file must be ABSENT"
  fi
  echo "--- unit After= (must NOT be multi-user.target — that drops boot start) ---"
  systemctl show -p After -p Before -p WantedBy -p ActiveState cardkb-inputd 2>/dev/null || true
  echo "--- journal (last 30) ---"
  journalctl -u cardkb-inputd -n 30 --no-pager 2>&1 || true
  echo "=== wiring reminder ==="
  echo "  CardKB 5V  → Pi pin 2"
  echo "  CardKB GND → Pi pin 6"
  echo "  CardKB SDA → Pi pin 3 (BCM2)"
  echo "  CardKB SCL → Pi pin 5 (BCM3)"
  echo "  NOT 3.3V. Reboot once after baudrate change."
  echo "  Verbose test: sudo python3 $SCRIPT -v"
}

if [[ "${1:-}" == "--doctor" ]]; then
  doctor
  exit 0
fi

if [[ "${1:-}" == "--if-needed" ]]; then
  mkdir -p /run/digivice
  chmod 0777 /run/digivice || true
  systemctl start cardkb-inputd.service 2>/dev/null || true
  echo "[ensure-cardkb] if-needed: $(systemctl is-active cardkb-inputd 2>/dev/null || echo down)"
  exit 0
fi

echo "[ensure-cardkb] installing deps…"
apt-get install -y python3-uinput python3-smbus2 i2c-tools >/dev/null 2>&1 \
  || apt-get install -y python3-uinput python3-smbus i2c-tools >/dev/null 2>&1 \
  || true
modprobe uinput 2>/dev/null || true
modprobe i2c-dev 2>/dev/null || true
if [[ ! -f /etc/modules-load.d/uinput.conf ]]; then
  echo uinput >/etc/modules-load.d/uinput.conf
fi

mkdir -p /run/digivice
chmod 0777 /run/digivice
cat >/etc/tmpfiles.d/digivice-cardkb.conf <<'EOF'
d /run/digivice 0777 root root -
EOF

cat >/etc/udev/rules.d/99-digivice-cardkb.rules <<'EOF'
# CardKB virtual keyboard — labwc/libinput must see it as a seat keyboard
KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"
SUBSYSTEM=="input", KERNEL=="event*", ATTRS{name}=="Digivice-CardKB", \
  MODE="0666", GROUP="input", \
  ENV{ID_INPUT}="1", ENV{ID_INPUT_KEYBOARD}="1", \
  ENV{ID_INPUT_KEY}="1", TAG+="uaccess", TAG+="seat"
EOF
cat >/etc/udev/hwdb.d/61-digivice-cardkb.hwdb <<'EOF'
evdev:name:Digivice-CardKB:*
 ID_INPUT_KEYBOARD=1
 ID_INPUT_KEY=1
EOF
udevadm hwdb --update 2>/dev/null || systemd-hwdb update 2>/dev/null || true
udevadm control --reload-rules 2>/dev/null || true
# Do NOT `udevadm trigger --subsystem-match=input` — that re-enumerates
# Bluetooth HID keyboards and they drop off the seat.

# Enable I2C if raspi-config available
if command -v raspi-config >/dev/null 2>&1; then
  raspi-config nonint do_i2c 0 2>/dev/null || true
fi

# Slow baud for Pi Zero clock-stretch
for cfg in /boot/firmware/config.txt /boot/config.txt; do
  if [[ -f "$cfg" ]] && ! grep -q 'i2c_arm_baudrate' "$cfg" 2>/dev/null; then
    echo "" >>"$cfg"
    echo "# Digivice CardKB — avoid I2C hang after first key" >>"$cfg"
    echo "dtparam=i2c_arm_baudrate=50000" >>"$cfg"
    echo "[ensure-cardkb] added i2c_arm_baudrate=50000 to $cfg — reboot once"
    break
  fi
done

GUI_USER="${SUDO_USER:-pi}"
id "$GUI_USER" >/dev/null 2>&1 || GUI_USER=pi
usermod -aG i2c,input "$GUI_USER" 2>/dev/null || true

cat >"$UNIT" <<EOF
[Unit]
Description=Digivice CardKB I2C → Linux desktop (via Digivice-Buttons)
# Start with the OS, before labwc. After=multi-user.target is an ordering
# cycle with WantedBy=multi-user.target — systemd then drops the boot job.
After=local-fs.target systemd-modules-load.service digi-buttons-inputd.service
Wants=digi-buttons-inputd.service
Before=graphical.target display-manager.service lightdm.service greetd.service

[Service]
Type=simple
User=root
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/${GUI_USER}/.Xauthority
ExecStartPre=-/sbin/modprobe uinput
ExecStartPre=-/sbin/modprobe i2c-dev
ExecStart=/usr/bin/python3 ${SCRIPT}
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable cardkb-inputd.service
# Restart CardKB daemon only (no extra HID). Do not udev-trigger all keyboards.
if systemctl is-active --quiet cardkb-inputd.service; then
  systemctl restart cardkb-inputd.service
  echo "[ensure-cardkb] restarted cardkb-inputd (I2C → Digivice-Buttons)"
else
  systemctl start cardkb-inputd.service
fi
sleep 1

if systemctl is-active --quiet cardkb-inputd.service; then
  echo "[ensure-cardkb] cardkb-inputd active + enabled"
  if [[ -e /dev/i2c-1 ]] && command -v i2cdetect >/dev/null; then
    echo "[ensure-cardkb] i2cdetect -y 1 (look for 5f):"
    i2cdetect -y 1 || true
  fi
  echo "  journalctl -u cardkb-inputd -f"
  echo "  sudo digivice-ensure-cardkb --doctor"
  exit 0
fi

echo "[ensure-cardkb] FAILED to start" >&2
journalctl -u cardkb-inputd -n 20 --no-pager >&2 || true
exit 1
