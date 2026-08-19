#!/bin/bash
# Digivice session helpers.
# Leave Digivice: Back×3 | Settings→Linux | handset-desktop | digivice-leave
# Home always returns to Digivice (on desktop: relaunches Digivice; in UI: home screen)
# Recovery with no keyboard: put empty file digivice-desktop on the SD boot partition.

set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
MODE_FILE="${HOME}/.esp-handset/session_mode"
LOG_DIR="${HOME}/.esp-handset"
LOG="${LOG_DIR}/handset.log"
mkdir -p "$(dirname "$MODE_FILE")" "$LOG_DIR"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG" >&2; }

# Pause I2C (stop) or give it back to Linux (start). Never systemctl stop —
# that destroys the uinput keyboard and labwc will not type CardKB.
cardkb_ctl() {
  local op="${1:-}"
  case "$op" in
    start|stop) ;;
    *) return 1 ;;
  esac
  if [[ "$(id -u)" -eq 0 ]]; then
    if command -v digivice-cardkb-ctl >/dev/null 2>&1; then
      digivice-cardkb-ctl "$op" >/dev/null 2>&1 && return 0
    fi
  else
    if command -v digivice-cardkb-ctl >/dev/null 2>&1; then
      sudo -n digivice-cardkb-ctl "$op" >/dev/null 2>&1 && return 0
    fi
  fi
  mkdir -p /run/digivice 2>/dev/null || true
  chmod 0777 /run/digivice 2>/dev/null || true
  if [[ "$op" == "stop" ]]; then
    echo 1 >/run/digivice/cardkb.pause 2>/dev/null || true
    chmod 666 /run/digivice/cardkb.pause 2>/dev/null || true
  else
    rm -f /run/digivice/cardkb.pause /tmp/digivice-cardkb.pause 2>/dev/null || true
  fi
  if [[ "$(id -u)" -eq 0 ]]; then
    systemctl start cardkb-inputd.service >/dev/null 2>&1 || true
  else
    sudo -n /usr/bin/systemctl start cardkb-inputd >/dev/null 2>&1 || true
  fi
  return 0
}

mode_get() {
  if [[ -f "$MODE_FILE" ]]; then
    tr -d '[:space:]' <"$MODE_FILE"
  else
    echo phone
  fi
}

mode_set() {
  local m="$1"
  echo "$m" >"$MODE_FILE"
  mkdir -p /etc/esp-handset 2>/dev/null || true
  if [[ -w /etc/esp-handset/ui_mode ]] || [[ -w /etc/esp-handset ]]; then
    echo "$m" >/etc/esp-handset/ui_mode 2>/dev/null || true
  elif command -v sudo >/dev/null 2>&1; then
    echo "$m" | sudo -n tee /etc/esp-handset/ui_mode >/dev/null 2>&1 || true
  fi
  # Notify digi-buttons (reads mode file; also restart is overkill)
  log "session_mode=$m (buttons: phone=keys desktop=mouse)"
}

kill_phone_ui() {
  pkill -f "$PREFIX/handset_app.py" 2>/dev/null || true
  pkill -f "handset_app.py" 2>/dev/null || true
}

spi_drm_mode() {
  # Instructables / Adafruit: mipi-dbi panel is a real OS display
  if [[ -f /etc/esp-handset/spi-userspace ]]; then
    return 1
  fi
  if [[ -f /etc/esp-handset/spi-mode ]] \
    && grep -qi instructables /etc/esp-handset/spi-mode 2>/dev/null; then
    return 0
  fi
  if [[ -f /etc/esp-handset/display-mode ]] \
    && grep -qi instructables /etc/esp-handset/display-mode 2>/dev/null; then
    return 0
  fi
  [[ "${ESP_HANDSET_SPI_BACKEND:-}" == "drm" ]] && return 0
  if [[ -f /etc/esp-handset/spi-backend ]] \
    && grep -qi '^drm' /etc/esp-handset/spi-backend 2>/dev/null; then
    return 0
  fi
  if [[ -f /etc/esp-handset/env ]] \
    && grep -q 'ESP_HANDSET_SPI_BACKEND=drm' /etc/esp-handset/env 2>/dev/null; then
    return 0
  fi
  return 1
}

