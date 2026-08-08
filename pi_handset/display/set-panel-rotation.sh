#!/usr/bin/env bash
# Rebuild Waveshare 2" panel firmware with a MADCTL rotation byte.
# Usage (on Pi):
#   sudo ./set-panel-rotation.sh 00    # factory default
#   sudo ./set-panel-rotation.sh c0    # 180°
#   sudo ./set-panel-rotation.sh 60    # often 90° (may need W/H swap in config)
#   sudo ./set-panel-rotation.sh a0    # often 270°
# Reboot after changing.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
ROT="${1:-00}"
ROT="$(echo "$ROT" | tr 'A-F' 'a-f' | sed 's/^0x//')"
case "$ROT" in
  00|c0|60|a0|70|b0|40|80) ;;
  *)
    echo "Use one of: 00 c0 60 a0  (try c0 first if upside-down)" >&2
    exit 1
    ;;
esac

TXT="$(mktemp)"
trap 'rm -f "$TXT"' EXIT
sed "s/^command 0x36 .*/command 0x36 0x${ROT}/" "$ROOT/waveshare2inch.txt" >"$TXT"
echo "MADCTL = 0x${ROT}"
python3 "$ROOT/mipi-dbi-cmd" /lib/firmware/waveshare2inch.bin "$TXT"
cp -f /lib/firmware/waveshare2inch.bin /lib/firmware/panel.bin
echo "Installed. Reboot: sudo reboot"
