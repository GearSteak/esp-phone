#!/usr/bin/env bash
# Restore multi-monitor desktop after Digivice (HDMI-first, never blank).
set +e
export DISPLAY="${DISPLAY:-:0}"
pkill -f handset_app.py 2>/dev/null || true

if command -v xrandr >/dev/null 2>&1 && xrandr --query >/dev/null 2>&1; then
  xrandr --auto 2>/dev/null || true
  mapfile -t OUTS < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
  HDMI=""
  for o in "${OUTS[@]:-}"; do
    xrandr --output "$o" --auto --on 2>/dev/null || true
    case "$o" in HDMI*|hdmi*) HDMI="${HDMI:-$o}" ;; esac
  done
  if [[ -n "$HDMI" ]]; then
    xrandr --output "$HDMI" --auto --primary --on 2>/dev/null || true
    for o in "${OUTS[@]:-}"; do
      [[ "$o" == "$HDMI" ]] && continue
      xrandr --output "$o" --auto --right-of "$HDMI" 2>/dev/null \
        || xrandr --output "$o" --auto --on 2>/dev/null || true
    done
  fi
fi
echo "Desktop displays restored (HDMI-first)."
