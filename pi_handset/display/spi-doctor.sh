#!/usr/bin/env bash
# Deep diagnose + repair helpers for Waveshare 2" SPI (mipi-dbi) blank panel.
#
#   digivice-spi-doctor           # report only
#   digivice-spi-doctor --fix     # reinstall firmware+DT (needs reboot)
#   digivice-spi-doctor --modes   # try enable CRTC if panel already probed
#
# Why name changed SPI → Unknown:
#   Old tinydrm/fb stacks used connector name SPI-*. Modern DRM panel-mipi-dbi
#   uses type "Unknown" (e.g. Unknown19-1). Same hardware. 0mm x 0mm is normal.
#
set +e
set -u

LOG="${HOME}/.esp-handset/handset.log"
mkdir -p "${HOME}/.esp-handset"
log() { echo "[spi-doctor] $*" | tee -a "$LOG" >&2; }

export DISPLAY="${DISPLAY:-:0}"
FIX=0
MODES=0
for a in "$@"; do
  case "$a" in
    --fix) FIX=1 ;;
    --modes) MODES=1 ;;
  esac
done

log "=== digivice-spi-doctor ==="
log "Host=$(uname -n) kernel=$(uname -r)"

# --- firmware ---
log "--- firmware ---"
for f in /lib/firmware/waveshare2inch.bin /lib/firmware/panel.bin; do
  if [[ -f "$f" ]]; then
    m=$(head -c 8 "$f" 2>/dev/null | tr -d '\0')
    sz=$(wc -c <"$f" 2>/dev/null)
    if [[ "$m" == "MIPI DBI" ]]; then
      log "OK $f size=$sz magic=MIPI DBI"
    else
      log "BAD $f size=$sz magic='$m' (must be MIPI DBI — probe will fail)"
    fi
  else
    log "MISSING $f"
  fi
done

# --- config.txt ---
log "--- config.txt Digivice block ---"
BOOT=""
for c in /boot/firmware/config.txt /boot/config.txt; do
  [[ -f "$c" ]] && BOOT="$c" && break
done
if [[ -n "$BOOT" ]]; then
  log "file=$BOOT"
  awk '/# --- ESP Digivice display/,/# --- END ESP Digivice display/{print}' "$BOOT" | tee -a "$LOG" >&2
  if grep -qE 'vc4-kms-v3d,nohdmi' "$BOOT"; then
    log "WARN: nohdmi present — HDMI dead risk"
  fi
  if ! grep -qE 'dtoverlay=mipi-dbi-spi' "$BOOT"; then
    log "WARN: no mipi-dbi-spi overlay in config"
  fi
else
  log "ERROR: no config.txt"
fi

# --- kernel probe ---
log "--- dmesg panel-mipi-dbi (last boot) ---"
dmesg 2>/dev/null | grep -iE 'mipi.dbi|panel-mipi|waveshare2inch|spi0\.0' | tail -n 40 | tee -a "$LOG" >&2
if dmesg 2>/dev/null | grep -qi 'Bad magic'; then
  log "FAIL: Bad magic — firmware file is wrong content or wrong path"
fi
if dmesg 2>/dev/null | grep -qi 'Direct firmware load.*failed\|firmware.*not found'; then
  log "FAIL: firmware file not found by kernel"
fi
if dmesg 2>/dev/null | grep -qi 'panel-mipi-dbi.*failed\|probe with driver panel-mipi-dbi.*failed'; then
  log "FAIL: panel probe failed (see lines above)"
fi

# --- DRM sysfs ---
log "--- /sys/class/drm (status + modes) ---"
for d in /sys/class/drm/card*-*; do
  [[ -d "$d" ]] || continue
  name=$(basename "$d")
  [[ "$name" == *"-"* ]] || continue
  st=""; [[ -r "$d/status" ]] && st=$(cat "$d/status")
  en=""; [[ -r "$d/enabled" ]] && en=$(cat "$d/enabled")
  modes=""
  [[ -r "$d/modes" ]] && modes=$(tr '\n' ' ' <"$d/modes")
  log "  $name status=$st enabled=$en modes=[${modes:-none}]"
done

# --- xrandr ---
log "--- xrandr ---"
if command -v xrandr >/dev/null 2>&1 && xrandr --query >/dev/null 2>&1; then
  xrandr --query 2>/dev/null | grep -E 'Screen | connected|disconnected' | tee -a "$LOG" >&2
  PANEL=$(xrandr --query 2>/dev/null | awk '/ connected/ && ($1 ~ /SPI|Unknown|DPI|DSI|PANEL/){print $1; exit}')
  if [[ -n "$PANEL" ]]; then
    log "detected panel output: $PANEL"
    xrandr --query 2>/dev/null | awk -v n="$PANEL" '
      $0 ~ ("^" n " ") {p=1}
      p {print}
      p && /^[^[:space:]]/ && $0 !~ ("^" n " ") {exit}
    ' | head -n 25 | tee -a "$LOG" >&2
  else
    log "No SPI/Unknown in xrandr connected list"
  fi
else
  log "xrandr unavailable (Wayland-only session? try X11: raspi-config)"
fi

# --- backlight ---
log "--- backlight ---"
for d in /sys/class/backlight/*; do
  [[ -d "$d" ]] || continue
  log "  $d bl_power=$(cat "$d/bl_power" 2>/dev/null) brightness=$(cat "$d/brightness" 2>/dev/null)/$(cat "$d/max_brightness" 2>/dev/null)"
done

log "--- analysis ---"
log "• SPI-1 vs Unknown19-1 is KMS naming, NOT a different panel."
log "• 'connected 0mm x 0mm' without '240x320+X+Y' = no CRTC (dark)."
log "• Need dmesg probe OK + firmware magic MIPI DBI + listed mode + backlight."

if [[ "$MODES" -eq 1 ]]; then
  log "--- --modes: enable CRTC (HDMI safety net) ---"
  if command -v digivice-layout >/dev/null 2>&1; then
    bash digivice-layout 2>&1 | tee -a "$LOG"
  elif [[ -f /opt/esp-handset/session/digivice-layout.sh ]]; then
    bash /opt/esp-handset/session/digivice-layout.sh 2>&1 | tee -a "$LOG"
  fi
  for o in $(xrandr --query 2>/dev/null | awk '/ connected/{print $1}'); do
    case "$o" in HDMI*|hdmi*)
      xrandr --output "$o" --auto --primary --on 2>/dev/null
      log "HDMI re-assert $o"
      ;;
    esac
  done
fi

if [[ "$FIX" -eq 1 ]]; then
  log "--- --fix: reinstall display firmware + DT ---"
  ROOT=""
  for c in /opt/esp-handset/display "$HOME/esp-phone/pi_handset/display" \
           "$(dirname "$0")/../display"; do
    if [[ -x "$c/install-display.sh" ]] || [[ -f "$c/install-display.sh" ]]; then
      ROOT="$c"; break
    fi
  done
  if [[ -z "$ROOT" ]]; then
    log "ERROR: install-display.sh not found (git pull + install-handset)"
    exit 1
  fi
  if [[ "$(id -u)" -ne 0 ]]; then
    log "re-run as: sudo digivice-spi-doctor --fix"
    exit 1
  fi
  bash "$ROOT/install-display.sh"
  log "REBOOT REQUIRED: sudo reboot"
  log "Then: digivice-spi-doctor && digivice-spi-doctor --modes"
fi

log "=== end spi-doctor ==="
exit 0
