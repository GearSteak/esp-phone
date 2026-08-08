#!/bin/bash
# Phone-first session helpers for ESP Handset on Raspberry Pi OS.
# Default: boot into fullscreen phone UI. Escape hatch: desktop for
# emulators / Linux programs / maps / browser.

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
  # Shared with hat-inputd (file is user-writable from install)
  if [[ -w /etc/esp-handset/ui_mode ]] || [[ -w /etc/esp-handset ]]; then
    echo "$1" >/etc/esp-handset/ui_mode 2>/dev/null || true
  fi
}

# Drive Digivice on the Waveshare SPI panel when no desktop session is up.
digivice_display_env() {
  if [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
    return 0
  fi
  if [[ -e /dev/fb0 ]]; then
    export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-linuxfb:fb=/dev/fb0}"
    export QT_QPA_FB_FORCE_FULLSCREEN="${QT_QPA_FB_FORCE_FULLSCREEN:-1}"
  fi
}

hide_desktop_chrome() {
  # Best-effort; ignore failures on Wayland / Lite
  command -v lxpanelctl >/dev/null 2>&1 && lxpanelctl hide || true
  command -v wmctrl >/dev/null 2>&1 && wmctrl -k on || true
}

show_desktop_chrome() {
  command -v lxpanelctl >/dev/null 2>&1 && lxpanelctl show || true
  command -v wmctrl >/dev/null 2>&1 && wmctrl -k off || true
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
    # Launch / return to phone UI (fullscreen kiosk)
    mode_set phone
    hide_desktop_chrome
    digivice_display_env
    export ESP_HANDSET_KIOSK=1
    exec /usr/bin/python3 "$PREFIX/handset_app.py"
    ;;
  autostart)
    # Called from .config/autostart — only enter phone if mode is phone
    m="$(mode_get)"
    if [[ "$m" != "phone" ]]; then
      show_desktop_chrome
      exit 0
    fi
    hide_desktop_chrome
    digivice_display_env
    export ESP_HANDSET_KIOSK=1
    exec /usr/bin/python3 "$PREFIX/handset_app.py"
    ;;
  desktop)
    # Exit phone → show desktop (emulators, terminal, etc.)
    mode_set desktop
    show_desktop_chrome
    pkill -f "$PREFIX/handset_app.py" 2>/dev/null || true
    pkill -f "handset_app.py" 2>/dev/null || true
    echo "Desktop mode. Run: handset-phone   to return."
    ;;
  maps)
    # Prefer offline-friendly maps if installed
    for bin in organicmaps osmAnd coMaps gnome-maps; do
      if command -v "$bin" >/dev/null 2>&1; then
        exec "$bin" "$@"
      fi
    done
    # Flatpak ids (optional)
    if command -v flatpak >/dev/null 2>&1; then
      flatpak run app.organicmaps.desktop 2>/dev/null && exit 0 || true
    fi
    echo "No maps app found. Install Organic Maps (or similar) later." >&2
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
    # Soft launchers — user installs cores later
    for bin in retroarch emulationstation mednafen; do
      if command -v "$bin" >/dev/null 2>&1; then
        mode_set desktop
        show_desktop_chrome
        exec "$bin" "$@"
      fi
    done
    echo "No emulator frontend found. From Desktop: sudo apt install retroarch" >&2
    exit 1
    ;;
  *)
    cat <<EOF
Usage: handset-session <command>

  autostart     Boot helper (phone UI if session_mode=phone)
  phone         Enter phone UI (fullscreen)
  desktop       Exit to desktop (Linux apps / emulators)
  maps          Launch maps if installed
  browser       Launch a light browser if installed
  emulators     Launch RetroArch / ES if installed
  mode          Print phone|desktop
  set-phone     Set mode without launching
  set-desktop   Set mode without launching

Mode file: $MODE_FILE
EOF
    exit 1
    ;;
esac
