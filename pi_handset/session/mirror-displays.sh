#!/usr/bin/env bash
# Mirror Digivice: same picture on Waveshare SPI + HDMI.
# Prefer SPI (240x320) as the layout source; HDMI scales that image up.
#
# Call once a graphical session exists (DISPLAY or WAYLAND_DISPLAY).
# Safe to re-run.
set -euo pipefail

log() { echo "[mirror-displays] $*" >&2; }

# --- X11 / Xwayland-friendly path (best cloning support) -----------------
mirror_x11() {
  command -v xrandr >/dev/null 2>&1 || return 1
  [[ -n "${DISPLAY:-}" ]] || return 1

  # Collect connected names (strip trailing)
  mapfile -t outs < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
  if [[ ${#outs[@]} -lt 2 ]]; then
    log "X11: need two outputs for mirror (have ${#outs[@]})"
    return 1
  fi

  local spi="" hdmi="" o
  for o in "${outs[@]}"; do
    case "$o" in
      *SPI*|*DPI*|*DSI*|PANEL*|Writeback*) spi="$o" ;;
      HDMI*|hdmi*) hdmi="$o" ;;
    esac
  done
  # Fallback: first two connected
  if [[ -z "$spi" || -z "$hdmi" ]]; then
    spi="${outs[0]}"
    hdmi="${outs[1]}"
    log "X11: guessed primary=$spi secondary=$hdmi"
  else
    log "X11: primary(SPI)=$spi  mirror→$hdmi"
  fi

  # SPI preferred as content source (phone resolution)
  xrandr --output "$spi" --auto --primary 2>/dev/null || \
    xrandr --output "$spi" --mode 240x320 --primary 2>/dev/null || true

  # HDMI shows a scaled clone of the 240×320 plane when --scale-from works
  if xrandr --output "$hdmi" --auto --scale-from 240x320 --same-as "$spi" 2>/dev/null; then
    log "X11: HDMI mirrored from 240x320 (scale-from)"
    return 0
  fi
  if xrandr --output "$hdmi" --auto --same-as "$spi" 2>/dev/null; then
    log "X11: HDMI --same-as $spi"
    return 0
  fi
  # Last resort: both at 0,0
  xrandr --output "$hdmi" --auto --pos 0x0 2>/dev/null || true
  xrandr --output "$spi" --auto --pos 0x0 --primary 2>/dev/null || true
  log "X11: overlapping pos 0,0 (soft mirror)"
  return 0
}

# --- Wayland / labwc ------------------------------------------------------
mirror_wayland() {
  [[ -n "${WAYLAND_DISPLAY:-}" || -n "${XDG_SESSION_TYPE:-}" ]] || return 1
  # If pure Wayland (no xrandr targets), try wlr-randr + optional wl-mirror
  if command -v wlr-randr >/dev/null 2>&1; then
    mapfile -t outs < <(wlr-randr 2>/dev/null | awk '/^[^ ]/{print $1}')
    if [[ ${#outs[@]} -ge 2 ]]; then
      local a="${outs[0]}" b="${outs[1]}"
      # Stack both at origin — some compositors then treat as clone
      wlr-randr --output "$a" --pos 0,0 --on 2>/dev/null || true
      wlr-randr --output "$b" --pos 0,0 --on 2>/dev/null || true
      log "Wayland: wlr-randr both at 0,0 ($a, $b)"
    fi
  fi

  # wl-mirror: real clone of one output into a fullscreen surface on the other
  if command -v wl-mirror >/dev/null 2>&1; then
    pkill -f 'wl-mirror' 2>/dev/null || true
    # Prefer mirror SPI → fullscreen window (user can drag to HDMI if needed)
    # Backend streaming often follows focused/fullscreen apps better mirrored via:
    #   wl-mirror -F <source>
    nohup wl-mirror -F -s 240x320 2>/dev/null &
    log "Wayland: started wl-mirror (install fixed: sudo apt install wl-mirror)"
    return 0
  fi

  # Xwayland often still exposes xrandr under labwc
  if mirror_x11; then
    return 0
  fi

  log "Wayland: install wl-mirror or use raspi-config → Advanced → Wayland → X11 for better mirror"
  return 1
}

main() {
  # Prefer X11-style clone when available
  if mirror_x11; then
    exit 0
  fi
  if mirror_wayland; then
    exit 0
  fi
  log "Could not configure mirror automatically."
  log "Manual (Screen Configuration GUI): set both displays to Mirror / Clone."
  log "Or: sudo raspi-config → Advanced Options → Wayland → X11, reboot, retry."
  exit 0
}

main "$@"
