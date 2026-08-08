#!/bin/bash
# Digivice session helpers. Default boot mode is DESKTOP (normal Pi UI on HDMI).
# Enter phone UI with: handset-phone
# Exit phone UI with:  handset-desktop   or F12 inside Digivice

set -euo pipefail

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
MODE_FILE="${HOME}/.esp-handset/session_mode"
mkdir -p "$(dirname "$MODE_FILE")"

mode_get() {
  if [[ -f "$MODE_FILE" ]]; then
    tr -d '[:space:]' <"$MODE_FILE"
  else
    # Safe default: never trap on Digivice after install
    echo desktop
  fi
}

mode_set() {
  echo "$1" >"$MODE_FILE"
  if [[ -w /etc/esp-handset/ui_mode ]] || [[ -w /etc/esp-handset ]]; then
    echo "$1" >/etc/esp-handset/ui_mode 2>/dev/null || true
  fi
}

# Prefer the running desktop/session display (HDMI). Only fall back to bare
# linuxfb when there is no graphical session at all.
digivice_display_env() {
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

hide_desktop_chrome() {
  command -v lxpanelctl >/dev/null 2>&1 && lxpanelctl hide || true
  command -v wmctrl >/dev/null 2>&1 && wmctrl -k on || true
}

show_desktop_chrome() {
  command -v lxpanelctl >/dev/null 2>&1 && lxpanelctl show || true
  command -v wmctrl >/dev/null 2>&1 && wmctrl -k off || true
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
    export ESP_HANDSET_KIOSK=1
    exec /usr/bin/python3 "$PREFIX/handset_app.py"
    ;;
  autostart)
    # Only auto-launch Digivice when explicitly set to phone
    m="$(mode_get)"
    if [[ "$m" != "phone" ]]; then
      show_desktop_chrome
      exit 0
    fi
    digivice_display_env
    export ESP_HANDSET_KIOSK=1
    exec /usr/bin/python3 "$PREFIX/handset_app.py"
    ;;
  desktop)
    mode_set desktop
    kill_phone_ui
    show_desktop_chrome
    echo "Desktop mode (HDMI/session). handset-phone to open Digivice again."
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
        mode_set desktop
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

  desktop       Kill Digivice, stay on normal Pi desktop (default / safe)
  phone         Launch Digivice UI
  autostart     Login hook — only opens Digivice if session_mode=phone
  mode          Print phone|desktop
  set-phone / set-desktop

  digivice-recover-hdmi   (separate cmd) restore HDMI if nohdmi was set

Mode file: $MODE_FILE
EOF
    exit 1
    ;;
esac
