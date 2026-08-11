#!/usr/bin/env bash
# Force a VISIBLE mouse cursor on Digivice Pi desktops.
#
#   digivice-fix-cursor              # now (X + overlay pointer)
#   sudo digivice-fix-cursor --permanent  # Xorg/labwc + force X11 preference
#   digivice-fix-cursor --overlay-only # just the yellow software pointer
#   digivice-fix-cursor --stop        # stop overlay
#
set +e
set -u
export DISPLAY="${DISPLAY:-:0}"
PERM=0
OVERLAY=1
STOP=0
for a in "$@"; do
  case "$a" in
    --permanent|-p) PERM=1 ;;
    --overlay-only) OVERLAY=1; PERM=0 ;;
    --no-overlay) OVERLAY=0 ;;
    --stop) STOP=1 ;;
  esac
done

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
LOG="${HOME:-/tmp}/.esp-handset/handset.log"
mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
log() { echo "[fix-cursor] $*" | tee -a "$LOG" 2>/dev/null; }

# Xauthority
if [[ -z "${XAUTHORITY:-}" ]]; then
  for a in "${HOME}/.Xauthority" /home/*/.Xauthority; do
    if [[ -f $a ]]; then
      export XAUTHORITY="$(ls $a 2>/dev/null | head -n1)"
      break
    fi
  done
fi

GUI_USER="${SUDO_USER:-$USER}"
[[ "$GUI_USER" == "root" ]] && GUI_USER=pi
GUI_HOME="$(getent passwd "$GUI_USER" 2>/dev/null | cut -d: -f6 || echo /home/pi)"

stop_overlay() {
  pkill -f "pointer_overlay.py" 2>/dev/null || true
  pkill -f "esp_handset/pointer_overlay" 2>/dev/null || true
  log "overlay stopped"
}

start_overlay() {
  stop_overlay
  local py=""
  for c in \
    "$PREFIX/esp_handset/pointer_overlay.py" \
    "$PREFIX/pointer_overlay.py" \
    /opt/esp-handset/esp_handset/pointer_overlay.py
  do
    [[ -f "$c" ]] && py="$c" && break
  done
  # from session tree during dev
  if [[ -z "$py" ]]; then
    local r
    r="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)/esp_handset/pointer_overlay.py"
    [[ -f "$r" ]] && py="$r"
  fi
  if [[ -z "$py" ]]; then
    log "pointer_overlay.py missing — copy via digivice-full-update"
    return 1
  fi
  export QT_QPA_PLATFORM=xcb
  export DISPLAY="${DISPLAY:-:0}"
  export PYTHONPATH="$(dirname "$py")/..:${PYTHONPATH:-}"
  if [[ -z "${XAUTHORITY:-}" ]]; then
    for a in "${HOME}/.Xauthority" /home/*/.Xauthority; do
      [[ -f $a ]] || continue
      export XAUTHORITY="$(ls $a 2>/dev/null | head -n1)"
      break
    done
  fi
  nohup /usr/bin/python3 "$py" >>"$LOG" 2>&1 &
  local pid=$!
  echo "$pid" >"${HOME}/.esp-handset/pointer_overlay.pid" 2>/dev/null || true
  sleep 0.4
  if kill -0 "$pid" 2>/dev/null; then
    log "started software pointer overlay pid=$pid ($py)"
  else
    log "ERROR: pointer overlay exited — last log:"
    tail -n 15 "$LOG" 2>/dev/null || true
    return 1
  fi
}

if [[ "$STOP" -eq 1 ]]; then
  stop_overlay
  exit 0
fi

# Kill hiders
pkill -x unclutter 2>/dev/null || true
pkill -f unclutter 2>/dev/null || true
pkill -x unclutter-xfixes 2>/dev/null || true

# Live X session cursor theme / size
export XCURSOR_SIZE="${XCURSOR_SIZE:-48}"
export XCURSOR_THEME="${XCURSOR_THEME:-Adwaita}"
if command -v xsetroot >/dev/null 2>&1; then
  xsetroot -cursor_name left_ptr 2>/dev/null || true
fi
if command -v xrdb >/dev/null 2>&1; then
  echo "Xcursor.size: 48
