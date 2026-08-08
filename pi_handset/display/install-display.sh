#!/usr/bin/env bash
# Waveshare 2" LCD Module (ST7789 240×320 SPI) as DRM primary display.
# Called from install-handset.sh. Idempotent — reboot after install.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
FW_NAME="waveshare2inch"
FW_BIN="/lib/firmware/${FW_NAME}.bin"
# Official Waveshare Pi wire: DC=25 RST=27 BL=18, SPI0 CE0
DC_GPIO=25
RST_GPIO=27
BL_GPIO=18
W=240
H=320

echo "=== Digivice display (mipi-dbi-spi ST7789 240x320 2inch) ==="

mkdir -p /lib/firmware
TMP_BIN="$(mktemp)"
if python3 "$ROOT/mipi-dbi-cmd" "$TMP_BIN" "$ROOT/waveshare2inch.txt" 2>/dev/null; then
  install -m 644 "$TMP_BIN" "$FW_BIN"
  echo "Installed $FW_BIN (from waveshare2inch.txt)"
else
  echo "WARN: rebuild failed; using prebuilt bin" >&2
  install -m 644 "$ROOT/waveshare2inch.bin" "$FW_BIN"
fi
rm -f "$TMP_BIN"
install -m 644 "$FW_BIN" /lib/firmware/panel.bin
# Drop old 1.3" firmware name so kernel does not pick stale config
rm -f /lib/firmware/waveshare13hat.bin 2>/dev/null || true

BOOTCFG=""
for cand in /boot/firmware/config.txt /boot/config.txt; do
  if [[ -f "$cand" ]]; then
    BOOTCFG="$cand"
    break
  fi
done
if [[ -z "$BOOTCFG" ]]; then
  echo "ERROR: no /boot/.../config.txt found" >&2
  exit 1
fi

if grep -qE '^dtoverlay=vc4-kms-v3d' "$BOOTCFG"; then
  sed -i -E 's/^dtoverlay=vc4-kms-v3d(|,.*)$/dtoverlay=vc4-kms-v3d,nohdmi/' "$BOOTCFG"
  echo "Set vc4-kms-v3d,nohdmi in $BOOTCFG"
fi

sed -i '/# --- ESP Digivice display/,/# --- END ESP Digivice display/d' "$BOOTCFG" || true
sed -i '/# --- ESP Digivice HAT/,/# See docs\/WAVESHARE_13_LCD_HAT.md/d' "$BOOTCFG" || true
sed -i '/# --- ESP Digivice HAT/,+3d' "$BOOTCFG" 2>/dev/null || true

{
  echo ""
  echo "# --- ESP Digivice display (Waveshare 2inch LCD ST7789 240x320) ---"
  echo "dtparam=spi=on"
  echo "dtparam=i2c_arm=on"
  if ! grep -qE '^dtoverlay=vc4-kms-v3d' "$BOOTCFG"; then
    echo "dtoverlay=vc4-kms-v3d,nohdmi"
  fi
  echo "dtoverlay=mipi-dbi-spi,spi0-0,speed=40000000"
  # shellcheck disable=SC2028
  echo "dtparam=compatible=${FW_NAME}\\0panel-mipi-dbi-spi"
  echo "dtparam=write-only"
  echo "dtparam=width=${W},height=${H},width-mm=31,height-mm=41"
  echo "dtparam=reset-gpio=${RST_GPIO},dc-gpio=${DC_GPIO},backlight-gpio=${BL_GPIO}"
  echo "# --- END ESP Digivice display ---"
} >>"$BOOTCFG"

echo "Display overlay written to $BOOTCFG"
echo "Firmware: $FW_BIN (+ /lib/firmware/panel.bin)"
echo "Wire: VCC 3V3, GND, DIN MOSI, CLK SCLK, CS CE0, DC 25, RST 27, BL 18"
echo "After reboot: dmesg | grep panel-mipi-dbi"