spi_userspace_on() {
  # Never userspace when Instructables DRM mode is active
  if spi_drm_mode; then
    return 1
  fi
  if [[ -f /etc/esp-handset/spi-userspace ]] \
    || [[ "${ESP_HANDSET_SPI_BACKEND:-}" == "userspace" ]] \
    || grep -q 'ESP_HANDSET_SPI_BACKEND=userspace' /etc/esp-handset/env 2>/dev/null; then
    return 0
  fi
  return 1
}

desktop_mirror_bin() {
  for m in \
    "$PREFIX/session/desktop-spi-mirror.sh" \
    /usr/local/bin/digivice-desktop-mirror \
    "$(dirname "$0")/desktop-spi-mirror.sh"
  do
    if [[ -f "$m" ]]; then
      echo "$m"
      return 0
    fi
  done
  echo ""
}

activate_spi_drm() {
  local s
  for s in \
    /usr/local/bin/digivice-spi-drm-activate \
    "$PREFIX/session/spi-drm-activate.sh" \
    "$(dirname "$0")/spi-drm-activate.sh"
  do
    if [[ -x "$s" || -f "$s" ]]; then
      log "SPI DRM activate (Instructables path): $s"
      bash "$s" >>"$LOG" 2>&1 || true
      return 0
    fi
  done
  log "WARN: digivice-spi-drm-activate missing"
  return 1
}

stop_desktop_spi_mirror() {
  local m
  m="$(desktop_mirror_bin)"
  if [[ -n "$m" ]]; then
    bash "$m" stop >>"$LOG" 2>&1 || true
  else
    pkill -f "desktop_spi_mirror.py" 2>/dev/null || true
  fi
}

start_desktop_spi_mirror() {
  # Instructables DRM path: OS owns the panel — no Python grab mirror
  if spi_drm_mode; then
    log "desktop SPI: DRM mode (Instructables) — enable panel head"
    stop_desktop_spi_mirror
    activate_spi_drm
    return 0
  fi
  if ! spi_userspace_on; then
    log "desktop SPI: try DRM activate (no userspace flag)"
    activate_spi_drm || true
    return 0
  fi
  export DISPLAY="${DISPLAY:-:0}"
  export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
  export ESP_HANDSET_SPI_BACKEND=userspace
  local m
  m="$(desktop_mirror_bin)"
  if [[ -z "$m" ]]; then
    log "desktop-spi-mirror.sh missing"
    return 1
  fi
  pkill -f "handset_app.py" 2>/dev/null || true
  rm -f /tmp/digivice-st7789.lock /run/digivice-st7789.lock 2>/dev/null || true
  sleep 0.8
  bash "$m" stop >>"$LOG" 2>&1 || true
  sleep 0.3
  bash "$m" start >>"$LOG" 2>&1 || true
  sleep 0.4
  if bash "$m" status >>"$LOG" 2>&1; then
    log "desktop → SPI mirror RUNNING"
  else
    log "WARN: desktop → SPI mirror not running — retry in 1s"
    sleep 1
    rm -f /tmp/digivice-st7789.lock /run/digivice-st7789.lock 2>/dev/null || true
    bash "$m" start >>"$LOG" 2>&1 || true
    bash "$m" status >>"$LOG" 2>&1 || log "ERROR: mirror failed — see $LOG"
  fi
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
  export ESP_HANDSET_MIRROR="${ESP_HANDSET_MIRROR:-0}"
  export ESP_HANDSET_SKIP_PIN="${ESP_HANDSET_SKIP_PIN:-1}"
  export ESP_HANDSET_SKIP_LAYOUT="${ESP_HANDSET_SKIP_LAYOUT:-0}"
  # 1 = SPI primary, HDMI off (proves dual-head was starving SPI)
  export ESP_HANDSET_SPI_ONLY="${ESP_HANDSET_SPI_ONLY:-0}"
  # Instructables-style ST7789 userspace mirror when /etc/esp-handset/spi-userspace exists
  if [[ -f /etc/esp-handset/spi-userspace ]] || [[ -f /etc/esp-handset/spi-backend ]]; then
    export ESP_HANDSET_SPI_BACKEND="${ESP_HANDSET_SPI_BACKEND:-userspace}"
    export ESP_HANDSET_SKIP_LAYOUT="${ESP_HANDSET_SKIP_LAYOUT:-1}"
  fi
  if [[ -f /etc/esp-handset/env ]]; then
    # shellcheck disable=SC1091
    set -a
    # shellcheck source=/dev/null
    source /etc/esp-handset/env 2>/dev/null || true
    set +a
  fi

  if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    export DISPLAY=:0
  fi

  # Desktop / .desktop launches often omit this — Qt then silently fails
  if [[ -n "${DISPLAY:-}" && -z "${XAUTHORITY:-}" ]]; then
    if [[ -f "${HOME}/.Xauthority" ]]; then
      export XAUTHORITY="${HOME}/.Xauthority"
    elif [[ -n "${SUDO_USER:-}" && -f "/home/${SUDO_USER}/.Xauthority" ]]; then
      export XAUTHORITY="/home/${SUDO_USER}/.Xauthority"
    fi
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
  local m args=()
  if [[ "${ESP_HANDSET_SPI_ONLY:-0}" == "1" ]]; then
    args+=(--spi-only)
    log "SPI-ONLY layout (HDMI off)"
  fi
  for m in \
    "$PREFIX/session/digivice-layout.sh" \
    /usr/local/bin/digivice-layout \
    "$(dirname "$0")/digivice-layout.sh"
  do
    if [[ -f "$m" ]]; then
      log "layout: $m ${args[*]:-}"
      bash "$m" "${args[@]}" >>"$LOG" 2>&1 || true
      return 0
    fi
  done
  log "layout script missing — continue"
}

