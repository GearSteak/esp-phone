#!/usr/bin/env bash
# Make SPI 2" the PRIMARY desktop and clone it up to HDMI (same content).
# Without this, Digivice fullscreen lands on HDMI and the tiny screen only
# shows the top-left crop of 1080p — exactly the "1/6 of the corner" bug.
#
#   digivice-mirror-displays
# Safe to re-run. Prefer X11: raspi-config → Advanced → Wayland → X11.
set -euo pipefail

log() { echo "[mirror-displays] $*" >&2; }

prefer_modes() {
  # modes that match Digivice panel / rotated panel
  echo "240x320 320x240 240x240"
}

find_spi_hdmi() {
  # Sets SPI_OUT HDMI_OUT from connected list
  SPI_OUT=""
  HDMI_OUT=""
  local o
  for o in "$@"; do
    case "$o" in
      *SPI*|*DPI*|*DSI*|*PANEL*) SPI_OUT="$o" ;;
      HDMI*|hdmi*) HDMI_OUT="$o" ;;
    esac
  done
}

# Prefer smallest-area output as "panel" if names unknown
pick_smallest() {
  command -v xrandr >/dev/null 2>&1 || return 1
  xrandr --query 2>/dev/null | awk '
    / connected/ {
      name=$1
      # next line often has current mode WxH+X+Y
    }
    name != "" && $0 ~ /[0-9]+x[0-9]+\+[0-9]+\+[0-9]+/ {
      split($1, a, "x")
      w=a[1]+0; h=a[2]+0
      if (w*h > 0 && (best == 0 || w*h < best)) { best=w*h; out=name }
      name=""
    }
    END { if (out != "") print out }
  '
}

mirror_x11() {
  command -v xrandr >/dev/null 2>&1 || return 1
  [[ -n "${DISPLAY:-}" ]] || return 1

  mapfile -t outs < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
  if [[ ${#outs[@]} -lt 1 ]]; then
    log "X11: no connected outputs"
    return 1
  fi

  find_spi_hdmi "${outs[@]}"
  if [[ -z "$SPI_OUT" ]]; then
    SPI_OUT="$(pick_smallest || true)"
  fi
  if [[ -z "$SPI_OUT" ]]; then
    SPI_OUT="${outs[0]}"
  fi
  if [[ -z "$HDMI_OUT" ]]; then
    for o in "${outs[@]}"; do
      if [[ "$o" != "$SPI_OUT" ]]; then
        HDMI_OUT="$o"
        break
      fi
    done
  fi

  log "panel/primary=$SPI_OUT  hdmi=$HDMI_OUT"

  # Turn SPI on as the *layout source* at native Digivice size
  local mode_ok=0
  for mode in 240x320 320x240 240x240; do
    if xrandr --output "$SPI_OUT" --mode "$mode" --primary --pos 0x0 2>/dev/null; then
      mode_ok=1
      log "SPI mode $mode primary"
      break
    fi
  done
  if [[ "$mode_ok" -eq 0 ]]; then
    xrandr --output "$SPI_OUT" --auto --primary --pos 0x0 2>/dev/null || true
    log "SPI --auto primary"
  fi

  if [[ -n "$HDMI_OUT" && "$HDMI_OUT" != "$SPI_OUT" ]]; then
    # Clone SPI plane onto HDMI (scaled). Failures fall through.
    local sw sh
    sw="$(xrandr --query | awk -v o="$SPI_OUT" '
      $0 ~ o" connected" {getline; if (match($0,/([0-9]+)x([0-9]+)/,a)){print a[1]; exit}}
    ')"
    sh="$(xrandr --query | awk -v o="$SPI_OUT" '
      $0 ~ o" connected" {getline; if (match($0,/([0-9]+)x([0-9]+)/,a)){print a[2]; exit}}
    ')"
    sw="${sw:-240}"
    sh="${sh:-320}"
    if xrandr --output "$HDMI_OUT" --auto --scale-from "${sw}x${sh}" --same-as "$SPI_OUT" 2>/dev/null; then
      log "HDMI scaled clone of ${sw}x${sh}"
      return 0
    fi
    if xrandr --output "$HDMI_OUT" --same-as "$SPI_OUT" 2>/dev/null; then
      log "HDMI --same-as $SPI_OUT"
      return 0
    fi
    # Move HDMI far away so it does not extend past SPI (avoids crop UX);
    # user still gets SPI full Digivice. Optional dim secondary.
    xrandr --output "$HDMI_OUT" --auto --pos 0x0 2>/dev/null || true
    log "HDMI pos overlap (soft). Install X11 if clone failed."
  fi
  return 0
}

mirror_wayland() {
  if command -v wlr-randr >/dev/null 2>&1; then
    mapfile -t outs < <(wlr-randr 2>/dev/null | awk '/^[^ ]/{print $1}')
    local panel="" hdmi="" o
    for o in "${outs[@]:-}"; do
      case "$o" in
        *SPI*|*DPI*|*DSI*) panel="$o" ;;
        *HDMI*) hdmi="$o" ;;
      esac
    done
    panel="${panel:-${outs[0]:-}}"
    if [[ -n "$panel" ]]; then
      # Prefer logical size close to Digivice
      wlr-randr --output "$panel" --on --pos 0,0 2>/dev/null || true
      if [[ -n "$hdmi" ]]; then
        wlr-randr --output "$hdmi" --on --pos 0,0 2>/dev/null || true
      fi
      log "Wayland: panel=$panel at 0,0 (clone not guaranteed)"
    fi
  fi
  if command -v wl-mirror >/dev/null 2>&1 && [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
    pkill -x wl-mirror 2>/dev/null || true
    # Mirror whatever is primary into a fullscreen window on the other output if supported
    nohup wl-mirror -F 2>/dev/null &
    log "started wl-mirror -F"
  fi
  # Xwayland xrandr often still works
  mirror_x11 || true
  return 0
}

main() {
  if [[ -n "${DISPLAY:-}" ]] && mirror_x11; then
    exit 0
  fi
  mirror_wayland || true
  log "Done. Digivice must fullscreen the *small* screen (handset does this in software)."
  log "If tiny panel still crops: sudo raspi-config → Advanced → Wayland → X11, reboot."
  exit 0
}

main "$@"
