#!/usr/bin/env bash
# Digivice layout: SPI/Unknown panel ON as primary 240×320.
# HDMI optional clone (scale-from same-as). Never leave panel blank.
#
set +e
set -u

LOG="${HOME}/.esp-handset/handset.log"
mkdir -p "${HOME}/.esp-handset" 2>/dev/null
log() { echo "[digivice-layout] $*" | tee -a "$LOG" >&2; }

MIRROR="${ESP_HANDSET_MIRROR:-1}"
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
    if [[ -w "$d/bl_power" ]]; then
      echo 0 >"$d/bl_power" 2>/dev/null || true
    fi
    if [[ -w "$d/brightness" && -r "$d/max_brightness" ]]; then
      cat "$d/max_brightness" >"$d/brightness" 2>/dev/null \
        || echo 255 >"$d/brightness" 2>/dev/null || true
    fi
    log "backlight: $d on"
  done
  if [[ -d /sys/class/leds ]]; then
    for d in /sys/class/leds/*backlight* /sys/class/leds/*bl*; do
      [[ -e "$d/brightness" ]] || continue
      echo 1 >"$d/brightness" 2>/dev/null || echo 255 >"$d/brightness" 2>/dev/null || true
    done
  fi
}

if ! command -v xrandr >/dev/null 2>&1 || ! xrandr --query >/dev/null 2>&1; then
  log "xrandr/X not available DISPLAY=$DISPLAY (Wayland?): try X11 session"
  unblank_backlight
  exit 0
fi

mapfile -t OUTS < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
log "connected: ${OUTS[*]:-none}"

SPI=""
HDMI=""
# Unknown19-1 is normal for mipi-dbi-spi
for o in "${OUTS[@]:-}"; do
  case "$o" in
    HDMI*|hdmi*|DP-*|DisplayPort*) HDMI="${HDMI:-$o}" ;;
    *SPI*|*DPI*|*DSI*|*PANEL*|[Uu]nknown*) SPI="$o" ;;
  esac
done

if [[ -z "$SPI" ]] || [[ "${#OUTS[@]}" -gt 1 ]]; then
  best=999999999
  pick=""
  for o in "${OUTS[@]:-}"; do
    case "$o" in HDMI*|hdmi*|DP-*) continue ;; esac
    area=$(xrandr --query 2>/dev/null | awk -v n="$o" '
      $0 ~ ("^" n " connected") { p=1; next }
      p && $1 ~ /^[0-9]+x[0-9]+/ { split($1,a,"x"); print (a[1]+0)*(a[2]+0); exit }
      p && /^[^ ]/ { exit }
    ')
    area="${area:-0}"
    if [[ "$area" -eq 76800 ]]; then
      pick=$o; best=$area; break
    fi
    if [[ "$area" -gt 1000 && "$area" -lt 500000 && "$area" -lt "$best" ]]; then
      best=$area; pick=$o
    fi
  done
  [[ -n "$pick" ]] && SPI="$pick"
fi

if [[ -z "$SPI" ]]; then
  log "ERROR no panel output (SPI/Unknown/small) — check mipi overlay + wiring"
  xrandr --query 2>&1 | tee -a "$LOG" >&2
  unblank_backlight
  exit 0
fi

log "panel=$SPI HDMI=${HDMI:-none} MODE=$MODE (Unknown* = normal SPI name)"

spi_on() {
  local try ok=0
  for try in "$MODE" 240x320 320x240; do
    if xrandr --output "$SPI" --mode "$try" --pos 0x0 --rotate normal 2>/dev/null; then
      MODE=$try; W="${MODE%x*}"; H="${MODE#*x}"; ok=1
      log "panel mode $MODE"
      break
    fi
  done
  if [[ "$ok" -eq 0 ]]; then
    xrandr --output "$SPI" --auto --pos 0x0 --rotate normal 2>/dev/null
    log "panel --auto"
  fi
  xrandr --output "$SPI" --primary 2>/dev/null
  xrandr --output "$SPI" --on 2>/dev/null || true
}

# Panel first — always
spi_on
unblank_backlight

# HDMI: try hardware clone of panel (same picture both places)
if [[ -n "$HDMI" && "$HDMI" != "$SPI" && "$MIRROR" != "0" ]]; then
  if xrandr --output "$HDMI" --auto --scale-from "$MODE" --same-as "$SPI" 2>/dev/null; then
    log "HDMI scale-from $MODE same-as panel"
  elif xrandr --output "$HDMI" --same-as "$SPI" 2>/dev/null; then
    log "HDMI same-as panel"
  else
    # Keep panel primary; HDMI extended (Digivice still owns SPI geometry)
    xrandr --output "$HDMI" --auto --right-of "$SPI" 2>/dev/null \
      || xrandr --output "$HDMI" --auto 2>/dev/null
    log "HDMI extended (clone failed); panel remains primary"
  fi
elif [[ -n "$HDMI" && "$MIRROR" == "0" ]]; then
  # Explicit SPI-only: leave HDMI on but do not make it primary
  xrandr --output "$HDMI" --auto --right-of "$SPI" 2>/dev/null || true
  log "MIRROR=0: HDMI extended, panel primary"
fi

# Re-assert panel primary (HDMI --auto can steal)
spi_on
unblank_backlight

active=$(xrandr --query 2>/dev/null | awk -v n="$SPI" '
  $0 ~ ("^" n " connected") {
    if (match($0, /[0-9]+x[0-9]+\+[0-9]+\+[0-9]+/))
      print substr($0, RSTART, RLENGTH)
  }')
if [[ -z "$active" ]]; then
  log "WARN: panel has no active WxH+X+Y — still dark; full xrandr:"
  xrandr --query 2>&1 | tee -a "$LOG" >&2
else
  log "panel ACTIVE $active (primary)"
fi

echo "$SPI" >/tmp/digivice-panel-output 2>/dev/null
export ESP_HANDSET_PANEL_OUTPUT="$SPI"
export ESP_HANDSET_TARGET=panel
export ESP_HANDSET_W="$W" ESP_HANDSET_H="$H"

log "final:"
xrandr --query 2>/dev/null | grep -E 'Screen | connected' | tee -a "$LOG" >&2
log "Digivice will fullscreen on $SPI — not multi-host grab"
exit 0
