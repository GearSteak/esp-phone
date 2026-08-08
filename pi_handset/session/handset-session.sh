#!/bin/bash
# Digivice session helpers.
# Leave Digivice: Back×3 | Home×3 | Settings→Linux | handset-desktop | digivice-leave
# Recovery with no keyboard: put empty file digivice-desktop on the SD boot partition.

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

kill_phone_ui() {
  pkill -f "$PREFIX/handset_app.py" 2>/dev/null || true
  pkill -f "handset_app.py" 2>/dev/null || true
}

# Recovery flag on FAT boot partition (Windows can create this while SD is in a PC)
boot_flag_desktop() {
  local f
  for f in \
    /boot/firmware/digivice-desktop \
    /boot/digivice-desktop \
    /boot/firmware/DIGIVICE-DESKTOP \
    /boot/DIGIVICE-DESKTOP
  do
    [[ -f "$f" ]] && return 0
  done
  return 1
}

force_desktop_from_boot_flag() {
  if boot_flag_desktop; then
    log "boot flag digivice-desktop present → force desktop"
    mode_set desktop
    kill_phone_ui
    pkill -9 -f handset_app.py 2>/dev/null || true
    return 0
  fi
  return 1
}

digivice_display_env() {
  export QT_AUTO_SCREEN_SCALE_FACTOR=0
  export QT_SCALE_FACTOR=1
  export QT_ENABLE_HIGHDPI_SCALING=0
  export ESP_HANDSET_MIRROR="${ESP_HANDSET_MIRROR:-1}"
  export ESP_HANDSET_SKIP_PIN="${ESP_HANDSET_SKIP_PIN:-1}"
  export ESP_HANDSET_SKIP_LAYOUT="${ESP_HANDSET_SKIP_LAYOUT:-0}"

  if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    export DISPLAY=:0
  fi

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
  if command -v xrandr >/dev/null 2>&1; then
    export DISPLAY="${DISPLAY:-:0}"
    xrandr --auto 2>/dev/null || true
  fi
}

launch_phone() {
  if force_desktop_from_boot_flag; then
    show_desktop_chrome
    log "not launching Digivice (recovery flag)"
    return 0
  fi
  mode_set phone
  digivice_display_env
  apply_digivice_layout
  export ESP_HANDSET_KIOSK=1
  local app="$PREFIX/handset_app.py"
  if [[ ! -f "$app" ]]; then
    log "ERROR missing $app"
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
  exec /usr/bin/python3 "$app" >>"$LOG" 2>&1
}

cmd="${1:-}"
case "$cmd" in
  mode) mode_get ;;
  set-phone) mode_set phone; log "mode=phone" ;;
  set-desktop) mode_set desktop; log "mode=desktop" ;;
  phone) launch_phone ;;
  autostart)
    # Always honor recovery file on boot partition first
    if force_desktop_from_boot_flag; then
      show_desktop_chrome
      log "autostart: desktop (boot recovery flag)"
      exit 0
    fi
    m="$(mode_get)"
    log "autostart mode=$m"
    if [[ "$m" != "phone" ]]; then
      show_desktop_chrome
      exit 0
    fi
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
    pkill -9 -f handset_app.py 2>/dev/null || true
    show_desktop_chrome
    command -v lxpanelctl >/dev/null 2>&1 && lxpanelctl show || true
    echo "Left Digivice. mode=desktop. Return: handset-phone"
    log "desktop ready"
    ;;
  kill|force-desktop)
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
  phone / autostart / desktop / force-desktop / layout / set-phone / set-desktop / mode / log

Hard buttons (no USB keyboard):
  Back ×3 quickly  → desktop
  Home ×3 quickly  → desktop

No keyboard recovery: power off, put SD in PC, create empty file on boot volume:
  digivice-desktop
Then reinsert SD and boot (Linux desktop, Digivice stays off until you handset-phone).

Mode file: $MODE_FILE
Log: $LOG
EOF
    exit 1
    ;;
esac
