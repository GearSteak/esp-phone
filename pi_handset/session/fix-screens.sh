#!/usr/bin/env bash
# UNDO HDMI-hotplug damage + restore 2" ST7789 (userspace SPI).
#
# The late-plug HDMI installer wrote hdmi_force_hotplug + a udev service that
# re-ran xrandr / restarted mirrors on every DRM event — that left the small
# panel dark or frozen. This script turns that OFF and restarts Digivice SPI.
#
#   sudo digivice-fix-screens
#   # or without install:
#   sudo bash pi_handset/session/fix-screens.sh
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

echo "=== digivice-fix-screens (undo HDMI hotplug + restore SPI) ==="
echo "user=$USER_NAME home=$USER_HOME"

# 1) Kill automatic HDMI hotplug completely
systemctl disable --now digivice-hdmi-hotplug.service 2>/dev/null || true
rm -f /etc/systemd/system/digivice-hdmi-hotplug.service
rm -f /etc/udev/rules.d/99-digivice-hdmi-hotplug.rules
systemctl daemon-reload 2>/dev/null || true
udevadm control --reload-rules 2>/dev/null || true
echo "  [1] HDMI hotplug udev/service removed"

# 2) Strip force_hotplug (fake HDMI head breaks X capture + confuses modes)
BOOTCFG=""
for c in /boot/firmware/config.txt /boot/config.txt; do
  [[ -f "$c" ]] && BOOTCFG="$c" && break
done
if [[ -n "$BOOTCFG" ]]; then
  cp -a "$BOOTCFG" "${BOOTCFG}.bak.digivice-fix-screens" 2>/dev/null || true
  sed -i -E 's/^dtoverlay=vc4-kms-v3d,nohdmi/dtoverlay=vc4-kms-v3d/' "$BOOTCFG" || true
  sed -i -E 's/^dtoverlay=vc4-kms-v3d(|,.*)$/dtoverlay=vc4-kms-v3d/' "$BOOTCFG" || true
  sed -i '/^hdmi_force_hotplug=/d' "$BOOTCFG" || true
  sed -i '/^hdmi_blanking=/d' "$BOOTCFG" || true
  # keep hdmi_drive=2 if present (usually fine)
  echo "  [2] cleaned $BOOTCFG (removed hdmi_force_hotplug / blanking)"
  echo "      backup: ${BOOTCFG}.bak.digivice-fix-screens"
else
  echo "  [2] no config.txt found"
fi

# 3) Ensure userspace SPI flags (Digivice + desktop mirror path)
mkdir -p /etc/esp-handset
echo userspace >/etc/esp-handset/spi-userspace
echo userspace >/etc/esp-handset/spi-backend
cat >/etc/esp-handset/env <<'EOF'
ESP_HANDSET_SPI_BACKEND=userspace
ESP_HANDSET_SKIP_LAYOUT=1
EOF
[[ -f /etc/esp-handset/panel-rotation ]] || echo 180 >/etc/esp-handset/panel-rotation
# Make sure mipi-dbi DRM block is not fighting spidev (comment headers only — full reinstall if missing spidev)
if [[ ! -e /dev/spidev0.0 ]]; then
  echo "  [3] WARNING: /dev/spidev0.0 missing"
  if [[ -x /usr/local/bin/digivice-install-spi-userspace ]]; then
    echo "      running digivice-install-spi-userspace…"
    /usr/local/bin/digivice-install-spi-userspace || true
  elif [[ -f "$PREFIX/display/install-spi-userspace.sh" ]]; then
    bash "$PREFIX/display/install-spi-userspace.sh" || true
  fi
  if [[ ! -e /dev/spidev0.0 ]]; then
    echo "      Still no spidev — REBOOT required after install-spi-userspace"
    NEED_REBOOT=1
  fi
else
  echo "  [3] /dev/spidev0.0 OK + userspace flags set"
fi

# 4) Stop thrashing processes
pkill -f desktop_spi_mirror.py 2>/dev/null || true
pkill -f handset_app.py 2>/dev/null || true
sleep 0.6
echo "  [4] stopped handset + old mirror"

# 5) Gentle xrandr (no primary thrash) then restart Digivice on SPI
sudo -u "$USER_NAME" env DISPLAY=:0 XAUTHORITY="$USER_HOME/.Xauthority" \
  xrandr --auto 2>/dev/null || true

mkdir -p "$USER_HOME/.esp-handset"
echo phone >"$USER_HOME/.esp-handset/session_mode"
echo phone >/etc/esp-handset/ui_mode
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset/session_mode" 2>/dev/null || true

if [[ -x /usr/local/bin/handset-phone ]]; then
  echo "  [5] starting Digivice (handset-phone)…"
  sudo -u "$USER_NAME" env DISPLAY=:0 XAUTHORITY="$USER_HOME/.Xauthority" \
    HOME="$USER_HOME" ESP_HANDSET_SPI_BACKEND=userspace \
    nohup /usr/local/bin/handset-phone \
    >>"$USER_HOME/.esp-handset/handset.log" 2>&1 &
elif [[ -x /usr/local/bin/handset-session ]]; then
  sudo -u "$USER_NAME" env DISPLAY=:0 XAUTHORITY="$USER_HOME/.Xauthority" \
    HOME="$USER_HOME" ESP_HANDSET_SPI_BACKEND=userspace \
    nohup /usr/local/bin/handset-session phone \
    >>"$USER_HOME/.esp-handset/handset.log" 2>&1 &
else
  echo "  [5] handset-phone missing — launch Digivice from your usual path"
fi

sleep 1.5
echo ""
echo "Done."
echo "  Digivice should own the 2\" panel again (userspace ST7789)."
echo "  Desktop later:  handset-desktop && digivice-desktop-mirror doctor"
echo "  Log:            tail -40 $USER_HOME/.esp-handset/handset.log"
if [[ "${NEED_REBOOT:-0}" -eq 1 ]]; then
  echo ""
  echo ">>> REBOOT REQUIRED (spidev still missing):  sudo reboot"
  echo "    After reboot:  sudo digivice-fix-screens"
else
  # config.txt force_hotplug strip needs reboot to fully apply firmware side
  echo ""
  echo "If the 2\" is still wrong, reboot once so firmware drops force_hotplug:"
  echo "  sudo reboot"
fi
