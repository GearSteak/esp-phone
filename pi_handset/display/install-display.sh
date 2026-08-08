#!/usr/bin/env bash
# Waveshare 2" LCD Module (ST7789 240×320 SPI) alongside HDMI (never kill HDMI).
# Called from install-handset.sh. Idempotent — reboot after install.
#
# Orientation: /etc/esp-handset/panel-rotation = 0|90|180|270  (default 180 —
# many Waveshare 2" units need 180 from the stock MADCTL=0 mapping).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
FW_NAME="waveshare2inch"
FW_BIN="/lib/firmware/${FW_NAME}.bin"
DC_GPIO=25
RST_GPIO=27
BL_GPIO=18

# Degrees → W H MADCTL
DEGREES="${ESP_PANEL_ROTATION:-}"
if [[ -z "$DEGREES" && -f /etc/esp-handset/panel-rotation ]]; then
  DEGREES="$(tr -d '[:space:]' </etc/esp-handset/panel-rotation)"
fi
# Default 180 — common "right" fix when stock portrait looks inverted on wire
DEGREES="${DEGREES:-180}"

W=240
H=320
MADCTL=c0
case "$DEGREES" in
  0)   W=240; H=320; MADCTL=00 ;;
  90)  W=320; H=240; MADCTL=60 ;;
  180) W=240; H=320; MADCTL=c0 ;;
  270) W=320; H=240; MADCTL=a0 ;;
  *)
    echo "WARN: bad panel-rotation '$DEGREES', using 180" >&2
    DEGREES=180
    W=240; H=320; MADCTL=c0
    ;;
esac

echo "=== Digivice display (HDMI + SPI 2inch, rotation ${DEGREES}°) ==="

mkdir -p /lib/firmware /etc/esp-handset
echo "$DEGREES" >/etc/esp-handset/panel-rotation

TMP_TXT="$(mktemp)"
TMP_BIN="$(mktemp)"
trap 'rm -f "$TMP_TXT" "$TMP_BIN"' EXIT
if grep -qE '^command 0x36' "$ROOT/waveshare2inch.txt"; then
  sed -E "s/^command 0x36 .*/command 0x36 0x${MADCTL}/" "$ROOT/waveshare2inch.txt" >"$TMP_TXT"
else
  cp "$ROOT/waveshare2inch.txt" "$TMP_TXT"
fi

if python3 "$ROOT/mipi-dbi-cmd" "$TMP_BIN" "$TMP_TXT" 2>/dev/null; then
  install -m 644 "$TMP_BIN" "$FW_BIN"
  echo "Installed $FW_BIN (MADCTL=0x${MADCTL})"
else
  echo "WARN: rebuild failed; using prebuilt bin (may be wrong rotation)" >&2
  install -m 644 "$ROOT/waveshare2inch.bin" "$FW_BIN"
fi
install -m 644 "$FW_BIN" /lib/firmware/panel.bin
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
  sed -i -E 's/^dtoverlay=vc4-kms-v3d(|,.*)$/dtoverlay=vc4-kms-v3d/' "$BOOTCFG"
  echo "Ensured dtoverlay=vc4-kms-v3d  (HDMI ON) in $BOOTCFG"
fi

sed -i '/# --- ESP Digivice display/,/# --- END ESP Digivice display/d' "$BOOTCFG" || true
sed -i '/# --- ESP Digivice HAT/,/# See docs\/WAVESHARE_13_LCD_HAT.md/d' "$BOOTCFG" || true
sed -i '/# --- ESP Digivice HAT/,+3d' "$BOOTCFG" 2>/dev/null || true

{
  echo ""
  echo "# --- ESP Digivice display (Waveshare 2inch LCD ST7789, rot=${DEGREES}) ---"
  echo "# HDMI stays enabled (do NOT add nohdmi to vc4-kms-v3d)."
  echo "# Rotation: sudo digivice-set-rotation 0|90|180|270 && sudo reboot"
  echo "dtparam=spi=on"
  echo "dtparam=i2c_arm=on"
  if ! grep -qE '^dtoverlay=vc4-kms-v3d' "$BOOTCFG"; then
    echo "dtoverlay=vc4-kms-v3d"
  fi
  echo "dtoverlay=mipi-dbi-spi,spi0-0,speed=40000000"
  # shellcheck disable=SC2028
  echo "dtparam=compatible=${FW_NAME}\\0panel-mipi-dbi-spi"
  echo "dtparam=write-only"
  echo "dtparam=width=${W},height=${H},width-mm=31,height-mm=41"
  echo "dtparam=reset-gpio=${RST_GPIO},dc-gpio=${DC_GPIO},backlight-gpio=${BL_GPIO}"
  echo "# --- END ESP Digivice display ---"
} >>"$BOOTCFG"

echo "Display overlay: ${W}x${H} MADCTL=0x${MADCTL} → $BOOTCFG"
echo "If sideways/upside-down: sudo digivice-set-rotation 180  (or 0 90 270) && sudo reboot"