show_desktop_chrome() {
  command -v lxpanelctl >/dev/null 2>&1 && lxpanelctl show || true
  command -v wmctrl >/dev/null 2>&1 && wmctrl -k off || true
  # Restart panels Digivice may have killed (Bookworm wf-panel-pi / lxpanel)
  pgrep -x lxpanel >/dev/null 2>&1 || (nohup lxpanel --profile LXDE-pi >/dev/null 2>&1 &) || true
  pgrep -x wf-panel-pi >/dev/null 2>&1 || (nohup wf-panel-pi >/dev/null 2>&1 &) || true
  # CardKB daemon for Linux desktop (Digivice used in-process reader)
  cardkb_ctl start
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
    # Light unlock only — do NOT run full digivice-hdmi-hotplug here
    # (2s sleep + primary thrash delayed SPI mirror and blanked captures).
    xrandr --auto 2>/dev/null || true
    while read -r line; do
      name="${line%% *}"
      case "$name" in
        HDMI*|hdmi*|DP-*)
          xrandr --output "$name" --auto --on 2>/dev/null || true
          ;;
      esac
    done < <(xrandr --query 2>/dev/null | awk '/ connected/{print}')
  fi
  # Yellow software pointer — hardware cursor often invisible on Pi / SPI clone
  for r in \
    /usr/local/bin/digivice-fix-cursor \
    "$PREFIX/session/fix-cursor.sh" \
    "$(dirname "$0")/fix-cursor.sh"
  do
    if [[ -f "$r" ]]; then
      # Default: system cursor only (no yellow double-cursor)
      bash "$r" >>"$LOG" 2>&1 || true
      break
    fi
  done
}

hide_desktop_chrome() {
  # Soft-hide only. Hard-killing wf-panel-pi / lxpanel crashed Digivice on open.
  # Opt-in hard kill: ESP_HANDSET_KILL_PANEL=1
  log "hide desktop taskbar / panels for Digivice"
  command -v lxpanelctl >/dev/null 2>&1 && lxpanelctl hide || true
  if [[ "${ESP_HANDSET_KILL_PANEL:-}" == "1" || "${ESP_HANDSET_KILL_PANEL:-}" == "true" ]]; then
    command -v wmctrl >/dev/null 2>&1 && wmctrl -k on || true
    pkill -x wf-panel-pi 2>/dev/null || true
    pkill -x wf-panel 2>/dev/null || true
    pkill -x waybar 2>/dev/null || true
    pkill -x lxpanel 2>/dev/null || true
    pkill -x lxqt-panel 2>/dev/null || true
    pcmanfm --desktop-off 2>/dev/null || true
  fi
}

