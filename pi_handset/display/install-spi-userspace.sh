#!/usr/bin/env bash
# Switch Digivice SPI to USERSACE ST7789 (Instructables / fbcp-style path).
#
# Disables mipi-dbi-spi DRM (which left Unknown19-1 dark under dual HDMI),
# frees /dev/spidev0.0, installs python deps. Digivice paints on HDMI and
# mirrors the UI over SPI bit-banged to ST7789.
#
#   sudo digivice-install-spi-userspace
#   sudo reboot
#   handset-phone
#
# Ref: https://www.instructables.com/How-to-Mirror-the-Desktop-of-RPI-OS-on-Any-St7789-/
#
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run: sudo digivice-install-spi-userspace" >&2
  exit 1
fi

echo "=== Digivice SPI userspace (ST7789 mirror, not DRM dual-head) ==="

apt-get update -qq
apt-get install -y python3-spidev python3-rpi.gpio 2>/dev/null \
  || apt-get install -y python3-spidev python3-rpi.lgpio 2>/dev/null \
  || true

BOOTCFG=""
for c in /boot/firmware/config.txt /boot/config.txt; do
  [[ -f "$c" ]] && BOOTCFG="$c" && break
done
if [[ -z "$BOOTCFG" ]]; then
  echo "ERROR: no config.txt" >&2
  exit 1
fi

# HDMI stay on — never write hdmi_force_hotplug (ghost heads break SPI mirror)
sed -i -E 's/^dtoverlay=vc4-kms-v3d(|,.*)$/dtoverlay=vc4-kms-v3d/' "$BOOTCFG" || true
if ! grep -qE '^dtoverlay=vc4-kms-v3d' "$BOOTCFG"; then
  echo "dtoverlay=vc4-kms-v3d" >>"$BOOTCFG"
fi
sed -i '/^hdmi_force_hotplug=/d' "$BOOTCFG" || true

# Remove Digivice mipi-dbi DRM block (frees SPI for spidev)
sed -i '/# --- ESP Digivice display/,/# --- END ESP Digivice display/d' "$BOOTCFG" || true
sed -i '/^dtoverlay=mipi-dbi-spi/d' "$BOOTCFG" || true
# Remove orphaned digivice dtparams that followed the overlay (best-effort strip known lines)
# Don't delete random dtparams; only ones inside removed blocks are gone.

# Keep SPI on for spidev
if ! grep -qE '^dtparam=spi=on' "$BOOTCFG"; then
  echo "dtparam=spi=on" >>"$BOOTCFG"
fi

{
  echo ""
  echo "# --- ESP Digivice SPI userspace (ST7789 mirror) ---"
  echo "# Instructables-style: app→HDMI, python pushes ST7789 via /dev/spidev0.0"
  echo "# Digivice sets ESP_HANDSET_SPI_BACKEND=userspace"
  echo "# pins: DC=25 RST=27 BL=18 CE0 — same Waveshare 2\" module"
  echo "dtparam=spi=on"
  echo "# --- END ESP Digivice SPI userspace ---"
} >>"$BOOTCFG"

mkdir -p /etc/esp-handset
echo userspace >/etc/esp-handset/spi-userspace
echo userspace >/etc/esp-handset/spi-backend
# Default rotation still applies in st7789_spi MADCTL
[[ -f /etc/esp-handset/panel-rotation ]] || echo 180 >/etc/esp-handset/panel-rotation

# Session env snippet
mkdir -p /etc/profile.d
cat >/etc/profile.d/esp-handset-spi.sh <<'EOF'
# Digivice ST7789 userspace mirror (see digivice-install-spi-userspace)
export ESP_HANDSET_SPI_BACKEND=userspace
EOF

# Also for handset service
mkdir -p /etc/esp-handset
cat >/etc/esp-handset/env <<'EOF'
ESP_HANDSET_SPI_BACKEND=userspace
ESP_HANDSET_SKIP_LAYOUT=1
EOF

echo ""
echo "OK. Wrote userspace SPI config to $BOOTCFG"
echo ">>> REBOOT REQUIRED so mipi-dbi releases SPI0:"
echo "    sudo reboot"
echo ""
echo "After reboot confirm spidev:"
echo "    ls -l /dev/spidev0.0"
echo "Then:"
echo "    export DISPLAY=:0"
echo "    export ESP_HANDSET_SPI_BACKEND=userspace"
echo "    handset-phone"
echo ""
echo "SPI should flash red then show Digivice (mirrored from the app)."
echo "HDMI still shows Digivice fullscreen."
echo "handset-desktop → SPI mirrors full Linux desktop (digivice-desktop-mirror)."
echo "Based on: https://www.instructables.com/How-to-Mirror-the-Desktop-of-RPI-OS-on-Any-St7789-/"
