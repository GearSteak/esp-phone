#!/usr/bin/env bash
# Digivice multi-display layout (HDMI-safe default OR SPI-only proof).
#
#   digivice-layout                 # dual: SPI on if possible, HDMI primary, never scale-from
#   ESP_HANDSET_SPI_ONLY=1 digivice-layout
#                                   # SPI = primary 240x320, HDMI off (prove panel scanout)
#   digivice-layout --spi-only      # same
#   digivice-layout --hdmi-restore  # turn HDMI back on (after spi-only)
#
# Root dual-head issue: if Unknown is only "connected 0mm" with no WxH+X+Y,
# the panel has no CRTC — Qt can't paint it. SPI-only forces CRTC assignment.
#
set +e
set -u

LOG="${HOME}/.esp-handset/handset.log"
mkdir -p "${HOME}/.esp-handset" 2>/dev/null
log() { echo "[digivice-layout] $*" | tee -a "$LOG" >&2; }

SPI_ONLY=0
HDMI_RESTORE=0
for a in "$@"; do
  case "$a" in
    --spi-only) SPI_ONLY=1 ;;
    --hdmi-restore) HDMI_RESTORE=1 ;;
  esac
done
[[ "${ESP_HANDSET_SPI_ONLY:-0}" == "1" ]] && SPI_ONLY=1

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
  for d in /sys/class/leds/*backlight* /sys/class/leds/*bl*; do
    [[ -e "$d/brightness" ]] || continue
    echo 1 >"$d/brightness" 2>/dev/null || echo 255 >"$d/brightness" 2>/dev/null || true
  done
  # Direct GPIO 18 if no backlight class (Waveshare BL)
  if [[ -w /sys/class/gpio/gpio18/value ]]; then
    echo 1 >/sys/class/gpio/gpio18/value 2>/dev/null || true
  fi
}

active_geo() {
  local n="$1"
  xrandr --query 2>/dev/null | awk -v n="$n" '
    $0 ~ ("^" n " connected") {
      if (match($0, /[0-9]+x[0-9]+\+[0-9]+\+[0-9]+/))
        print substr($0, RSTART, RLENGTH)
    }'
}

list_modes_for() {
  local n="$1"
  xrandr --query 2>/dev/null | awk -v n="$n" '
    $0 ~ ("^" n " ") {p=1; next}
    p && /^[[:space:]]+[0-9]+x[0-9]+/ {
      gsub(/^[[:space:]]+/, "", $1); print $1; next
    }
    p && /^[^[:space:]]/ { exit }
  '
}

find_outputs() {
  HDMI=""; SPI=""
  mapfile -t OUTS < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
  for o in "${OUTS[@]:-}"; do
    case "$o" in
      HDMI*|hdmi*|DP-*) HDMI="${HDMI:-$o}" ;;
      *SPI*|*DPI*|*DSI*|*PANEL*|[Uu]nknown*) SPI="${SPI:-$o}" ;;
    esac
  done
  if [[ -z "$SPI" ]]; then
    for o in "${OUTS[@]:-}"; do
      case "$o" in HDMI*|hdmi*|DP-*) continue ;; esac
      SPI="$o"; break
    done
  fi
  log "connected: ${OUTS[*]:-none} → SPI=${SPI:-none} HDMI=${HDMI:-none}"
}

force_spi_mode() {
  local SPI="$1" try m ok=0
  for try in "$MODE" 240x320 320x240; do
    if xrandr --output "$SPI" --mode "$try" --pos 0x0 --rotate normal --primary --on 2>/dev/null; then
      MODE=$try; ok=1; log "SPI $SPI mode $MODE primary"; break
    fi
  done
  if [[ "$ok" -eq 0 ]]; then
    mapfile -t modes < <(list_modes_for "$SPI")
    log "SPI modes: ${modes[*]:-none}"
    for m in "${modes[@]:-}"; do
      if xrandr --output "$SPI" --mode "$m" --pos 0x0 --primary --on 2>/dev/null; then
        MODE=$m; ok=1; log "SPI driver mode $m"; break
      fi
    done
  fi
  [[ "$ok" -eq 0 ]] && xrandr --output "$SPI" --auto --pos 0x0 --primary --on 2>/dev/null && log "SPI --auto"

  # Synthetic last resort
  if [[ -z "$(active_geo "$SPI")" ]]; then
    xrandr --newmode "digi240x320" 5.00 240 256 280 320 320 323 327 335 -hsync +vsync 2>/dev/null || true
    xrandr --addmode "$SPI" "digi240x320" 2>/dev/null || true
    xrandr --output "$SPI" --mode digi240x320 --pos 0x0 --primary --on 2>/dev/null && log "SPI digi240x320"
  fi
}

hdmi_on_primary() {
  local HDMI="$1"
  [[ -z "$HDMI" ]] && return
  xrandr --output "$HDMI" --auto --on 2>/dev/null
  xrandr --output "$HDMI" --primary 2>/dev/null
  log "HDMI on primary: $HDMI"
}

hdmi_off() {
  local HDMI="$1"
  [[ -z "$HDMI" ]] && return
  xrandr --output "$HDMI" --off 2>/dev/null
  log "HDMI OFF (SPI-only proof — restore with digivice-layout --hdmi-restore)"
}

if ! command -v xrandr >/dev/null 2>&1 || ! xrandr --query >/dev/null 2>&1; then
  log "no xrandr/X — set DISPLAY=:0 and use X11 (not Wayland-only)"
  unblank_backlight
  exit 0
fi

find_outputs
unblank_backlight

# --- HDMI restore only ---
if [[ "$HDMI_RESTORE" -eq 1 ]]; then
  find_outputs
  hdmi_on_primary "$HDMI"
  if [[ -n "$SPI" ]]; then
    xrandr --output "$SPI" --auto --right-of "$HDMI" --on 2>/dev/null || true
  fi
  xrandr --query 2>/dev/null | grep connected | tee -a "$LOG" >&2
  exit 0
fi

# --- SPI-only proof (HDMI off so CRTC goes to SPI) ---
if [[ "$SPI_ONLY" -eq 1 ]]; then
  log "=== SPI-ONLY mode (HDMI off) — proves whether panel can scan out ==="
  if [[ -z "$SPI" ]]; then
    log "FATAL: no SPI/Unknown connector — firmware/overlay not probed"
    log "  sudo digivice-spi-doctor --fix && sudo reboot"
    exit 1
  fi
  # Turn HDMI off FIRST so sole CRTC attaches to SPI (dual-head often starves SPI)
  hdmi_off "$HDMI"
  sleep 0.3
  force_spi_mode "$SPI"
  echo "$SPI" >/tmp/digivice-panel-output
  export ESP_HANDSET_PANEL_OUTPUT="$SPI"
  unblank_backlight
  geo=$(active_geo "$SPI")
  if [[ -n "$geo" ]]; then
    log "SPI ACTIVE $geo — Digivice should fill this; HDMI is off"
  else
    log "SPI still no active mode AFTER HDMI-off — kernel/firmware problem, not dual-head"
    log "  Restoring HDMI for desk use..."
    hdmi_on_primary "$HDMI"
  fi
  xrandr --query 2>/dev/null | grep -E 'Screen | connected' | tee -a "$LOG" >&2
  echo "$SPI_ONLY" >/tmp/digivice-spi-only 2>/dev/null
  exit 0
fi

# --- Dual head (default): never blank HDMI; try SPI with real mode ---
log "=== dual head (HDMI primary, SPI secondary if possible) ==="
if [[ -n "$SPI" ]]; then
  force_spi_mode "$SPI" || true
  echo "$SPI" >/tmp/digivice-panel-output
fi
if [[ -n "$HDMI" ]]; then
  xrandr --output "$HDMI" --auto --on 2>/dev/null
  if [[ -n "$SPI" && -n "$(active_geo "$SPI")" ]]; then
    xrandr --output "$HDMI" --right-of "$SPI" 2>/dev/null || true
  fi
  xrandr --output "$HDMI" --primary 2>/dev/null
  log "HDMI primary kept ON"
fi
# Re-assert SPI after HDMI primary (some drivers drop it)
if [[ -n "$SPI" ]]; then
  xrandr --output "$SPI" --on 2>/dev/null || true
  geo=$(active_geo "$SPI")
  log "SPI final: ${geo:-NO MODE (dark — try: ESP_HANDSET_SPI_ONLY=1 digivice-layout)}"
fi
unblank_backlight
rm -f /tmp/digivice-spi-only 2>/dev/null
xrandr --query 2>/dev/null | grep -E 'Screen | connected' | tee -a "$LOG" >&2
exit 0
