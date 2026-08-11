#!/usr/bin/env bash
# Nuclear screen recovery for Digivice 2" ST7789 + optional HDMI undo.
#
#   sudo digivice-fix-screens
#
set +e
set -u

if [[ "$(id -u)" -ne 0 ]]; then
  if sudo -n true 2>/dev/null; then
    exec sudo -n env HOME="${HOME}" SUDO_USER="${SUDO_USER:-$USER}" bash "$0" "$@"
  fi
  echo "Run: sudo digivice-fix-screens" >&2
  exit 1
fi

USER_NAME="${SUDO_USER:-}"
if [[ -z "$USER_NAME" || "$USER_NAME" == "root" ]]; then
  USER_NAME="$(logname 2>/dev/null || true)"
fi
if [[ -z "$USER_NAME" || "$USER_NAME" == "root" ]]; then
  for u in pi isaac; do id "$u" >/dev/null 2>&1 && USER_NAME=$u && break; done
fi
USER_NAME="${USER_NAME:-pi}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6 || echo /home/$USER_NAME)"
PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$USER_HOME/.Xauthority}"
export ESP_HANDSET_SPI_BACKEND=userspace
export PYTHONPATH="$PREFIX:${PYTHONPATH:-}"

echo "════════════════════════════════════════"
echo " digivice-fix-screens"
echo " user=$USER_NAME  home=$USER_HOME"
echo "════════════════════════════════════════"

# --- A: kill HDMI auto-hotplug (root of prior breakage) ---
systemctl disable --now digivice-hdmi-hotplug.service 2>/dev/null || true
rm -f /etc/systemd/system/digivice-hdmi-hotplug.service
rm -f /etc/udev/rules.d/99-digivice-hdmi-hotplug.rules
systemctl daemon-reload 2>/dev/null || true
udevadm control --reload-rules 2>/dev/null || true
echo "[A] HDMI hotplug service/udev: OFF"

# --- B: config.txt cleanup ---
BOOTCFG=""
for c in /boot/firmware/config.txt /boot/config.txt; do
  [[ -f "$c" ]] && BOOTCFG="$c" && break
done
if [[ -n "$BOOTCFG" ]]; then
  cp -a "$BOOTCFG" "${BOOTCFG}.bak.digivice-fix-screens" 2>/dev/null || true
  sed -i -E 's/^dtoverlay=vc4-kms-v3d,nohdmi/dtoverlay=vc4-kms-v3d/' "$BOOTCFG"
  sed -i -E 's/^dtoverlay=vc4-kms-v3d(|,.*)$/dtoverlay=vc4-kms-v3d/' "$BOOTCFG"
  sed -i '/^hdmi_force_hotplug=/d' "$BOOTCFG"
  sed -i '/^hdmi_blanking=/d' "$BOOTCFG"
  # remove ALL mipi-dbi (frees SPI0 for spidev)
  sed -i '/# --- ESP Digivice display/,/# --- END ESP Digivice display/d' "$BOOTCFG"
  sed -i '/^dtoverlay=mipi-dbi-spi/d' "$BOOTCFG"
  if ! grep -qE '^dtparam=spi=on' "$BOOTCFG"; then
    echo "dtparam=spi=on" >>"$BOOTCFG"
  fi
  # idempotent userspace marker block (don't duplicate forever)
  if ! grep -q 'ESP Digivice SPI userspace' "$BOOTCFG"; then
    cat >>"$BOOTCFG" <<'EOF'

# --- ESP Digivice SPI userspace (ST7789 mirror) ---
dtparam=spi=on
# --- END ESP Digivice SPI userspace ---
EOF
  fi
  echo "[B] cleaned $BOOTCFG (no force_hotplug, no mipi-dbi-spi)"
fi

# --- C: flags + deps ---
mkdir -p /etc/esp-handset
echo userspace >/etc/esp-handset/spi-userspace
echo userspace >/etc/esp-handset/spi-backend
cat >/etc/esp-handset/env <<'EOF'
ESP_HANDSET_SPI_BACKEND=userspace
ESP_HANDSET_SKIP_LAYOUT=1
EOF
[[ -f /etc/esp-handset/panel-rotation ]] || echo 180 >/etc/esp-handset/panel-rotation
apt-get install -y python3-spidev python3-rpi.gpio 2>/dev/null \
  || apt-get install -y python3-spidev python3-rpi.lgpio 2>/dev/null || true
