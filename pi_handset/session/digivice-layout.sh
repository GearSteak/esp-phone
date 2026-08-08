#!/usr/bin/env bash
# SAFE Digivice layout — never blank HDMI.
#
# 1) Bring HDMI up first (primary) so you always have a visible desktop monitor.
# 2) Enable SPI/Unknown panel as a second head (extended).
# 3) NEVER use --scale-from / --same-as (those blacked out HDMI on Pi).
#
set +e
set -u

LOG="${HOME}/.esp-handset/handset.log"
mkdir -p "${HOME}/.esp-handset" 2>/dev/null
log() { echo "[digivice-layout] $*" | tee -a "$LOG" >&2; }

ROT="0"
[[ -f /etc/esp-handset/panel-rotation ]] && \
  ROT="$(tr -d '[:space:]' </etc/esp-handset/panel-rotation 2>/dev/null || echo 0)"
W=240; H=320
case "$ROT" in 90|270) W=320; H=240 ;; esac
MODE="${W}x${H}"
export DISPLAY="${DISPLAY:-:0}"

unblank_backlight() {
  local d
  for d in /sys/class/backlight/*; do
    [[ -d "$d" ]] || continue
    echo 0 >"$d/bl_power" 2>/dev/null || true
    [[ -r "$d/max_brightness" ]] && cat "$d/max_brightness" >"$d/brightness" 2>/dev/null || true
  done
}

if ! command -v xrandr >/dev/null 2>&1 || ! xrandr --query >/dev/null 2>&1; then
  log "no xrandr — unblank backlight only"
  unblank_backlight
  exit 0
fi

# ---- HDMI first (must never stay off) ----
mapfile -t OUTS < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
log "connected: ${OUTS[*]:-none}"

HDMI=""
SPI=""
for o in "${OUTS[@]:-}"; do
  case "$o" in
    HDMI*|hdmi*|DP-*|DisplayPort*) HDMI="${HDMI:-$o}" ;;
    *SPI*|*DPI*|*DSI*|*PANEL*|[Uu]nknown*) SPI="${SPI:-$o}" ;;
  esac
done

# Pick small panel by size if name missed
if [[ -z "$SPI" ]]; then
  best=999999999
  for o in "${OUTS[@]:-}"; do
    case "$o" in HDMI*|hdmi*|DP-*) continue ;; esac
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

# Global auto first (recovers heads after bad layout)
xrandr --auto 2>/dev/null
unblank_backlight

if [[ -n "$HDMI" ]]; then
  xrandr --output "$HDMI" --auto --on 2>/dev/null
  xrandr --output "$HDMI" --primary 2>/dev/null
  log "HDMI primary: $HDMI (SAFE path — you should see picture here)"
else
  log "WARN: no HDMI in xrandr connected list"
fi

if [[ -n "$SPI" && "$SPI" != "$HDMI" ]]; then
  ok=0
  for try in "$MODE" 240x320 320x240; do
    if xrandr --output "$SPI" --mode "$try" --right-of "${HDMI:-$SPI}" --rotate normal 2>/dev/null; then
      MODE=$try; ok=1
      log "panel $SPI mode $MODE right-of HDMI"
      break
    fi
  done
  if [[ "$ok" -eq 0 ]]; then
    xrandr --output "$SPI" --auto --on 2>/dev/null
    if [[ -n "$HDMI" ]]; then
      xrandr --output "$SPI" --right-of "$HDMI" 2>/dev/null || true
    fi
    log "panel $SPI --auto"
  fi
  xrandr --output "$SPI" --on 2>/dev/null || true
  echo "$SPI" >/tmp/digivice-panel-output 2>/dev/null
  export ESP_HANDSET_PANEL_OUTPUT="$SPI"
else
  log "no SPI/Unknown panel found — HDMI-only is fine for recovery"
fi

# Re-assert HDMI primary once more (never leave SPI-only dark world)
if [[ -n "$HDMI" ]]; then
  xrandr --output "$HDMI" --auto --primary --on 2>/dev/null
fi

export ESP_HANDSET_W="$W" ESP_HANDSET_H="$H"
log "final (HDMI must stay on):"
xrandr --query 2>/dev/null | grep -E 'Screen | connected' | tee -a "$LOG" >&2
exit 0
