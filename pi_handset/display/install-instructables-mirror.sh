#!/usr/bin/env bash
# Digivice: Instructables-style ST7789 desktop path.
#
# Source guide:
#   https://www.instructables.com/How-to-Mirror-the-Desktop-of-RPI-OS-on-Any-St7789-/
#
# That guide runs Adafruit's adafruit-pitft.py (option ST7789 2.0"), which:
#   • loads ST7789 as a *real* DRM panel (mipi-dbi-spi / tinydrm)
#   • lets RPi OS draw the desktop onto the SPI display
#   • is NOT "Qt grabs X11 and bitbangs SPI" (our earlier approximation)
#
# On Bookworm, true fbcp is broken; the working equivalent is:
#   mipi-dbi DRM head + enable SPI output + (optionally) clone/scale HDMI → SPI.
#
# Waveshare 2" wiring (this project), not Adafruit stock BL=22:
#   MOSI=10  SCLK=11  CE0=8  DC=25  RST=27  BL=18
#
#   sudo digivice-install-instructables
#   sudo reboot
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run: sudo digivice-install-instructables" >&2
  exit 1
fi

echo "=== Digivice Instructables ST7789 path (Adafruit-style DRM panel) ==="
echo "Ref: https://www.instructables.com/How-to-Mirror-the-Desktop-of-RPI-OS-on-Any-St7789-/"
echo ""

# Kill userspace grabbers — DRM owns SPI after this
pkill -9 -f desktop_spi_mirror.py 2>/dev/null || true
pkill -9 -f handset_app.py 2>/dev/null || true
rm -f /tmp/digivice-st7789.lock /run/digivice-st7789.lock 2>/dev/null || true

# Package bits used by panel + clone
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq 2>/dev/null || true
apt-get install -y x11-xserver-utils wlr-randr 2>/dev/null || true

# Build/install Waveshare MIPI-DBI firmware + config.txt overlay
if [[ -f "$ROOT/install-display.sh" ]]; then
  bash "$ROOT/install-display.sh"
elif [[ -f "$PREFIX/display/install-display.sh" ]]; then
  bash "$PREFIX/display/install-display.sh"
else
  echo "ERROR: install-display.sh not found next to $0" >&2
  exit 1
fi

# Drop ALL userspace-spidev flags (they fight mipi-dbi)
rm -f /etc/esp-handset/spi-userspace
echo drm >/etc/esp-handset/spi-backend
mkdir -p /etc/esp-handset
cat >/etc/esp-handset/env <<'EOF'
# Instructables / Adafruit PiTFT model: OS draws on ST7789 DRM
ESP_HANDSET_SPI_BACKEND=drm
# Do not thrash layout for dual-head — activate SPI via digivice-spi-drm-activate
ESP_HANDSET_SKIP_LAYOUT=0
EOF

mkdir -p /etc/profile.d
cat >/etc/profile.d/esp-handset-spi.sh <<'EOF'
export ESP_HANDSET_SPI_BACKEND=drm
EOF

# Stamp so full-update knows not to re-force userspace
echo "instructables-drm $(date -Iseconds)" >/etc/esp-handset/display-mode
echo "instructables" >/etc/esp-handset/spi-mode

# Install desktop-activate helper
ACT_SRC="$ROOT/../session/spi-drm-activate.sh"
if [[ ! -f "$ACT_SRC" ]]; then
  ACT_SRC="$(cd "$ROOT/.." && pwd)/session/spi-drm-activate.sh"
fi
if [[ -f "$ACT_SRC" ]]; then
  mkdir -p "$PREFIX/session"
  install -m 755 "$ACT_SRC" "$PREFIX/session/spi-drm-activate.sh"
  install -m 755 "$ACT_SRC" /usr/local/bin/digivice-spi-drm-activate
fi

# Autostart for GUI user: enable SPI head after login (Bookworm = 2nd display)
for home in /home/*; do
  [[ -d "$home" ]] || continue
  u="$(basename "$home")"
  mkdir -p "$home/.config/autostart"
  cat >"$home/.config/autostart/digivice-spi-drm.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Digivice SPI DRM activate
Comment=Instructables path: enable ST7789 KMS panel after login
Exec=/usr/local/bin/digivice-spi-drm-activate
X-GNOME-Autostart-enabled=true
EOF
  chown -R "$u:$u" "$home/.config/autostart" 2>/dev/null || true
done

# Strip userspace-only boot block if present (mipi already written by install-display)
BOOTCFG=""
for c in /boot/firmware/config.txt /boot/config.txt; do
  [[ -f "$c" ]] && BOOTCFG="$c" && break
done
if [[ -n "$BOOTCFG" ]]; then
  sed -i '/# --- ESP Digivice SPI userspace/,/# --- END ESP Digivice SPI userspace/d' "$BOOTCFG" || true
  # Never add fbcp-era hdmi_force_hotplug (Bookworm + dual SPI static)
  sed -i '/^hdmi_force_hotplug=/d' "$BOOTCFG" || true
fi

echo ""
echo "OK — Instructables/DRM path installed."
echo "  Panel: mipi-dbi-spi 240×320  DC=25 RST=27 BL=18"
echo "  Backend: drm (OS draws desktop + Digivice can use SPI QScreen)"
echo "  Activate: digivice-spi-drm-activate (autostarts at login)"
echo ""
echo ">>> REBOOT REQUIRED:"
echo "    sudo reboot"
echo ""
echo "After reboot, if 2\" is still blank:"
echo "  digivice-spi-drm-activate"
echo "  # or Screen Configuration → enable SPI / Unknown output"
echo ""
