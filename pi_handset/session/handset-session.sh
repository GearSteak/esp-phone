#!/bin/bash
# Digivice session helpers.
# Default when mode file missing: phone (Digivice).
# HDMI is never disabled by this script — display is kernel config only.
# Exit Digivice: handset-desktop | F12 | Ctrl+Shift+D

set -euo pipefail

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
MODE_FILE="${HOME}/.esp-handset/session_mode"
mkdir -p "$(dirname "$MODE_FILE")"

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

# Prefer running desktop/session (HDMI works). Only bare linuxfb if no GUI session.
digivice_display_env() {
  # Always prevent HiDPI crop of phone UI
  export QT_AUTO_SCREEN_SCALE_FACTOR=0
  export QT_SCALE_FACTOR=1
  export QT_ENABLE_HIGHDPI_SCALING=0
  export ESP_HANDSET_MIRROR="${ESP_HANDSET_MIRROR:-1}"

  if [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
    unset QT_QPA_PLATFORM 2>/dev/null || true
    export QT_XCB_NO_XI2_MOUSE="${QT_XCB_NO_XI2_MOUSE:-0}"
    return 0
  fi
  if [[ -e /dev/fb0 ]]; then
    export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-linuxfb:fb=/dev/fb0}"
    export QT_QPA_FB_FORCE_FULLSCREEN="${QT_QPA_FB_FORCE_FULLSCREEN:-1}"
    export QT_QPA_GENERIC_PLUGINS="${QT_QPA_GENERIC_PLUGINS:-evdevkeyboard,evdevmouse}"
    export QT_QPA_EVDEV_KEYBOARD_PARAMETERS="${QT_QPA_EVDEV_KEYBOARD_PARAMETERS:-grab=1}"
  fi
}

# SPI primary + optional HDMI clone (must run before Digivice)
apply_digivice_layout() {
  local m=""
  for m in \
    "$PREFIX/session/digivice-layout.sh" \
    /usr/local/bin/digivice-layout \
    "$(dirname "$0")/digivice-layout.sh"
  do
    if [[ -f "$m" ]]; then
      # shellcheck disable=SC1090
      bash "$m" 2>&1 || true
      return 0
    fi
  done
  # Fallback old mirror script
  for m in \
    "$PREFIX/session/mirror-displays.sh" \
    /usr/local/bin/digivice-mirror-displays
  do
    if [[ -f "$m" ]]; then
      bash "$m" 2>/dev/null || true
      return 0
    fi
  done
}

hide_desktop_chrome() {
  command -v lxpanelctl >/dev/null 2>&1 && lxpanelctl hide || true
  command -v wmctrl >/dev/null 2>&1 && wmctrl -k on || true
}

show_desktop_chrome() {
  command -v lxpanelctl >/dev/null 2>&1 && lxpanelctl show || true
  command -v wmctrl >/dev/null 2>&1 && wmctrl -k off || true
  # Restore HDMI if layout turned it off
  if command -v xrandr >/dev/null 2>&1 && [[ -n "${DISPLAY:-}" ]]; then
    mapfile -t outs < <(xrandr --query 2>/dev/null | awk '/ connected|disconnected/{print $1,$2}')
    # turn on any HDMI currently disconnected from config... use --auto on HDMI names
    while read -r name rest; do
      case "$name" in
        HDMI*|hdmi*) xrandr --output "$name" --auto 2>/dev/null || true ;;
      esac
    done < <(xrandr --query 2>/dev/null | awk '/^(HDMI|hdmi)/{print $1}')
  fi
}

kill_phone_ui() {
  pkill -f "$PREFIX/handset_app.py" 2>/dev/null || true
  pkill -f "handset_app.py" 2>/dev/null || true
  pkill -f "esp_handset/handset_app.py" 2>/dev/null || true
}

cmd="${1:-}"
case "$cmd" in
  mode)
    mode_get
    ;;
  set-phone)
    mode_set phone
    ;;
  set-desktop)
    mode_set desktop
    ;;
  phone)
    mode_set phone
    digivice_display_env
    apply_digivice_layout
    export ESP_HANDSET_KIOSK=1
    exec /usr/bin/python3 "$PREFIX/handset_app.py"
    ;;
  autostart)
    m="$(mode_get)"
    if [[ "$m" != "phone" ]]; then
      show_desktop_chrome
      exit 0
    fi
    digivice_display_env
    apply_digivice_layout
    ( sleep 2; apply_digivice_layout ) &
    export ESP_HANDSET_KIOSK=1
    exec /usr/bin/python3 "$PREFIX/handset_app.py"
    ;;
  mirror|layout)
    digivice_display_env
    apply_digivice_layout
    echo "Digivice display layout applied (SPI primary; HDMI clone if possible)."
    ;;
  desktop)
    kill_phone_ui
    show_desktop_chrome
    echo "Left Digivice (UI). Default login is still: $(mode_get)"
    echo "  set-desktop  → make desktop the boot default"
    echo "  set-phone / handset-phone → Digivice"
    ;;
  maps)
    for bin in organicmaps osmAnd coMaps gnome-maps; do
      if command -v "$bin" >/dev/null 2>&1; then
        exec "$bin" "$@"
      fi
    done
    if command -v flatpak >/dev/null 2>&1; then
      flatpak run app.organicmaps.desktop 2>/dev/null && exit 0 || true
    fi
    echo "No maps app found." >&2
    exit 1
    ;;
  browser)
    for bin in midori epiphany netsurf-gtk chromium-browser chromium firefox-esr; do
      if command -v "$bin" >/dev/null 2>&1; then
        exec "$bin" "$@"
      fi
    done
    echo "No light browser found. Try: sudo apt install midori" >&2
    exit 1
    ;;
  emulators)
    for bin in retroarch emulationstation mednafen; do
      if command -v "$bin" >/dev/null 2>&1; then
        show_desktop_chrome
        exec "$bin" "$@"
      fi
    done
    echo "No emulator frontend found." >&2
    exit 1
    ;;
  *)
    cat <<EOF
Usage: handset-session <command>

  phone         Launch Digivice + mirror SPI/HDMI when possible
  mirror        Re-apply same picture on both screens
  desktop       Kill Digivice UI only (login default unchanged)
  set-phone     Digivice default at next login/boot
  set-desktop   Desktop default at next login/boot
  mode          Print phone|desktop

Escape Digivice UI: F12 · Ctrl+Shift+D · Settings→Linux · handset-desktop

Mode: $MODE_FILE
EOF
    exit 1
    ;;
esac
