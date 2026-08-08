#!/usr/bin/env bash
# Turn SPI panel ON for Digivice (do not leave it blank).
# Digivice app paints natively on SPI; HDMI gets a software scaled copy.
# Prefer: keep HDMI on too so Qt sees both screens.
#
set +e
set -u
LOG="${HOME}/.esp-handset/handset.log"
mkdir -p "${HOME}/.esp-handset" 2>/dev/null
log() { echo "[digivice-layout] $*" | tee -a "$LOG" >&2; }

export DISPLAY="${DISPLAY:-:0}"

# backlight
for d in /sys/class/backlight/*; do
  [[ -d "$d" ]] || continue
  echo 0 >"$d/bl_power" 2>/dev/null || true
  [[ -r "$d/max_brightness" ]] && cat "$d/max_brightness" >"$d/brightness" 2>/dev/null || true
  log "backlight $d"
done

if ! command -v xrandr >/dev/null 2>&1 || ! xrandr --query >/dev/null 2>&1; then
  log "no xrandr/X — SPI may only work if already active"
  exit 0
fi

mapfile -t OUTS < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
log "connected: ${OUTS[*]:-none}"

SPI=""; HDMI=""
for o in "${OUTS[@]:-}"; do
  case "$o" in
    *SPI*|*DPI*|*DSI*|*PANEL*) SPI="$o" ;;
    HDMI*|hdmi*) HDMI="$o" ;;
  esac
done

if [[ -z "$SPI" ]]; then
  best=999999999
  for o in "${OUTS[@]:-}"; do
    case "$o" in HDMI*|hdmi*) continue ;; esac
    area=$(xrandr --query 2>/dev/null | awk -v n="$o" '
      $0 ~ ("^" n " connected") {p=1;next}
      p && $1 ~ /^[0-9]+x[0-9]+/ {split($1,a,"x"); print (a[1]+0)*(a[2]+0); exit}
      p && /^[^ ]/ {exit}')
    area="${area:-0}"
    if [[ "$area" -gt 1000 && "$area" -lt 500000 && "$area" -lt "$best" ]]; then
      best=$area; SPI=$o
    fi
  done
fi

if [[ -z "$SPI" ]]; then
  log "ERROR: no SPI/small output — Digivice cannot live on panel; Qt will only use HDMI"
  xrandr --query 2>&1 | tee -a "$LOG" >&2
  exit 0
fi

ROT=0
[[ -f /etc/esp-handset/panel-rotation ]] && \
  ROT="$(tr -d '[:space:]' </etc/esp-handset/panel-rotation 2>/dev/null || echo 0)"
MODE=240x320
case "$ROT" in 90|270) MODE=320x240 ;; esac

log "enabling SPI=$SPI MODE=$MODE (HDMI stays ${HDMI:-none})"

# CRITICAL: turn SPI on; do NOT turn it off or leave without a mode
ok=0
for try in "$MODE" 240x320 320x240; do
  if xrandr --output "$SPI" --mode "$try" --pos 0x0 --rotate normal 2>/dev/null; then
    MODE=$try; ok=1; log "SPI mode $MODE"; break
  fi
done
[[ "$ok" -eq 0 ]] && xrandr --output "$SPI" --auto --pos 0x0 2>/dev/null && log "SPI --auto"
xrandr --output "$SPI" --primary 2>/dev/null
xrandr --output "$SPI" --on 2>/dev/null

# Keep HDMI on so software scale host can attach (extended is fine now)
if [[ -n "$HDMI" ]]; then
  xrandr --output "$HDMI" --auto 2>/dev/null
  # Put HDMI to the right of SPI so they are distinct QScreens, not a crop
  xrandr --output "$HDMI" --right-of "$SPI" 2>/dev/null \
    || xrandr --output "$HDMI" --auto 2>/dev/null
  log "HDMI on (extended); Digivice will scale full UI onto it"
fi

# Re-assert SPI (some drivers re-primary HDMI)
xrandr --output "$SPI" --primary 2>/dev/null
xrandr --output "$SPI" --on 2>/dev/null

echo "$SPI" >/tmp/digivice-panel-output 2>/dev/null
export ESP_HANDSET_PANEL_OUTPUT="$SPI"
export ESP_HANDSET_TARGET=panel
W="${MODE%x*}"; H="${MODE#*x}"
export ESP_HANDSET_W="$W" ESP_HANDSET_H="$H"

log "final layout:"
xrandr --query 2>/dev/null | grep -E 'Screen | connected' | tee -a "$LOG" >&2
log "SPI must say: connected … ${MODE} …  Digivice binds here; HDMI gets scaled copy"
exit 0
