#!/usr/bin/env bash
# Set Waveshare 2" ST7789 panel orientation. Requires reboot.
#
#   sudo digivice-set-rotation 0
#   sudo digivice-set-rotation 90
#   sudo digivice-set-rotation 180
#   sudo digivice-set-rotation 270
#
# Or: 0x00 / 0x60 / 0xc0 / 0xa0 (MADCTL)
#
# Preference saved in /etc/esp-handset/panel-rotation (degrees).
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run: sudo digivice-set-rotation 180   # or 0 90 270" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")" && pwd)"
# Prefer installed tree when present
if [[ -d /opt/esp-handset/display ]]; then
  ROOT=/opt/esp-handset/display
fi

ARG="${1:-}"
if [[ -z "$ARG" ]]; then
  cat >&2 <<'EOF'
Usage: sudo digivice-set-rotation <0|90|180|270>

  0   = upright phone (240×320)
  90  = turn right (sideways)
  180 = upside-down fix (try this first if text is inverted)
  270 = turn left (sideways)

After: sudo reboot
EOF
  exit 1
fi

# Normalize
ARG="$(echo "$ARG" | tr 'A-F' 'a-f' | sed 's/^0x//')"
DEGREES=""
MADCTL=""
W=240
H=320

case "$ARG" in
  0|00)
    DEGREES=0
    MADCTL=00
    W=240
    H=320
    ;;
  90|60)
    DEGREES=90
    MADCTL=60
    W=320
    H=240
    ;;
  180|c0)
    DEGREES=180
    MADCTL=c0
    W=240
    H=320
    ;;
  270|a0)
    DEGREES=270
    MADCTL=a0
    W=320
    H=240
    ;;
  70)
    # Waveshare demo landscape MADCTL
    DEGREES=90
    MADCTL=70
    W=320
    H=240
    ;;
  *)
    echo "Unknown: $ARG  (use 0 90 180 270)" >&2
    exit 1
    ;;
esac

TXT_SRC="$ROOT/waveshare2inch.txt"
if [[ ! -f "$TXT_SRC" ]]; then
  echo "Missing $TXT_SRC" >&2
  exit 1
fi

mkdir -p /etc/esp-handset /lib/firmware
echo "$DEGREES" >/etc/esp-handset/panel-rotation
# Stamp so digivice-full-update keeps this pick (vs migrating legacy 180→0)
echo "$DEGREES" >/etc/esp-handset/panel-rotation.user

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
# Ensure MADCTL line exists and set it
if grep -qE '^command 0x36' "$TXT_SRC"; then
  sed -E "s/^command 0x36 .*/command 0x36 0x${MADCTL}/" "$TXT_SRC" >"$TMP"
else
  # insert after 0x3A
  awk -v m="$MADCTL" '
    { print }
    /^command 0x3A/ { print "command 0x36 0x" m }
  ' "$TXT_SRC" >"$TMP"
fi

CMD="$ROOT/mipi-dbi-cmd"
[[ -x "$CMD" ]] || CMD="python3 $ROOT/mipi-dbi-cmd"
if python3 "$ROOT/mipi-dbi-cmd" /lib/firmware/waveshare2inch.bin "$TMP"; then
  :
else
  echo "WARN: mipi-dbi-cmd failed (DRM firmware)" >&2
  if [[ -f /etc/esp-handset/spi-userspace ]]; then
    echo "Userspace SPI: preference saved — reboot Digivice / Pi to apply MADCTL" >&2
  else
    echo "Panel preference still saved in /etc/esp-handset/panel-rotation" >&2
  fi
fi
cp -f /lib/firmware/waveshare2inch.bin /lib/firmware/panel.bin 2>/dev/null || true
# Keep source tree copy in sync when under /opt
if [[ -w "$ROOT/waveshare2inch.txt" ]]; then
  cp -f "$TMP" "$ROOT/waveshare2inch.txt" 2>/dev/null || true
fi

BOOTCFG=""
for cand in /boot/firmware/config.txt /boot/config.txt; do
  if [[ -f "$cand" ]]; then
    BOOTCFG="$cand"
    break
  fi
done
if [[ -z "$BOOTCFG" ]]; then
  echo "No config.txt — firmware MADCTL set only" >&2
  echo "MADCTL=0x${MADCTL} ${DEGREES}°  → sudo reboot"
  exit 0
fi

# Patch width/height inside Digivice block (or any mipi-dbi dtparam)
if grep -q 'dtparam=width=' "$BOOTCFG"; then
  sed -i -E "s/dtparam=width=[0-9]+,height=[0-9]+/dtparam=width=${W},height=${H}/" "$BOOTCFG"
  # width-mm may stay; fine
  echo "config.txt width×height → ${W}×${H}"
else
  echo "WARN: no dtparam=width in $BOOTCFG — re-run install-display after reboot" >&2
fi

echo ""
echo "Panel rotation set: ${DEGREES}°  (MADCTL=0x${MADCTL}, mode ${W}x${H})"
echo "Reboot now:  sudo reboot"
echo "If still wrong:  sudo digivice-set-rotation 90   # try 0 → 180 → 90 → 270"