# Always restore *system* cursor after SPI layout (no yellow overlay —
# that caused double cursors once the black cursor came back).
ensure_desktop_cursor() {
  log "ensure desktop cursor (system only, kill yellow overlay)"
  for r in \
    /usr/local/bin/digivice-fix-cursor \
    "$PREFIX/session/fix-cursor.sh" \
    "$(dirname "$0")/fix-cursor.sh"
  do
    if [[ -f "$r" ]]; then
      bash "$r" --stop >>"$LOG" 2>&1 || true
      bash "$r" >>"$LOG" 2>&1 || true
      return 0
    fi
  done
  pkill -f "pointer_overlay.py" 2>/dev/null || true
  log "WARN: digivice-fix-cursor missing"
  return 1
}

# Digivice phone UI: no mouse cursor
hide_phone_cursor() {
  log "hide cursor for Digivice UI"
  for r in \
    /usr/local/bin/digivice-fix-cursor \
    "$PREFIX/session/fix-cursor.sh" \
    "$(dirname "$0")/fix-cursor.sh"
  do
    if [[ -f "$r" ]]; then
      bash "$r" --hide >>"$LOG" 2>&1 || true
      return 0
    fi
  done
  pkill -f "pointer_overlay.py" 2>/dev/null || true
}

ensure_buttons_daemon() {
  # Hard keys are a separate systemd service — always on before Digivice
  if systemctl is-active --quiet digi-buttons-inputd 2>/dev/null \
    || systemctl is-active --quiet digi-buttons-inputd.service 2>/dev/null; then
    log "digi-buttons-inputd already active"
    return 0
  fi
  log "digi-buttons-inputd not active — enabling"
  local e
  for e in \
    /usr/local/bin/digivice-ensure-buttons \
    "$PREFIX/session/ensure-buttons.sh" \
    "$(dirname "$0")/ensure-buttons.sh"
  do
    if [[ -f "$e" ]]; then
      if [[ "$(id -u)" -eq 0 ]]; then
        bash "$e" >>"$LOG" 2>&1 && return 0
      fi
      sudo -n bash "$e" >>"$LOG" 2>&1 && return 0
      bash "$e" >>"$LOG" 2>&1 && return 0
    fi
  done
  sudo -n systemctl enable --now digi-buttons-inputd 2>>"$LOG" || true
  if systemctl is-active --quiet digi-buttons-inputd 2>/dev/null; then
    log "digi-buttons-inputd started"
  else
    log "WARN: digi-buttons-inputd still down — wire check +: sudo digivice-ensure-buttons"
  fi
}

ensure_cardkb_daemon() {
  # Start cardkb-inputd if needed. Do not run the full installer (udev trigger
  # of every input device knocks Bluetooth keyboards off the seat).
  local e
  for e in \
    /usr/local/bin/digivice-ensure-cardkb \
    "$PREFIX/session/ensure-cardkb.sh" \
    "$(dirname "$0")/ensure-cardkb.sh"
  do
    if [[ -f "$e" ]]; then
      if [[ "$(id -u)" -eq 0 ]]; then
        bash "$e" --if-needed >>"$LOG" 2>&1 || true
      else
        sudo -n bash "$e" --if-needed >>"$LOG" 2>&1 || true
      fi
      break
    fi
  done
  cardkb_ctl stop
  log "CardKB: Digivice in-process (daemon I2C paused)"
}

