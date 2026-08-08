#!/usr/bin/env bash
# Digivice display model (correct direction):
#
#   SPI 2"  = PRIMARY  (true 240×320 / 320×240 phone canvas)
#   HDMI    = MIRROR   (scaled clone of SPI so you can watch on a monitor)
#
# Do NOT put Digivice fullscreen on HDMI first — that crops to trash on SPI.
# Digivice Qt must target the SPI panel; HDMI only echoes that.
#
set +e
set -u

log() { echo "[digivice-layout] $*" >&2; }

MIRROR="${ESP_HANDSET_MIRROR:-1}"
ROT="0"
[[ -f /etc/esp-handset/panel-rotation ]] && \
  ROT="$(tr -d '[:space:]' </etc/esp-handset/panel-rotation 2>/dev/null || echo 0)"
MODE="240x320"
case "$ROT" in 90|270) MODE="320x240" ;; esac

if [[ -z "${DISPLAY:-}" ]]; then
  export DISPLAY=:0
fi

if ! command -v xrandr >/dev/null 2>&1; then
  log "need xrandr (X11).: sudo raspi-config → Advanced → Wayland → X11"
  exit 0
fi
if ! xrandr --query >/dev/null 2>&1; then
  log "xrandr cannot talk to X (DISPLAY=$DISPLAY)"
  exit 0
fi

mapfile -t OUTS < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
log "connected: ${OUTS[*]:-none}"

SPI=""
HDMI=""
for o in "${OUTS[@]:-}"; do
  case "$o" in
    *SPI*|*DPI*|*DSI*|*PANEL*) SPI="$o" ;;
    HDMI*|hdmi*) HDMI="$o" ;;
  esac
done

# Smallest non-HDMI under ~500k px as panel
if [[ -z "$SPI" ]]; then
  best=999999999
  for o in "${OUTS[@]:-}"; do
    case "$o" in HDMI*|hdmi*) continue ;; esac
    area=$(xrandr --query 2>/dev/null | awk -v n="$o" '
      $0 ~ ("^" n " connected") {
        for (i=1;i<=NF;i++) if ($i ~ /^[0-9]+x[0-9]+/) {
          split($i,a,"x"); print (a[1]+0)*(a[2]+0); exit
        }
      }')
    area="${area:-0}"
    if [[ "$area" -gt 1000 && "$area" -lt 400000 && "$area" -lt "$best" ]]; then
      best=$area; SPI=$o
    fi
  done
fi

if [[ -z "$SPI" ]]; then
  log "SPI panel not found — cannot mirror. Digivice may only show if SPI is active."
  log "Check: xrandr | grep connected"
  exit 0
fi
if [[ -n "$HDMI" && "$SPI" == "$HDMI" ]]; then
  log "panel==hdmi, abort"
  exit 0
fi

log "PRIMARY(SPI)=$SPI  MIRROR(HDMI)=${HDMI:-none}  mode=$MODE"

# 1) SPI is the only layout source
for try in "$MODE" 240x320 320x240; do
  if xrandr --output "$SPI" --mode "$try" --primary --pos 0x0 2>/dev/null; then
    MODE=$try
    log "SPI mode $MODE primary @ 0,0"
    break
  fi
done
xrandr --output "$SPI" --primary --pos 0x0 2>/dev/null || \
  xrandr --output "$SPI" --auto --primary --pos 0x0 2>/dev/null

# 2) HDMI is a scaled copy of SPI (same content, zoomed), not a second desktop
if [[ -n "$HDMI" && "$MIRROR" != "0" ]]; then
  # Detach HDMI from any extended layout first
  xrandr --output "$HDMI" --off 2>/dev/null
  sleep 0.15
  if xrandr --output "$HDMI" --auto --scale-from "$MODE" --same-as "$SPI" 2>/dev/null; then
    log "HDMI = scaled mirror of SPI ($MODE → HDMI)"
  elif xrandr --output "$HDMI" --same-as "$SPI" 2>/dev/null; then
    log "HDMI = --same-as SPI (may look blocky)"
  else
    # Re-enable HDMI without extended desktop mess: same-as was required
    xrandr --output "$HDMI" --auto --same-as "$SPI" 2>/dev/null \
      || xrandr --output "$HDMI" --auto --right-of "$SPI" 2>/dev/null
    log "WARN: scale-from failed — try X11 if HDMI does not match SPI"
  fi
elif [[ -n "$HDMI" ]]; then
  xrandr --output "$HDMI" --off 2>/dev/null
  log "MIRROR=0 — HDMI off; Digivice lives on SPI only"
fi

echo "$SPI" >/tmp/digivice-panel-output 2>/dev/null
export ESP_HANDSET_PANEL_OUTPUT="$SPI"
export ESP_HANDSET_W="${MODE%x*}"
export ESP_HANDSET_H="${MODE#*x}"
# Soft hint for Qt (software still prefers panel by name/size)
export ESP_HANDSET_TARGET=panel
log "done: Digivice canvas ${ESP_HANDSET_W}x${ESP_HANDSET_H} on $SPI; HDMI mirrors it"
exit 0
