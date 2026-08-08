#!/bin/bash
# Digivice session helpers — always try to launch with logs.
# Exit Digivice: handset-desktop | F12 | Ctrl+Shift+D

set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
MODE_FILE="${HOME}/.esp-handset/session_mode"
LOG_DIR="${HOME}/.esp-handset"
LOG="${LOG_DIR}/handset.log"
mkdir -p "$(dirname "$MODE_FILE")" "$LOG_DIR"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG" >&2; }

mode_get() {
  if [[ -f "$MODE_FILE" ]]; then
    tr -d '[:space:]' <"$MODE_FILE"
  else
    echo phone
  fi
}

mode_set() {
  echo "$1" >"$MODE_FILE"
  if [[ -w /etc/esp-handset/ui_mode ]] || [[ -w /etc/esp-handset ]]; then
    echo "$1" >/etc/esp-handset/ui_mode 2>/dev/null || true
  fi
}

digivice_display_env() {
  export QT_AUTO_SCREEN_SCALE_FACTOR=0
  export QT_SCALE_FACTOR=1
  export QT_ENABLE_HIGHDPI_SCALING=0
  # SPI primary + optional HDMI clone (layout). Digivice fullscreen on panel.
  export ESP_HANDSET_MIRROR="${ESP_HANDSET_MIRROR:-1}"
  export ESP_HANDSET_SKIP_PIN="${ESP_HANDSET_SKIP_PIN:-1}"
  # Always run digivice-layout so Unknown/SPI is on as primary
  export ESP_HANDSET_SKIP_LAYOUT="${ESP_HANDSET_SKIP_LAYOUT:-0}"

  if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    export DISPLAY=:0
  fi

  # Graphical session: NEVER fall through to linuxfb (that was hiding Digivice)
  if [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
    if [[ -n "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
      export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
    else
      unset QT_QPA_PLATFORM 2>/dev/null || true
    fi
    return 0
  fi

  if [[ -e /dev/fb0 ]]; then
    export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-linuxfb:fb=/dev/fb0}"
    export QT_QPA_FB_FORCE_FULLSCREEN=1
    export QT_QPA_GENERIC_PLUGINS="${QT_QPA_GENERIC_PLUGINS:-evdevkeyboard,evdevmouse}"
  fi
}

apply_digivice_layout() {
  if [[ "${ESP_HANDSET_SKIP_LAYOUT:-0}" == "1" ]]; then
    log "skip digivice-layout"
    return 0
  fi
  local m
  for m in \
    "$PREFIX/session/digivice-layout.sh" \
    /usr/local/bin/digivice-layout \
    "$(dirname "$0")/digivice-layout.sh"
  do
    if [[ -f "$m" ]]; then
      log "layout: $m"
      bash "$m" >>"$LOG" 2>&1 || true
      return 0
    fi
  done
  log "layout script missing — continue"
}

show_desktop_chrome() {
  command -v lxpanelctl >/dev/null 2>&1 && lxpanelctl show || true
  command -v wmctrl >/dev/null 2>&1 && wmctrl -k off || true
  local r
  for r in \
    "$PREFIX/session/restore-desktop-displays.sh" \
    /usr/local/bin/digivice-restore-desktop \
    "$(dirname "$0")/restore-desktop-displays.sh"
  do
    if [[ -f "$r" ]]; then
      bash "$r" >>"$LOG" 2>&1 || true
      break
    fi
  done
}

kill_phone_ui() {
  pkill -f "$PREFIX/handset_app.py" 2>/dev/null || true
  pkill -f "handset_app.py" 2>/dev/null || true
}

launch_phone() {
  mode_set phone
  digivice_display_env
  apply_digivice_layout
  export ESP_HANDSET_KIOSK=1
  local app="$PREFIX/handset_app.py"
  if [[ ! -f "$app" ]]; then
    log "ERROR missing $app"
    # Try repo-style path next to this script
    local alt
    alt="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)/esp_handset/handset_app.py"
    if [[ -f "$alt" ]]; then
      app="$alt"
      export PYTHONPATH="$(dirname "$alt")/..:${PYTHONPATH:-}"
    else
      log "FATAL: no handset_app.py"
      return 1
    fi
  fi
  log "starting $app DISPLAY=${DISPLAY:-} WAYLAND=${WAYLAND_DISPLAY:-}"
  # Do not use exec so we can log exit codes from autostart debugging —
  # but phone interactive still wants exclusive process. Use exec for phone.
  exec /usr/bin/python3 "$app" >>"$LOG" 2>&1
}

cmd="${1:-}"
case "$cmd" in
  mode) mode_get ;;
  set-phone) mode_set phone; log "mode=phone" ;;
  set-desktop) mode_set desktop; log "mode=desktop" ;;
  phone) launch_phone ;;
  autostart)
    m="$(mode_get)"
    log "autostart mode=$m"
    if [[ "$m" != "phone" ]]; then
      show_desktop_chrome
      exit 0
    fi
    # Wait for desktop/session display
    sleep 2
    digivice_display_env
    apply_digivice_layout
    launch_phone
    ;;
  mirror|layout)
    digivice_display_env
    apply_digivice_layout
    echo "Layout done — see $LOG"
    ;;
  desktop)
    mode_set desktop
    log "leaving Digivice → desktop"
    kill_phone_ui
    sleep 0.2
    # Force-kill stuck UI
    pkill -9 -f handset_app.py 2>/dev/null || true
    show_desktop_chrome
    # Unblank HDMI / panel for desktop use
    if command -v xrandr >/dev/null 2>&1; then
      export DISPLAY="${DISPLAY:-:0}"
      while read -r name; do
        xrandr --output "$name" --auto 2>/dev/null || true
      done < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
    fi
    # Show panels / taskbars if present
    command -v lxpanelctl >/dev/null 2>&1 && lxpanelctl show || true
    command -v wmctrl >/dev/null 2>&1 && wmctrl -k off || true
    echo "Left Digivice. mode=desktop. Return: handset-phone"
    log "desktop ready"
    ;;
  kill|force-desktop)
    # Emergency from SSH/terminal when UI is stuck
    mode_set desktop
    kill_phone_ui
    pkill -9 -f handset_app.py 2>/dev/null || true
    pkill -9 -f "python3.*handset" 2>/dev/null || true
    show_desktop_chrome
    echo "Force-killed Digivice. mode=desktop"
    ;;
  log)
    tail -n 80 "$LOG" 2>/dev/null || echo "(no log yet at $LOG)"
    ;;
  *)
    cat <<EOF
Usage: handset-session <command>
  phone / autostart / desktop / layout / set-phone / set-desktop / mode / log
Mode file: $MODE_FILE
Log: $LOG
EOF
    exit 1
    ;;
esac