Xcursor.theme: Adwaita" | xrdb -merge 2>/dev/null || true
fi
if command -v gsettings >/dev/null 2>&1; then
  gsettings set org.gnome.desktop.interface cursor-size 48 2>/dev/null || true
  gsettings set org.gnome.desktop.interface cursor-theme 'Adwaita' 2>/dev/null || true
fi
if command -v xdotool >/dev/null 2>&1; then
  xdotool mousemove_relative -- 3 0 2>/dev/null
  xdotool mousemove_relative -- -3 0 2>/dev/null
fi

# Permanent system config
if [[ "$PERM" -eq 1 ]]; then
  if [[ "$(id -u)" -ne 0 ]]; then
    log "elevating for --permanent"
    exec sudo -n env DISPLAY="$DISPLAY" XAUTHORITY="${XAUTHORITY:-}" \
      HOME="$HOME" SUDO_USER="$GUI_USER" bash "$0" --permanent --no-overlay
  fi
  apt-get install -y xbitmaps x11-xserver-utils xdotool adwaita-icon-theme 2>/dev/null || true
  mkdir -p /etc/X11/xorg.conf.d
  cat >/etc/X11/xorg.conf.d/20-digivice-swcursor.conf <<'EOF'
# Digivice — software cursor (vc4 HW plane often blank after multi-head)
Section "Device"
    Identifier "Digivice modesetting"
    Driver "modesetting"
    Option "SWcursor" "true"
    Option "ShadowFB" "true"
EndSection
Section "ServerFlags"
    Option "BlankTime" "0"
    Option "StandbyTime" "0"
    Option "SuspendTime" "0"
    Option "OffTime" "0"
EndSection
EOF

  # labwc / Wayland large cursor
  for home in "$GUI_HOME" /home/pi /home/*; do
    [[ -d "$home" ]] || continue
    mkdir -p "$home/.config/labwc" "$home/.config/environment.d"
    cat >"$home/.config/labwc/environment" <<'EOF'
XCURSOR_THEME=Adwaita
XCURSOR_SIZE=48
EOF
    cat >"$home/.config/environment.d/90-digivice-cursor.conf" <<'EOF'
XCURSOR_THEME=Adwaita
XCURSOR_SIZE=48
EOF
    chown -R "$(stat -c '%U:%G' "$home" 2>/dev/null || echo pi:pi)" \
      "$home/.config/labwc" "$home/.config/environment.d" 2>/dev/null || true
  done

  # Prefer X11 session (software cursor + our overlay actually work reliably)
  if command -v raspi-config >/dev/null 2>&1; then
    # W1=Wayland W2=X11 on recent raspi-config — try both safe forms
    raspi-config nonint do_wayland W2 2>/dev/null \
      || raspi-config nonint do_wayland x11 2>/dev/null \
      || true
    log "Asked raspi-config for X11 (if available)"
  fi

  # Autostart overlay for every desktop login
  AS_DIR="$GUI_HOME/.config/autostart"
  mkdir -p "$AS_DIR"
  cat >"$AS_DIR/digivice-pointer.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Digivice pointer (visible cursor)
Comment=Software mouse arrow when HW cursor is invisible
Exec=/bin/bash -c 'sleep 2; export DISPLAY=:0; /usr/local/bin/digivice-fix-cursor --overlay-only'
X-GNOME-Autostart-enabled=true
Hidden=false
EOF
  chown -R "$GUI_USER:" "$AS_DIR" 2>/dev/null || true
  log "permanent: Xorg SWcursor + labwc XCURSOR_SIZE=48 + autostart overlay"
  log "  REBOOT once if still missing, or log out/in"
fi

if [[ "$OVERLAY" -eq 1 ]]; then
  start_overlay
fi

if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
  log "Wayland is active ($WAYLAND_DISPLAY)."
  log "  Overlay needs X11 — reboot after: sudo digivice-fix-cursor --permanent"
  log "  or: sudo raspi-config → Advanced → Wayland → X11 → reboot"
fi

log "done — yellow software pointer should track the mouse."
log "stop with: digivice-fix-cursor --stop"
