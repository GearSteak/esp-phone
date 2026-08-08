#!/usr/bin/env bash
# SAFE Digivice layout — HDMI stays on; SPI enabled with a real mode.
#
# Digivice app pin-bounds its window onto SPI geometry (not HDMI fullscreen).
# Never use --scale-from / --same-as (can blank HDMI).
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
    log "backlight $d"
  done
  # gpio-backlight often used by mipi-dbi
  for d in /sys/class/leds/*backlight* /sys/class/leds/*bl*; do
    [[ -e "$d/brightness" ]] || continue
    echo 1 >"$d/brightness" 2>/dev/null || echo 255 >"$d/brightness" 2>/dev/null || true
  done
}

if ! command -v xrandr >/dev/null 2>&1 || ! xrandr --query >/dev/null 2>&1; then
  log "no xrandr — backlight only"
  unblank_backlight
  exit 0
fi

mapfile -t OUTS < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
log "connected: ${OUTS[*]:-none}"

HDMI=""; SPI=""
for o in "${OUTS[@]:-}"; do
  case "$o" in
    HDMI*|hdmi*|DP-*|DisplayPort*) HDMI="${HDMI:-$o}" ;;
    *SPI*|*DPI*|*DSI*|*PANEL*|[Uu]nknown*) SPI="${SPI:-$o}" ;;
  esac
done

if [[ -z "$SPI" ]]; then
  best=999999999
  for o in "${OUTS[@]:-}"; do
    case "$o" in HDMI*|hdmi*|DP-*) continue ;; esac
    area=$(xrandr --query 2>/dev/null | awk -v n="$o" '
      $0 ~ ("^" n " connected") {p=1;next}
      p && $1 ~ /^[0-9]+x[0-9]+/ {split($1,a,"x"); print (a[1]+0)*(a[2]+0); exit}
      p && /^[^ ]/ {exit}')
    area="${area:-0}"
    if [[ "$area" -eq 76800 ]]; then pick=$o; best=$area; break; fi
    if [[ "$area" -gt 1000 && "$area" -lt 500000 && "$area" -lt "$best" ]]; then
      best=$area; pick=$o
    fi
  done
  [[ -n "${pick:-}" ]] && SPI="$pick"
fi

xrandr --auto 2>/dev/null
unblank_backlight

# --- SPI first at 0,0 with phone mode (content plane Digivice will bind to) ---
if [[ -n "$SPI" ]]; then
  ok=0
  for try in "$MODE" 240x320 320x240; do
    # Force preferred + enable; pos 0,0 so Digivice geometry is simple
    if xrandr --output "$SPI" --mode "$try" --pos 0x0 --rotate normal --on 2>/dev/null; then
      MODE=$try; ok=1
      log "SPI $SPI mode $MODE @0+0"
      break
    fi
  done
  if [[ "$ok" -eq 0 ]]; then
    xrandr --output "$SPI" --auto --pos 0x0 --on 2>/dev/null
    log "SPI $SPI --auto @0+0 (preferred modes failed for $MODE)"
    # List available modes for debugging
    xrandr --query 2>/dev/null | awk -v n="$SPI" '
      $0 ~ ("^" n " ") {p=1; print; next}
      p && /^[[:space:]]+[0-9]+x/ {print; next}
      p && /^[^ ]/ {exit}' | tee -a "$LOG" >&2
  fi
  echo "$SPI" >/tmp/digivice-panel-output
  export ESP_HANDSET_PANEL_OUTPUT="$SPI"
else
  log "ERROR: SPI/Unknown not in connected list — wiring/overlay?"
  log "  dmesg | grep -iE 'mipi|panel|spi'"
  xrandr --query 2>&1 | tee -a "$LOG" >&2
fi

# --- HDMI next to SPI (primary for desktop tools) ---
if [[ -n "$HDMI" ]]; then
  # Place HDMI to the RIGHT of 240-wide panel so desktop tools start on big screen
  # but SPI plane exists at 0,0 for Digivice bind
  SPIM=$(xrandr --query 2>/dev/null | awk -v n="${SPI:-}" '
    $0 ~ ("^" n " connected") {
      if (match($0, /([0-9]+)x([0-9]+)\+([0-9]+)\+([0-9]+)/, a))
        { print a[1]; exit }
    }')
  SPIM="${SPIM:-240}"
  xrandr --output "$HDMI" --auto --pos "${SPIM}x0" --on 2>/dev/null \
    || xrandr --output "$HDMI" --auto --right-of "${SPI:-$HDMI}" --on 2>/dev/null \
    || xrandr --output "$HDMI" --auto --on 2>/dev/null
  xrandr --output "$HDMI" --primary 2>/dev/null
  log "HDMI $HDMI on (primary), pos right of SPI width=${SPIM}"
fi

# Re-enable SPI (HDMI --primary must not disable it)
if [[ -n "$SPI" ]]; then
  xrandr --output "$SPI" --on 2>/dev/null || true
  # ensure still has active geometry
  active=$(xrandr --query 2>/dev/null | awk -v n="$SPI" '
    $0 ~ ("^" n " connected") {
      if (match($0, /[0-9]+x[0-9]+\+[0-9]+\+[0-9]+/))
        print substr($0, RSTART, RLENGTH)
    }')
  if [[ -z "$active" ]]; then
    log "WARN: SPI has no active WxH+X+Y after layout — panel CRTC dark"
    xrandr --output "$SPI" --auto --pos 0x0 --on 2>/dev/null
  else
    log "SPI ACTIVE $active  ← Digivice will pin here"
  fi
fi

unblank_backlight
W="${MODE%x*}"; H="${MODE#*x}"
export ESP_HANDSET_W="$W" ESP_HANDSET_H="$H"
log "final:"
xrandr --query 2>/dev/null | grep -E 'Screen | connected' | tee -a "$LOG" >&2
exit 0
