#!/usr/bin/env bash
# Force Digivice layout so the 2" SPI shows the FULL UI (not a crop of HDMI).
#
# Strategy:
#  1) Find SPI / DPI panel + HDMI
#  2) SPI = primary at 240x320 (or 320x240 if rotated)
#  3) Turn HDMI off briefly so Qt only has one screen
#  4) If ESP_HANDSET_MIRROR!=0, re-enable HDMI as scaled clone of SPI
#
# Called by handset-session before launching Digivice.
set -euo pipefail

log() { echo "[digivice-layout] $*" >&2; }

MIRROR="${ESP_HANDSET_MIRROR:-1}"
ROT="$(tr -d '[:space:]' </etc/esp-handset/panel-rotation 2>/dev/null || echo 0)"
MODE="240x320"
case "$ROT" in
  90|270) MODE="320x240" ;;
esac

if ! command -v xrandr >/dev/null 2>&1 || [[ -z "${DISPLAY:-}" ]]; then
  log "no xrandr/DISPLAY — try LinuxFB or start from desktop session"
  # Wayland: turn off HDMI so only panel remains
  if command -v wlr-randr >/dev/null 2>&1; then
    while read -r name; do
      case "$name" in
        *HDMI*|*hdmi*)
          wlr-randr --output "$name" --off 2>/dev/null || true
          log "Wayland off: $name"
          ;;
        *SPI*|*DPI*|*DSI*)
          wlr-randr --output "$name" --on --pos 0,0 2>/dev/null || true
          log "Wayland on primary-ish: $name"
          ;;
      esac
    done < <(wlr-randr 2>/dev/null | awk '/^[^ ]/{print $1}')
  fi
  exit 0
fi

mapfile -t OUTS < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
SPI=""
HDMI=""
for o in "${OUTS[@]:-}"; do
  case "$o" in
    *SPI*|*DPI*|*DSI*|*PANEL*) SPI="$o" ;;
    HDMI*|hdmi*) HDMI="$o" ;;
  esac
done

# Smallest non-HDMI as panel fallback
if [[ -z "$SPI" ]]; then
  best=999999999
  for o in "${OUTS[@]:-}"; do
    case "$o" in HDMI*|hdmi*) continue ;; esac
    # shellcheck disable=SC2016
    area=$(xrandr --query | awk -v n="$o" '
      $0 ~ n" connected" {getline; if (match($0,/([0-9]+)x([0-9]+)/,a)) print a[1]*a[2]}
    ')
    area="${area:-0}"
    if [[ "$area" -gt 0 && "$area" -lt "$best" ]]; then
      best=$area
      SPI=$o
    fi
  done
fi

if [[ -z "$SPI" && ${#OUTS[@]} -gt 0 ]]; then
  SPI="${OUTS[0]}"
fi
if [[ -z "$SPI" ]]; then
  log "no outputs — nothing to do"
  exit 0
fi

log "panel=$SPI mode=$MODE  hdmi=${HDMI:-none}  mirror=$MIRROR"

# --- Critical: do not leave a large primary with SPI as a small viewport ---
if [[ -n "$HDMI" ]]; then
  xrandr --output "$HDMI" --off 2>/dev/null || true
  log "HDMI off (so Digivice cannot bind to 1080p primary)"
  sleep 0.2
fi

# SPI only, fixed Digivice resolution
ok=0
for try in "$MODE" 240x320 320x240; do
  if xrandr --output "$SPI" --mode "$try" --primary --pos 0x0 2>/dev/null; then
    log "SPI mode $try primary"
    ok=1
    MODE=$try
    break
  fi
done
if [[ "$ok" -eq 0 ]]; then
  xrandr --output "$SPI" --auto --primary --pos 0x0 2>/dev/null || true
  log "SPI --auto primary"
fi

# Optional: bring HDMI back as *clone* of the SPI plane (same full UI, scaled)
if [[ -n "$HDMI" && "$MIRROR" != "0" ]]; then
  sleep 0.2
  if xrandr --output "$HDMI" --auto --scale-from "$MODE" --same-as "$SPI" 2>/dev/null; then
    log "HDMI mirror scale-from $MODE"
  elif xrandr --output "$HDMI" --same-as "$SPI" 2>/dev/null; then
    log "HDMI --same-as $SPI"
  else
    # Leave HDMI off — user still has full Digivice on SPI (not a crop)
    log "HDMI stay off (clone failed) — SPI has full Digivice"
  fi
fi

# Export for Qt (single-geometry hint)
export ESP_HANDSET_PANEL_OUTPUT="$SPI"
export ESP_HANDSET_W="${MODE%x*}"
export ESP_HANDSET_H="${MODE#*x}"
echo "$SPI" >/tmp/digivice-panel-output 2>/dev/null || true

log "done  ESP_HANDSET=${ESP_HANDSET_W}x${ESP_HANDSET_H} panel=$SPI"
