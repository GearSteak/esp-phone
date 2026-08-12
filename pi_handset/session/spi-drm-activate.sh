#!/usr/bin/env bash
# After login: enable the ST7789 DRM head (Instructables / Adafruit model).
#
# Bookworm treats SPI as a second display rather than auto-mirroring.
# This script turns the SPI connector on and tries to clone HDMI content.
#
set +e
export DISPLAY="${DISPLAY:-:0}"
LOG="${HOME}/.esp-handset/handset.log"
mkdir -p "${HOME}/.esp-handset"
log() { echo "[spi-drm] $*" | tee -a "$LOG" >&2; }

if [[ -z "${XAUTHORITY:-}" ]]; then
  for a in "${HOME}/.Xauthority" /home/*/.Xauthority; do
    [[ -f $a ]] || continue
    export XAUTHORITY="$(ls $a 2>/dev/null | head -n1)"
    break
  done
fi

# Prefer X11 tools; fall back to wlr-randr for labwc
if ! command -v xrandr >/dev/null 2>&1; then
  log "xrandr missing — install x11-xserver-utils"
fi

# Wait for X/Wayland randr
for _ in $(seq 1 15); do
  if xrandr --query >/dev/null 2>&1; then
    break
  fi
  sleep 0.4
done

if ! xrandr --query >/dev/null 2>&1; then
  # Wayland / labwc path
  if command -v wlr-randr >/dev/null 2>&1; then
    log "using wlr-randr"
    wlr-randr 2>/dev/null | tee -a "$LOG" || true
    # Turn on every output that looks like SPI panel
    while read -r name rest; do
      case "$name" in
        SPI*|Unknown*|DPI*|DSI*)
          wlr-randr --output "$name" --on 2>/dev/null || true
          log "wlr on $name"
          ;;
      esac
    done < <(wlr-randr 2>/dev/null | awk '/^[A-Za-z0-9_-]+ /{print $1}')
  else
    log "no xrandr/wlr-randr — cannot auto-enable SPI panel"
  fi
  exit 0
fi

mapfile -t OUTS < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
log "connected: ${OUTS[*]:-none}"

HDMI=""
SPI=""
for o in "${OUTS[@]:-}"; do
  case "$o" in
    HDMI*|hdmi*) HDMI="${HDMI:-$o}" ;;
    SPI*|Unknown*|DPI*|DSI*|Composite*)
      # Prefer SPI-ish names; Unknown* is often mipi-dbi on Pi
      if [[ -z "$SPI" || "$o" == SPI* ]]; then
        SPI="$o"
      fi
      ;;
  esac
done

# If only one output and it's huge, no SPI
if [[ -z "$SPI" ]]; then
  # Smallest connected head as candidate panel
  best=""; best_a=999999999
  while read -r name w h; do
    [[ -n "$name" && -n "$w" ]] || continue
    a=$((w * h))
    if (( a < best_a && a > 100 )); then
      best_a=$a
      best=$name
    fi
  done < <(xrandr --query 2>/dev/null | awk '
    / connected/{n=$1}
    n && /[0-9]+x[0-9]+/{
      split($1,a,"x");
      if (a[1]+0>0) { print n, a[1], a[2]; n="" }
    }')
  if [[ -n "$best" && "$best_a" -lt 200000 ]]; then
    SPI="$best"
    log "guess SPI panel = $SPI (${best_a}px)"
  fi
fi

if [[ -z "$SPI" ]]; then
  log "no SPI/DRM panel found — is mipi-dbi installed? reboot after digivice-install-instructables"
  xrandr --query 2>/dev/null | tee -a "$LOG" || true
  exit 1
fi

log "enable SPI head: $SPI (HDMI=${HDMI:-none})"
xrandr --output "$SPI" --auto --on 2>/dev/null || true

if [[ -n "$HDMI" ]]; then
  xrandr --output "$HDMI" --auto --primary --on 2>/dev/null || true
  # Prefer clone so desktop content appears on 2" (Instructables intent)
  if xrandr --output "$SPI" --same-as "$HDMI" 2>/dev/null; then
    log "cloned $SPI same-as $HDMI"
  else
    # Different mode: place and scale-from if supported
    xrandr --output "$SPI" --auto --right-of "$HDMI" 2>/dev/null \
      || xrandr --output "$SPI" --auto 2>/dev/null || true
    log "SPI beside HDMI (clone modes failed — layout right-of)"
  fi
else
  xrandr --output "$SPI" --auto --primary --on 2>/dev/null || true
  log "SPI is sole / primary head"
fi

# Keep panel awake
xset s off 2>/dev/null || true
xset -dpms 2>/dev/null || true

log "done"
xrandr --query 2>/dev/null | grep connected | tee -a "$LOG" || true

# HW cursor usually works with DRM clone now — restore system cursor only.
# Do NOT start the yellow overlay (double cursor).
for c in \
  /usr/local/bin/digivice-fix-cursor \
  /opt/esp-handset/session/fix-cursor.sh
do
  if [[ -f "$c" ]]; then
    log "restore system cursor (no yellow overlay)"
    ( sleep 0.5; bash "$c" >>"$LOG" 2>&1 ) &
    break
  fi
done

exit 0
