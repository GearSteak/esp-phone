#!/usr/bin/env bash
# Ensure Digivice hard-button daemon is installed, enabled, and running on boot.
# Also installs udev + xdotool so keys reach Digivice GUI (not only /dev/input).
#
#   sudo digivice-ensure-buttons
#   sudo digivice-ensure-buttons --doctor
#
set +e
set -u
PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
SCRIPT="$PREFIX/buttons_inputd.py"
UNIT=/etc/systemd/system/digi-buttons-inputd.service
UDEV=/etc/udev/rules.d/99-digivice-buttons.rules
DOCTOR=0

for a in "$@"; do
  [[ "$a" == "--doctor" || "$a" == "doctor" ]] && DOCTOR=1
done

if [[ "$(id -u)" -ne 0 ]]; then
  if sudo -n true 2>/dev/null; then
    exec sudo -n env ESP_HANDSET_PREFIX="$PREFIX" bash "$0" "$@"
  fi
  echo "[ensure-buttons] need root (or passwordless sudo)" >&2
  exit 1
fi

# Resolve real GUI user (for XAUTHORITY / groups)
GUI_USER="${SUDO_USER:-}"
if [[ -z "$GUI_USER" || "$GUI_USER" == "root" ]]; then
  GUI_USER="$(logname 2>/dev/null || true)"
fi
if [[ -z "$GUI_USER" || "$GUI_USER" == "root" ]]; then
  for u in pi isaac; do
    if id "$u" >/dev/null 2>&1; then GUI_USER=$u; break; fi
  done
fi
GUI_HOME="$(getent passwd "${GUI_USER:-pi}" | cut -d: -f6 || echo /home/pi)"

install_script() {
  if [[ -f "$SCRIPT" ]]; then
    return 0
  fi
  local alt
  alt="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)/esp_handset/buttons_inputd.py"
  if [[ -f "$alt" ]]; then
    mkdir -p "$PREFIX"
    install -m 755 "$alt" "$SCRIPT"
    return 0
  fi
  echo "[ensure-buttons] missing $SCRIPT" >&2
  return 1
}

install_deps() {
  command -v xdotool >/dev/null 2>&1 || apt-get install -y xdotool >/dev/null 2>&1 || true
  python3 -c "import uinput" 2>/dev/null || apt-get install -y python3-uinput >/dev/null 2>&1 || true
  python3 -c "import RPi.GPIO" 2>/dev/null \
    || python3 -c "import lgpio" 2>/dev/null \
    || apt-get install -y python3-rpi.gpio python3-lgpio >/dev/null 2>&1 || true
  modprobe uinput 2>/dev/null || true
  # Persistent module
  if [[ ! -f /etc/modules-load.d/uinput.conf ]]; then
    echo uinput >/etc/modules-load.d/uinput.conf
  fi
  if id "${GUI_USER:-}" >/dev/null 2>&1; then
    usermod -aG input,gpio "${GUI_USER}" 2>/dev/null || usermod -aG input "${GUI_USER}" 2>/dev/null || true
  fi
}

install_udev() {
  cat >"$UDEV" <<'EOF'
# Digivice hard buttons — let the seat / X see the virtual keyboard
KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"
SUBSYSTEM=="input", KERNEL=="event*", ATTRS{name}=="Digivice-Buttons", \
  MODE="0666", GROUP="input", \
  ENV{ID_INPUT}="1", ENV{ID_INPUT_KEYBOARD}="1", \
  ENV{ID_INPUT_KEY}="1", TAG+="uaccess", TAG+="seat"
EOF
  udevadm control --reload-rules 2>/dev/null || true
  udevadm trigger 2>/dev/null || true
}

write_unit() {
  local xauth="${GUI_HOME}/.Xauthority"
  cat >"$UNIT" <<EOF
[Unit]
Description=Digivice hard buttons (GPIO → keys)
After=multi-user.target systemd-udev-settle.service
Wants=multi-user.target

[Service]
Type=simple
User=root
# Reach X11 Digivice session (xdotool + uinput)
Environment=DISPLAY=:0
Environment=XAUTHORITY=$xauth
Environment=ESP_HANDSET_PREFIX=$PREFIX
ExecStartPre=-/sbin/modprobe uinput
ExecStart=/usr/bin/python3 $SCRIPT
Restart=always
RestartSec=1

[Install]
WantedBy=multi-user.target
EOF
}

run_doctor() {
  echo "=== digivice-buttons doctor ==="
  echo "GUI user: ${GUI_USER:-?}  home: $GUI_HOME"
  echo "script: $SCRIPT  exists=$([[ -f $SCRIPT ]] && echo yes || echo NO)"
  systemctl is-enabled digi-buttons-inputd 2>&1 || true
  systemctl is-active digi-buttons-inputd 2>&1 || true
  echo "--- unit ---"
  systemctl cat digi-buttons-inputd 2>&1 | head -n 30
  echo "--- last log ---"
  journalctl -u digi-buttons-inputd -n 40 --no-pager 2>&1
  echo "--- input nodes ---"
  grep -A4 -i digivice /proc/bus/input/devices 2>/dev/null || echo "(no Digivice-Buttons in /proc)"
  echo "--- packages ---"
  python3 -c "import uinput; print('uinput OK')" 2>&1
  python3 -c "import RPi.GPIO; print('RPi.GPIO OK')" 2>&1 \
    || python3 -c "import lgpio; print('lgpio OK')" 2>&1
  command -v xdotool >/dev/null && echo "xdotool OK" || echo "xdotool MISSING"
  echo "--- live GPIO sample (1s) BCM 5,6,12,13,16,19,20 ---"
  python3 - <<'PY' 2>&1 || true
import time
try:
    import RPi.GPIO as G
    G.setmode(G.BCM)
    G.setwarnings(False)
    pins = (5, 6, 12, 13, 16, 19, 20)
    for p in pins:
        G.setup(p, G.IN, pull_up_down=G.PUD_UP)
    for _ in range(20):
        print({p: G.input(p) for p in pins})
        time.sleep(0.05)
    G.cleanup()
except Exception as e:
    print("gpio sample failed:", e)
PY
  echo "Press each button once — journal should show PRESS lines:"
  echo "  journalctl -u digi-buttons-inputd -f"
  echo "=== end doctor ==="
}

install_script || exit 1
install_deps
install_udev
write_unit
systemctl daemon-reload
systemctl enable digi-buttons-inputd.service
systemctl restart digi-buttons-inputd.service
sleep 0.4

if [[ "$DOCTOR" -eq 1 ]]; then
  run_doctor
fi

if systemctl is-active --quiet digi-buttons-inputd.service; then
  echo "[ensure-buttons] digi-buttons-inputd active + enabled on boot"
  echo "  Press a button then:  journalctl -u digi-buttons-inputd -n 5 --no-pager"
  echo "  Expect: PRESS UP / PRESS CONFIRM …"
  exit 0
fi

echo "[ensure-buttons] FAILED to start" >&2
run_doctor
exit 1
