#!/usr/bin/env bash
# SAFE layout: keep HDMI, force Unknown19-1 / SPI into an ACTIVE mode.
#
# 0mm x 0mm on Unknown* is NORMAL for mipi-dbi (no EDID mm size).
# What matters: active "240x320+X+Y" after this script — not the mm fields.
#
# Never --scale-from / --same-as (can blank HDMI).
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
  for d in /sys/class/leds/*backlight* /sys/class/leds/*bl*; do
    [[ -e "$d/brightness" ]] || continue
    echo 1 >"$d/brightness" 2>/dev/null || echo 255 >"$d/brightness" 2>/dev/null || true
  done
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
      gsub(/^[[:space:]]+/, "", $1)
      print $1
      next
    }
    p && /^[^[:space:]]/ { exit }
  '
}

# Add a synthetic mode if the panel has none (connected 0mm x 0mm, no listed modes)
add_synth_mode() {
  local SPI="$1" name="digi240x320"
  # Tiny modeline (~60Hz-ish) for 240x320 SPI panels
  # Prefer cvt when available
  if command -v cvt >/dev/null 2>&1; then
    # cvt may refuse tiny; try anyway then fall through
    local line
    line=$(cvt "$W" "$H" 50 2>/dev/null | awk '/Modeline/{ $1=""; $2=""; print }' | sed 's/^ *//')
    if [[ -n "$line" ]]; then
      # shellcheck disable=SC2086
      eval "xrandr --newmode $line" 2>/dev/null
      name=$(echo "$line" | awk '{print $1}' | tr -d '"')
      xrandr --addmode "$SPI" "$name" 2>/dev/null && {
        log "added cvt mode $name"
        echo "$name"
        return 0
      }
    fi
  fi
  # Fixed modeline for 240x320
  xrandr --newmode "digi240x320"  5.00  240 256 280 320  320 323 327 335 -hsync +vsync 2>/dev/null || true
  xrandr --addmode "$SPI" "digi240x320" 2>/dev/null || true
  if xrandr --query 2>/dev/null | grep -q digi240x320; then
    log "added synthetic digi240x320"
    echo "digi240x320"
    return 0
  fi
  # Landscape variant
  xrandr --newmode "digi320x240"  5.00  320 336 360 400  240 243 247 255 -hsync +vsync 2>/dev/null || true
  xrandr --addmode "$SPI" "digi320x240" 2>/dev/null || true
  if xrandr --query 2>/dev/null | grep -q digi320x240; then
    echo "digi320x240"
    return 0
  fi
  return 1
}

force_spi_on() {
  local SPI="$1"
  local try m modes ok=0
  log "forcing active mode on $SPI (0mmx0mm is OK if we get WxH+X+Y)"

  # Preferred modes
  for try in "$MODE" 240x320 320x240; do
    if xrandr --output "$SPI" --mode "$try" --pos 0x0 --rotate normal --on 2>/dev/null; then
      MODE=$try
      log "SPI mode $MODE OK"
      ok=1
      break
    fi
  done

  # Any mode the driver already advertises
  if [[ "$ok" -eq 0 ]]; then
    mapfile -t modes < <(list_modes_for "$SPI")
    log "SPI advertised modes: ${modes[*]:-(none)}"
    for m in "${modes[@]:-}"; do
      if xrandr --output "$SPI" --mode "$m" --pos 0x0 --on 2>/dev/null; then
        MODE=$m
        log "SPI mode (driver) $MODE OK"
        ok=1
        break
      fi
    done
  fi

  # --auto
  if [[ "$ok" -eq 0 ]]; then
    xrandr --output "$SPI" --auto --pos 0x0 --on 2>/dev/null && {
      log "SPI --auto"
      ok=1
    }
  fi

  # Synthesize / addmode
  if [[ -z "$(active_geo "$SPI")" ]]; then
    m=$(add_synth_mode "$SPI" || true)
    if [[ -n "${m:-}" ]]; then
      if xrandr --output "$SPI" --mode "$m" --pos 0x0 --on 2>/dev/null; then
        MODE=$m
        log "SPI synthetic mode $MODE OK"
        ok=1
      fi
    fi
  fi

  xrandr --output "$SPI" --on 2>/dev/null || true

  local geo
  geo=$(active_geo "$SPI")
  if [[ -n "$geo" ]]; then
    log "SPI ACTIVE $geo  (0mmx0mm physical size is fine)"
    return 0
  fi
  log "FAIL: $SPI still has no active WxH+X+Y — CRTC not scanning"
  log "  Full block for $SPI:"
  xrandr --query 2>/dev/null | awk -v n="$SPI" '
    $0 ~ ("^" n " ") {p=1}
    p {print}
    p && /^[^[:space:]]/ && $0 !~ ("^" n " ") {exit}
  ' | head -n 20 | tee -a "$LOG" >&2
  log "  Try: dmesg | grep -iE 'mipi|panel|st7789|spi0'"
  return 1
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
  for o in "${OUTS[@]:-}"; do
    case "$o" in HDMI*|hdmi*|DP-*) continue ;; esac
    SPI="$o"; break
  done
fi

unblank_backlight

if [[ -n "$SPI" ]]; then
  force_spi_on "$SPI" || true
  echo "$SPI" >/tmp/digivice-panel-output
  export ESP_HANDSET_PANEL_OUTPUT="$SPI"
else
  log "ERROR: no SPI/Unknown connector at all"
fi

# HDMI on, primary, NEVER disabled
if [[ -n "$HDMI" ]]; then
  xrandr --output "$HDMI" --auto --on 2>/dev/null
  # Prefer extended: SPI at 0,0 if active, else just leave HDMI
  geo=$(active_geo "${SPI:-}")
  if [[ -n "$geo" && -n "$SPI" ]]; then
    xrandr --output "$HDMI" --right-of "$SPI" 2>/dev/null \
      || xrandr --output "$HDMI" --auto --on 2>/dev/null
  fi
  xrandr --output "$HDMI" --primary 2>/dev/null
  log "HDMI primary $HDMI (kept on)"
fi

# SPI still on
if [[ -n "$SPI" ]]; then
  xrandr --output "$SPI" --on 2>/dev/null || true
  geo=$(active_geo "$SPI")
  log "SPI final: ${geo:-STILL NO MODE (dark)}  mm=0x0 is normal for mipi-dbi"
fi

# Final HDMI safety
if [[ -n "$HDMI" ]]; then
  xrandr --output "$HDMI" --auto --on --primary 2>/dev/null
fi

unblank_backlight
export ESP_HANDSET_W="$W" ESP_HANDSET_H="$H"
log "final (look for Unknown … 240x320+0+0 — NOT just 'connected 0mm x 0mm'):"
xrandr --query 2>/dev/null | grep -E 'Screen | connected' | tee -a "$LOG" >&2
exit 0
