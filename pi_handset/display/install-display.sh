#!/usr/bin/env bash
# Waveshare 2" ST7789 via mipi-dbi-spi + HDMI (never nohdmi).
# Re-run after fixing blank SPI; always reboot for firmware/DT to take effect.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
FW_NAME="waveshare2inch"
FW_BIN="/lib/firmware/${FW_NAME}.bin"
DC_GPIO=25
RST_GPIO=27
BL_GPIO=18
# 32 MHz is the overlay default; 40 M was flaky on some Zero 2 W runs
SPI_HZ=32000000

DEGREES="${ESP_PANEL_ROTATION:-}"
if [[ -z "$DEGREES" && -f /etc/esp-handset/panel-rotation ]]; then
  DEGREES="$(tr -d '[:space:]' </etc/esp-handset/panel-rotation)"
fi
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

echo "=== Digivice SPI panel install (${W}x${H}, rot=${DEGREES}°, MADCTL=0x${MADCTL}) ==="

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

if ! python3 "$ROOT/mipi-dbi-cmd" "$TMP_BIN" "$TMP_TXT"; then
  echo "ERROR: mipi-dbi-cmd failed building firmware" >&2
  exit 1
fi

# Verify MIPI DBI magic (must NOT be text /dtoverlay garbage)
MAGIC=$(head -c 8 "$TMP_BIN" | tr -d '\0' || true)
if [[ "$MAGIC" != "MIPI DBI" ]]; then
  echo "ERROR: firmware magic is '$MAGIC' (want 'MIPI DBI')" >&2
  exit 1
fi

install -m 644 "$TMP_BIN" "$FW_BIN"
install -m 644 "$TMP_BIN" /lib/firmware/panel.bin
# Also under /lib/firmware/mipi/ for some loaders
mkdir -p /lib/firmware/mipi 2>/dev/null || true
install -m 644 "$TMP_BIN" /lib/firmware/mipi/panel.bin 2>/dev/null || true
echo "Firmware OK: $FW_BIN + /lib/firmware/panel.bin ($(wc -c <"$FW_BIN") bytes, magic MIPI DBI)"
rm -f /lib/firmware/waveshare13hat.bin 2>/dev/null || true

BOOTCFG=""
for cand in /boot/firmware/config.txt /boot/config.txt; do
  if [[ -f "$cand" ]]; then
    BOOTCFG="$cand"
    break
  fi
done
if [[ -z "$BOOTCFG" ]]; then
  echo "ERROR: no config.txt" >&2
  exit 1
fi

# HDMI always available
if grep -qE '^dtoverlay=vc4-kms-v3d' "$BOOTCFG"; then
  sed -i -E 's/^dtoverlay=vc4-kms-v3d(|,.*)$/dtoverlay=vc4-kms-v3d/' "$BOOTCFG"
else
  echo "dtoverlay=vc4-kms-v3d" >>"$BOOTCFG"
fi
# Drop legacy nohdmi if present elsewhere
sed -i -E 's/,nohdmi//' "$BOOTCFG" 2>/dev/null || true

# Remove old Digivice blocks (all variants)
sed -i '/# --- ESP Digivice display/,/# --- END ESP Digivice display/d' "$BOOTCFG" || true
sed -i '/# --- ESP Digivice HAT/,/# See docs\/WAVESHARE_13_LCD_HAT.md/d' "$BOOTCFG" || true
# Remove stray older mipi-dbi lines that can double-bind SPI
sed -i '/^dtoverlay=mipi-dbi-spi/d' "$BOOTCFG" || true

{
  echo ""
  echo "# --- ESP Digivice display (Waveshare 2inch ST7789, rot=${DEGREES}) ---"
  echo "# Connector may show as SPI-1 or Unknown19-1 — both are this panel (KMS name)."
  echo "# Firmware: /lib/firmware/waveshare2inch.bin (+ panel.bin). Reboot required."
  echo "# NEVER dtoverlay=vc4-kms-v3d,nohdmi"
  echo "dtparam=spi=on"
  # One coherent overlay line + params that attach to it
  echo "dtoverlay=mipi-dbi-spi,spi0-0,speed=${SPI_HZ}"
  # shellcheck disable=SC2028
  echo "dtparam=compatible=${FW_NAME}\\0panel-mipi-dbi-spi"
  echo "dtparam=write-only"
  echo "dtparam=width=${W},height=${H},width-mm=31,height-mm=41"
  echo "dtparam=reset-gpio=${RST_GPIO},dc-gpio=${DC_GPIO},backlight-gpio=${BL_GPIO}"
  echo "# --- END ESP Digivice display ---"
} >>"$BOOTCFG"

echo "config.txt → $BOOTCFG"
echo "  overlay: mipi-dbi-spi spi0-0 ${W}x${H} @ ${SPI_HZ}Hz"
echo "  pins: DC=${DC_GPIO} RST=${RST_GPIO} BL=${BL_GPIO}"
echo ""
echo ">>> MUST reboot for SPI firmware/DT change:  sudo reboot"
echo "After reboot: digivice-spi-doctor"
echo "If sideways: sudo digivice-set-rotation 0|90|180|270 && sudo reboot"
