#!/usr/bin/env bash
# Digivice multi-display layout. NEVER leave the user with zero outputs.
#
# - If SPI/DPI panel is found: make it primary; optionally clone to HDMI.
# - If SPI is NOT found: do nothing (keep HDMI). Digivice still launches.
# - Never assign SPI == HDMI. Never kill the only display.
set +e
set -u

log() { echo "[digivice-layout] $*" >&2; }

MIRROR="${ESP_HANDSET_MIRROR:-1}"
ROT="0"
if [[ -f /etc/esp-handset/panel-rotation ]]; then
  ROT="$(tr -d '[:space:]' </etc/esp-handset/panel-rotation 2>/dev/null || echo 0)"
fi
MODE="240x320"
case "$ROT" in
  90|270) MODE="320x240" ;;
esac

if ! command -v xrandr >/dev/null 2>&1; then
  log "xrandr missing — skip"
  exit 0
fi

if [[ -z "${DISPLAY:-}" ]]; then
  # Try common desktop display for autostart
  export DISPLAY="${DISPLAY:-:0}"
fi

if ! xrandr --query >/dev/null 2>&1; then
  log "xrandr cannot query (no X?). skip layout"
  exit 0
fi

mapfile -t OUTS < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
if [[ ${#OUTS[@]} -eq 0 ]]; then
  log "no connected outputs"
  exit 0
fi

SPI=""
HDMI=""
for o in "${OUTS[@]}"; do
  case "$o" in
    *SPI*|*DPI*|*DSI*|*PANEL*|*Writeback*) SPI="$o" ;;
    HDMI*|hdmi*) HDMI="$o" ;;
  esac
done

# Smallest non-HDMI as panel when name unknown (area < 200k ≈ under ~500x400)
if [[ -z "$SPI" ]]; then
  best=999999999
  for o in "${OUTS[@]}"; do
    case "$o" in HDMI*|hdmi*) continue ;; esac
    area=$(xrandr --query 2>/dev/null | awk -v n="$o" '
      index($0, n " connected")==1 {
        for(i=1;i<=NF;i++) if ($i ~ /^[0-9]+x[0-9]+/) {
          split($i,a,"x"); print (a[1]+0)*(a[2]+0); exit
        }
      }
    ')
    area="${area:-0}"
    if [[ "$area" -gt 0 && "$area" -lt 300000 && "$area" -lt "$best" ]]; then
      best=$area
      SPI=$o
    fi
  done
fi

log "outputs=${OUTS[*]}  panel=${SPI:-none}  hdmi=${HDMI:-none}"

# No separate SPI panel → do NOT touch layout (HDMI stays, Digivice can still open)
if [[ -z "$SPI" ]]; then
  log "no SPI/small panel detected — leave displays alone"
  exit 0
fi
if [[ -n "$HDMI" && "$SPI" == "$HDMI" ]]; then
  log "refusing layout (panel==hdmi)"
  exit 0
fi

# Only one output and it's the panel
if [[ ${#OUTS[@]} -eq 1 ]]; then
  xrandr --output "$SPI" --auto --primary --pos 0x0 2>/dev/null
  for try in "$MODE" 240x320 320x240; do
    xrandr --output "$SPI" --mode "$try" --primary 2>/dev/null && break
  done
  log "single output $SPI"
  exit 0
fi

# Multi: set SPI primary (do not blank HDMI unless clone will replace it)
for try in "$MODE" 240x320 320x240; do
  if xrandr --output "$SPI" --mode "$try" --primary --pos 0x0 2>/dev/null; then
    MODE=$try
    log "SPI $SPI mode $MODE primary"
    break
  fi
done
xrandr --output "$SPI" --auto --primary --pos 0x0 2>/dev/null

if [[ -n "$HDMI" && "$MIRROR" != "0" ]]; then
  if xrandr --output "$HDMI" --auto --scale-from "$MODE" --same-as "$SPI" 2>/dev/null; then
    log "HDMI clone scale-from $MODE"
  elif xrandr --output "$HDMI" --same-as "$SPI" 2>/dev/null; then
    log "HDMI --same-as $SPI"
  else
    # Keep HDMI on auto — better a side-by-side than a black monitor
    xrandr --output "$HDMI" --auto --right-of "$SPI" 2>/dev/null \
      || xrandr --output "$HDMI" --auto 2>/dev/null
    log "HDMI kept on (clone failed) — Digivice targets SPI in software"
  fi
elif [[ -n "$HDMI" ]]; then
  xrandr --output "$HDMI" --auto 2>/dev/null
  log "HDMI left auto (MIRROR=0)"
fi

echo "$SPI" >/tmp/digivice-panel-output 2>/dev/null
export ESP_HANDSET_PANEL_OUTPUT="$SPI"
export ESP_HANDSET_W="${MODE%x*}"
export ESP_HANDSET_H="${MODE#*x}"
log "done panel=$SPI ${ESP_HANDSET_W}x${ESP_HANDSET_H}"
exit 0