echo "[C] /etc/esp-handset userspace + python spidev"

# --- D: free SPI process hold ---
pkill -9 -f handset_app.py 2>/dev/null || true
pkill -9 -f desktop_spi_mirror.py 2>/dev/null || true
pkill -9 -f pointer_overlay.py 2>/dev/null || true
sleep 0.5
echo "[D] killed Digivice/mirror/pointer"

# --- E: hardware flash test ---
FLASH=""
for f in \
  /usr/local/bin/digivice-spi-flash \
  "$PREFIX/session/spi-flash.sh" \
  "$(dirname "$0")/spi-flash.sh"
do
  [[ -f "$f" ]] && FLASH="$f" && break
done

echo "[E] SPI hardware flash test…"
if [[ -n "$FLASH" ]]; then
  bash "$FLASH"
  FLASH_RC=$?
else
  echo "  spi-flash.sh missing — inline flash"
  python3 - <<'PY'
import sys, time
sys.path.insert(0, "/opt/esp-handset")
try:
    from esp_handset import st7789_spi as st
except Exception as e:
    print("import fail", e); sys.exit(3)
if st.ready():
    st.close(blank_panel=False)
if not st.init():
    print("init fail"); sys.exit(4)
st.wake_display()
for r,g,b,n in [(255,0,0,"R"),(0,255,0,"G"),(0,0,255,"B")]:
    print(n); st.fill(r,g,b); st.wake_display(); time.sleep(1.2)
st.fill(0,200,0); st.wake_display(); st.close(blank_panel=False)
print("inline flash ok")
PY
  FLASH_RC=$?
fi

if [[ ! -e /dev/spidev0.0 ]]; then
  echo ""
  echo ">>> NO /dev/spidev0.0 after cleanup — REBOOT then re-run:"
  echo "    sudo reboot"
  echo "    sudo digivice-fix-screens"
  exit 2
fi

if [[ "$FLASH_RC" -ne 0 ]]; then
  echo ""
  echo ">>> HARDWARE FLASH FAILED (rc=$FLASH_RC)"
  echo "    Check: SPI wiring DC=25 RST=27 BL=18 CE0, 3.3V, GND"
  echo "    dmesg | tail -30"
  echo "    If first time after removing mipi-dbi: sudo reboot"
  exit "$FLASH_RC"
fi

echo "[E] FLASH OK — 2\" should have shown color bars / green"

# --- F: start Digivice ---
mkdir -p "$USER_HOME/.esp-handset"
echo phone >"$USER_HOME/.esp-handset/session_mode"
echo phone >/etc/esp-handset/ui_mode
chown -R "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset" 2>/dev/null || true

if [[ -x /usr/local/bin/handset-phone ]]; then
  echo "[F] starting handset-phone…"
  sudo -u "$USER_NAME" env \
    DISPLAY=:0 \
    XAUTHORITY="$USER_HOME/.Xauthority" \
    HOME="$USER_HOME" \
    ESP_HANDSET_SPI_BACKEND=userspace \
    PYTHONPATH="$PREFIX" \
    nohup /usr/local/bin/handset-phone \
    >>"$USER_HOME/.esp-handset/handset.log" 2>&1 &
  sleep 2
  if pgrep -f handset_app.py >/dev/null; then
    echo "[F] Digivice process is running"
  else
    echo "[F] Digivice failed to stay up — log tail:"
    tail -n 40 "$USER_HOME/.esp-handset/handset.log" 2>/dev/null
  fi
else
  echo "[F] handset-phone not installed"
fi

echo ""
echo "════════════════════════════════════════"
echo " If colors flashed but Digivice UI still missing on 2\":"
echo "   tail -50 $USER_HOME/.esp-handset/handset.log | grep -i spi"
echo " Desktop SPI later:"
echo "   handset-desktop && digivice-desktop-mirror doctor"
echo " Full reboot if config.txt just changed:"
echo "   sudo reboot && after: sudo digivice-spi-flash"
echo "════════════════════════════════════════"
