#!/usr/bin/env bash
# Restore multi-monitor desktop after Digivice (SPI-only layout).
set +e
export DISPLAY="${DISPLAY:-:0}"
if command -v xrandr >/dev/null 2>&1 && xrandr --query >/dev/null 2>&1; then
  while read -r name; do
    case "$name" in
      HDMI*|hdmi*) xrandr --output "$name" --auto 2>/dev/null || true ;;
    esac
  done < <(xrandr --query 2>/dev/null | awk '/connected/{print $1}')
  # Loose auto so desktop spreads again
  xrandr --auto 2>/dev/null || true
fi
echo "Desktop displays restored (best effort)."