launch_phone() {
  if force_desktop_from_boot_flag; then
    show_desktop_chrome
    start_desktop_spi_mirror
    ensure_desktop_cursor
    log "not launching Digivice (recovery flag)"
    return 0
  fi
  # Break GB handoff loops: never let digivice-gb/retroarch keep killing Digivice
  pkill -9 -f '/usr/local/bin/digivice-gb' 2>/dev/null || true
  pkill -9 -f 'digivice-gb.sh' 2>/dev/null || true
  pkill -9 -f 'retroarch' 2>/dev/null || true
  pkill -9 -f 'mgba-sdl' 2>/dev/null || true
  pkill -9 -f 'mgba-qt' 2>/dev/null || true
  rm -f /run/digivice-gb-rom 2>/dev/null || true
  # Digivice owns SPI — stop desktop mirror first; kill any prior phone UI
  # (two writers on ST7789 = static/snow on the panel)
  stop_desktop_spi_mirror
  pkill -f "handset_app.py" 2>/dev/null || true
  sleep 0.35
  # Kill taskbar before splash / Digivice paints (Bookworm = wf-panel-pi)
  hide_desktop_chrome
  # Digivice phone UI — hide mouse (system + any leftover yellow overlay)
  hide_phone_cursor
  ensure_buttons_daemon
  ensure_cardkb_daemon
  mode_set phone
  digivice_display_env
  apply_digivice_layout
  export ESP_HANDSET_KIOSK=1
  # never carry junk SPEED/SWAP from bad full-update experiments
  unset ESP_ST7789_SPEED ESP_ST7789_SWAP ESP_ST7789_INVERT 2>/dev/null || true
  # Critical: installed tree is /opt/esp-handset/{handset_app.py,esp_handset/}
  # Without PYTHONPATH, imports fail and Digivice dies instantly (SPI stays on desktop mirror).
  export PYTHONPATH="${PREFIX}${PYTHONPATH:+:$PYTHONPATH}"
  local app="$PREFIX/handset_app.py"
  if [[ ! -f "$app" ]]; then
    log "ERROR missing $app"
    local alt
    alt="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)/esp_handset/handset_app.py"
    if [[ -f "$alt" ]]; then
      app="$alt"
      export PYTHONPATH="$(dirname "$alt")/..:${PYTHONPATH:-}"
    else
      # Live git tree
      for hit in \
        "${HOME}/esp-phone/pi_handset/esp_handset/handset_app.py" \
        /home/*/esp-phone/pi_handset/esp_handset/handset_app.py
      do
        for f in $hit; do
          if [[ -f "$f" ]]; then
            app="$f"
            export PYTHONPATH="$(dirname "$(dirname "$f")"):${PYTHONPATH:-}"
            break 2
          fi
        done
      done
    fi
  fi
  if [[ ! -f "$app" ]]; then
    log "FATAL: no handset_app.py under $PREFIX or git checkout"
    return 1
  fi
  log "starting $app DISPLAY=${DISPLAY:-} XAUTH=${XAUTHORITY:-} PYTHONPATH=$PYTHONPATH SPI=${ESP_HANDSET_SPI_BACKEND:-}"
  # Preflight: surface ImportError in the log instead of a silent exit
  if ! /usr/bin/python3 -c "import sys; sys.path.insert(0, r'$PREFIX'); import esp_handset" >>"$LOG" 2>&1; then
    log "FATAL: cannot import esp_handset — PYTHONPATH=$PYTHONPATH"
    /usr/bin/python3 -c "import sys; print(sys.path)" >>"$LOG" 2>&1 || true
    ls -la "$PREFIX" >>"$LOG" 2>&1 || true
    return 1
  fi
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
      start_desktop_spi_mirror
      ensure_desktop_cursor
      log "autostart: desktop (boot recovery flag) + SPI mirror"
      exit 0
    fi
    m="$(mode_get)"
    # Stale gb mode from a crashed handoff — never boot into GB limbo
    if [[ "$m" == "gb" ]]; then
      log "autostart: clearing stale session_mode=gb → phone"
      mode_set phone
      m=phone
      pkill -9 -f 'digivice-gb|retroarch|mgba-sdl|mgba-qt' 2>/dev/null || true
    fi
    log "autostart mode=$m"
    if [[ "$m" != "phone" ]]; then
      show_desktop_chrome
      start_desktop_spi_mirror
      ensure_desktop_cursor
      log "autostart: desktop + SPI mirror + cursor"
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
    log "leaving Digivice → desktop (SPI mirrors desktop)"
    kill_phone_ui
    sleep 0.3
    pkill -9 -f handset_app.py 2>/dev/null || true
    # Always restore HDMI after SPI-only digivice
    digivice_display_env
    for m in \
      "$PREFIX/session/digivice-layout.sh" \
      /usr/local/bin/digivice-layout
    do
      if [[ -f "$m" ]]; then
        bash "$m" --hdmi-restore >>"$LOG" 2>&1 || true
        break
      fi
    done
    show_desktop_chrome
    start_desktop_spi_mirror
    ensure_desktop_cursor
    echo "Left Digivice. SPI shows desktop mirror. Return: handset-phone"
    log "desktop ready + SPI mirror + cursor"
    ;;
  browser)
    # Home → Browser: midori/epiphany/chromium fullscreen, then Digivice again
    log "browser: hand off Digivice → light browser → return"
    mode_set desktop
    kill_phone_ui
    sleep 0.4
    pkill -9 -f handset_app.py 2>/dev/null || true
    digivice_display_env
    for m in \
      "$PREFIX/session/digivice-layout.sh" \
      /usr/local/bin/digivice-layout
    do
      if [[ -f "$m" ]]; then
        bash "$m" --hdmi-restore >>"$LOG" 2>&1 || true
        break
      fi
    done
    show_desktop_chrome
    start_desktop_spi_mirror
    ensure_desktop_cursor
    export DISPLAY="${DISPLAY:-:0}"
    BROWSER_BIN=""
    for c in midori epiphany-browser epiphany chromium-browser chromium firefox-esr firefox; do
      if command -v "$c" >/dev/null 2>&1; then
        BROWSER_BIN="$(command -v "$c")"
        break
      fi
    done
    START_URL="${ESP_HANDSET_BROWSER_URL:-https://www.google.com/}"
    if [[ -z "$BROWSER_BIN" ]]; then
      log "browser: none installed (try: sudo apt install midori)"
      # brief notify via zenity if present
      if command -v zenity >/dev/null 2>&1; then
        zenity --error --text="No browser installed.\nRun: sudo apt install midori" --timeout=5 2>/dev/null || true
      fi
    else
      log "browser: launching $BROWSER_BIN $START_URL"
      base="$(basename "$BROWSER_BIN")"
      case "$base" in
        midori)
          "$BROWSER_BIN" -e Fullscreen "$START_URL" >>"$LOG" 2>&1 || \
            "$BROWSER_BIN" "$START_URL" >>"$LOG" 2>&1
          ;;
        epiphany|epiphany-browser)
          "$BROWSER_BIN" --new-window "$START_URL" >>"$LOG" 2>&1
          ;;
        chromium|chromium-browser)
          "$BROWSER_BIN" --kiosk --noerrdialogs --disable-infobars \
            --check-for-update-interval=31536000 "$START_URL" >>"$LOG" 2>&1 || \
            "$BROWSER_BIN" --start-fullscreen "$START_URL" >>"$LOG" 2>&1
          ;;
        *)
          "$BROWSER_BIN" "$START_URL" >>"$LOG" 2>&1
          ;;
      esac
      log "browser: exited ($base)"
    fi
    # Back to Digivice
    mode_set phone
    pkill -f desktop_spi_mirror.py 2>/dev/null || true
    pkill -f desktop-spi-mirror 2>/dev/null || true
    sleep 0.3
    digivice_display_env
    apply_digivice_layout
    hide_phone_cursor 2>/dev/null || true
    if [[ -x /usr/local/bin/digivice-start ]]; then
      /usr/local/bin/digivice-start >>"$LOG" 2>&1 || launch_phone
    else
      launch_phone
    fi
    ;;
  spi-phone)
    # Digivice with SPI as sole head (HDMI off) — use when dual-head blanks SPI
    export ESP_HANDSET_SPI_ONLY=1
    launch_phone
    ;;
  spi-prove)
    digivice_display_env
    for m in \
      "$PREFIX/session/spi-prove.sh" \
      /usr/local/bin/digivice-spi-prove \
      "$(dirname "$0")/spi-prove.sh"
    do
      if [[ -f "$m" ]]; then
        bash "$m"
        exit $?
      fi
    done
    echo "spi-prove script missing"
    exit 1
    ;;
  kill|force-desktop)
    mode_set desktop
    kill_phone_ui
    pkill -9 -f handset_app.py 2>/dev/null || true
    pkill -9 -f "python3.*handset" 2>/dev/null || true
    show_desktop_chrome
    start_desktop_spi_mirror
    ensure_desktop_cursor
    echo "Force-killed Digivice. mode=desktop (SPI mirrors desktop)"
    ;;
  log)
    tail -n 80 "$LOG" 2>/dev/null || echo "(no log yet at $LOG)"
    ;;
  *)
    cat <<EOF
Usage: handset-session <command>
  phone / spi-phone / spi-prove / desktop / browser / layout / set-phone / set-desktop / mode / log

  browser   — leave Digivice, open midori/epiphany/chromium, return when closed
  spi-prove  — red on SPI (HDMI off 6s) then restore HDMI  ← run this first if SPI dark
  spi-phone  — Digivice on SPI only (HDMI off). handset-desktop restores HDMI.

Hard exit Digivice: Back×3 or handset-desktop (Home = Digivice, never desktop exit)
On desktop, Home relaunches Digivice. 2\" SPI mirrors Linux desktop when left.
EOF
    exit 1
    ;;
esac
