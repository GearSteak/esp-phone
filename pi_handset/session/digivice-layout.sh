#!/usr/bin/env bash
# Digivice layout: SPI must end ON as primary with a real mode.
# HDMI is optional scaled mirror. Never leave SPI blank.
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

# --- backlight: unblank GPIO panel if present ---
unblank_backlight() {
  local d
  for d in /sys/class/backlight/*; do
    [[ -d "$d" ]] || continue
    # 0 = full on for many panels; some use max brightness
    if [[ -w "$d/bl_power" ]]; then
      echo 0 >"$d/bl_power" 2>/dev/null || true
    fi
    if [[ -w "$d/brightness" && -r "$d/max_brightness" ]]; then
      cat "$d/max_brightness" >"$d/brightness" 2>/dev/null || echo 255 >"$d/brightness" 2>/dev/null || true
    fi
    log "backlight: $d on"
  done
  # Some Waveshare overlays use gpio-backlight
  if [[ -d /sys/class/leds ]]; then
    for d in /sys/class/leds/*backlight* /sys/class/leds/*bl*; do
      [[ -e "$d/brightness" ]] || continue
      echo 1 >"$d/brightness" 2>/dev/null || echo 255 >"$d/brightness" 2>/dev/null || true
    done
  fi
}

if ! command -v xrandr >/dev/null 2>&1 || ! xrandr --query >/dev/null 2>&1; then
  log "xrandr/X not available DISPLAY=$DISPLAY"
  unblank_backlight
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

if [[ -z "$SPI" ]]; then
  best=999999999
  for o in "${OUTS[@]:-}"; do
    case "$o" in HDMI*|hdmi*) continue ;; esac
    area=$(xrandr --query 2>/dev/null | awk -v n="$o" '
      $0 ~ ("^" n " connected") { p=1; next }
      p && $1 ~ /^[0-9]+x[0-9]+/ { split($1,a,"x"); print (a[1]+0)*(a[2]+0); exit }
      p && /^[^ ]/ { exit }
    ')
    area="${area:-0}"
    if [[ "$area" -gt 1000 && "$area" -lt 500000 && "$area" -lt "$best" ]]; then
      best=$area; SPI=$o
    fi
  done
fi

if [[ -z "$SPI" ]]; then
  log "ERROR no SPI output in xrandr — panel may be dead to X (kernel/wiring)"
  xrandr --query 2>&1 | tee -a "$LOG" >&2
  unblank_backlight
  exit 0
fi

log "SPI=$SPI HDMI=${HDMI:-none} MODE=$MODE"

# --- Bring SPI up FIRST and keep it on (blank SPI = we failed) ---
spi_on() {
  local try ok=0
  for try in "$MODE" 240x320 320x240; do
    if xrandr --output "$SPI" --mode "$try" --pos 0x0 --rotate normal 2>/dev/null; then
      MODE=$try; W="${MODE%x*}"; H="${MODE#*x}"; ok=1
      log "SPI mode $MODE"
      break
    fi
  done
  if [[ "$ok" -eq 0 ]]; then
    xrandr --output "$SPI" --auto --pos 0x0 --rotate normal 2>/dev/null
    log "SPI --auto"
  fi
  xrandr --output "$SPI" --primary 2>/dev/null
  xrandr --output "$SPI" --on 2>/dev/null || true
}

spi_on
unblank_backlight

# Prefer: SPI primary, HDMI clone of SPI (big preview)
if [[ -n "$HDMI" && "$MIRROR" != "0" ]]; then
  # Do NOT leave SPI without CRTC: set clone without long HDMI-off
  if xrandr --output "$HDMI" --auto --scale-from "$MODE" --same-as "$SPI" 2>/dev/null; then
    log "HDMI scale-from $MODE same-as SPI"
  elif xrandr --output "$HDMI" --same-as "$SPI" 2>/dev/null; then
    log "HDMI same-as SPI"
  else
    # Side-by-side last resort — SPI still has CRTC/content
    xrandr --output "$HDMI" --auto --right-of "$SPI" 2>/dev/null \
      || xrandr --output "$HDMI" --auto 2>/dev/null
    log "HDMI extended (clone failed); SPI remains primary"
  fi
  # Re-assert SPI primary after HDMI ops (some drivers steal primary)
  spi_on
  unblank_backlight
elif [[ -n "$HDMI" ]]; then
  # MIRROR=0: keep HDMI for desktop install, SPI still primary for Digivice
  xrandr --output "$HDMI" --auto --right-of "$SPI" 2>/dev/null || true
  spi_on
fi

# Do NOT call xrandr --fb when it risks blanking SPI on Pi DRM — optional only if single output
if [[ -z "$HDMI" || "$MIRROR" == "0" ]]; then
  if xrandr --fb "$MODE" 2>/dev/null; then
    log "fb $MODE"
    spi_on
  fi
fi

echo "$SPI" >/tmp/digivice-panel-output 2>/dev/null
export ESP_HANDSET_PANEL_OUTPUT="$SPI"
export ESP_HANDSET_W="$W"
export ESP_HANDSET_H="$H"
export ESP_HANDSET_TARGET=panel

log "final:"
xrandr --query 2>/dev/null | grep -E "Screen | connected| disconnected" | tee -a "$LOG" >&2
log "SPI must be 'connected primary'. Digivice TARGET=panel → $SPI"
exit 0
