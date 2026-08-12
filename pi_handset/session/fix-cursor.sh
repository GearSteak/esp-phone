#!/usr/bin/env bash
# Digivice desktop cursor helper.
#
# Default: restore the *system* cursor only (no yellow overlay).
# The yellow overlay was a fallback when HW cursor vanished — it caused
# double-cursors once the black system cursor returned.
#
#   digivice-fix-cursor                 # system cursor on, kill yellow overlay
#   digivice-fix-cursor --hide           # blank cursor (Digivice phone UI)
#   digivice-fix-cursor --stop           # kill yellow overlay only
#   digivice-fix-cursor --overlay-only   # opt-in yellow fallback (usually don't)
#   sudo digivice-fix-cursor --permanent
#
set +e
set -u
export DISPLAY="${DISPLAY:-:0}"
PERM=0
OVERLAY=0
STOP=0
HIDE=0
for a in "$@"; do
  case "$a" in
    --permanent|-p) PERM=1 ;;
    --overlay-only|--force-overlay) OVERLAY=1 ;;
    --no-overlay) OVERLAY=0 ;;
    --stop) STOP=1 ;;
    --hide) HIDE=1 ;;
  esac
done

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
LOG="${HOME:-/tmp}/.esp-handset/handset.log"
mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
log() { echo "[fix-cursor] $*" | tee -a "$LOG" 2>/dev/null; }

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
  rm -f "${HOME}/.esp-handset/pointer_overlay.pid" 2>/dev/null || true
  log "yellow overlay stopped"
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
  if [[ -z "$py" ]]; then
    local r
    r="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)/esp_handset/pointer_overlay.py"
    [[ -f "$r" ]] && py="$r"
  fi
  if [[ -z "$py" ]]; then
    log "pointer_overlay.py missing"
    return 1
  fi
  export QT_QPA_PLATFORM=xcb
  export DISPLAY="${DISPLAY:-:0}"
  export PYTHONPATH="$(dirname "$py")/..:${PYTHONPATH:-}"
  nohup /usr/bin/python3 "$py" >>"$LOG" 2>&1 &
  log "started yellow overlay pid=$! (opt-in fallback)"
}

show_system_cursor() {
  export XCURSOR_SIZE="${XCURSOR_SIZE:-32}"
  export XCURSOR_THEME="${XCURSOR_THEME:-Adwaita}"
  pkill -x unclutter 2>/dev/null || true
  pkill -f unclutter 2>/dev/null || true
  pkill -x unclutter-xfixes 2>/dev/null || true
  if command -v xsetroot >/dev/null 2>&1; then
    xsetroot -cursor_name left_ptr 2>/dev/null \
      || xsetroot -cursor_name arrow 2>/dev/null || true
  fi
  if command -v xrdb >/dev/null 2>&1; then
    echo "Xcursor.size: 32
Xcursor.theme: Adwaita" | xrdb -merge 2>/dev/null || true
  fi
  if command -v gsettings >/dev/null 2>&1; then
    gsettings set org.gnome.desktop.interface cursor-size 32 2>/dev/null || true
    gsettings set org.gnome.desktop.interface cursor-theme 'Adwaita' 2>/dev/null || true
  fi
  if command -v xdotool >/dev/null 2>&1; then
    xdotool mousemove_relative -- 1 0 2>/dev/null
    xdotool mousemove_relative -- -1 0 2>/dev/null
  fi
  log "system cursor restored (left_ptr)"
}

hide_system_cursor() {
  # Digivice phone UI — no mouse pointer on screen
  stop_overlay
  # Invisible 1x1 cursor via xsetroot if available
  if command -v xsetroot >/dev/null 2>&1; then
    # empty bitmap cursor
    local empty=/tmp/digivice-empty-cursor.xbm
    cat >"$empty" <<'EOF'
#define empty_width 1
#define empty_height 1
static unsigned char empty_bits[] = { 0x00 };
EOF
    xsetroot -cursor "$empty" "$empty" 2>/dev/null || true
  fi
  # unclutter hides after idle; -idle 0 hides immediately on some builds
  if command -v unclutter >/dev/null 2>&1; then
    pkill -x unclutter 2>/dev/null || true
    nohup unclutter -idle 0 -root >/dev/null 2>&1 &
  elif command -v unclutter-xfixes >/dev/null 2>&1; then
    pkill -f unclutter-xfixes 2>/dev/null || true
    nohup unclutter-xfixes --timeout 0 --jitter 0 >/dev/null 2>&1 &
  fi
  log "system cursor hidden (phone UI)"
}

if [[ "$STOP" -eq 1 ]]; then
  stop_overlay
  exit 0
fi

if [[ "$HIDE" -eq 1 ]]; then
  hide_system_cursor
  exit 0
fi

# Kill yellow overlay first — system black cursor is the one we want
stop_overlay
pkill -x unclutter 2>/dev/null || true
pkill -f unclutter 2>/dev/null || true
pkill -x unclutter-xfixes 2>/dev/null || true

show_system_cursor

if [[ "$PERM" -eq 1 ]]; then
  if [[ "$(id -u)" -ne 0 ]]; then
    log "elevating for --permanent"
    exec sudo -n env DISPLAY="$DISPLAY" XAUTHORITY="${XAUTHORITY:-}" \
      HOME="$HOME" SUDO_USER="$GUI_USER" bash "$0" --permanent --no-overlay
  fi
  apt-get install -y xbitmaps x11-xserver-utils xdotool adwaita-icon-theme 2>/dev/null || true
  mkdir -p /etc/X11/xorg.conf.d
  cat >/etc/X11/xorg.conf.d/20-digivice-swcursor.conf <<'EOF'
# Digivice — software cursor plane (helps when HW cursor blank)
Section "Device"
    Identifier "Digivice modesetting"
    Driver "modesetting"
    Option "SWcursor" "true"
    Option "ShadowFB" "true"
EndSection
EOF

  for home in "$GUI_HOME" /home/pi /home/*; do
    [[ -d "$home" ]] || continue
    mkdir -p "$home/.config/labwc" "$home/.config/environment.d" "$home/.config/autostart"
    cat >"$home/.config/labwc/environment" <<'EOF'
XCURSOR_THEME=Adwaita
XCURSOR_SIZE=32
EOF
    cat >"$home/.config/environment.d/90-digivice-cursor.conf" <<'EOF'
XCURSOR_THEME=Adwaita
XCURSOR_SIZE=32
EOF
    # Remove old yellow-overlay autostart (caused double cursor)
    rm -f "$home/.config/autostart/digivice-pointer.desktop" 2>/dev/null || true
    chown -R "$(stat -c '%U:%G' "$home" 2>/dev/null || echo pi:pi)" \
      "$home/.config/labwc" "$home/.config/environment.d" "$home/.config/autostart" 2>/dev/null || true
  done
  log "permanent: SWcursor + removed yellow overlay autostart"
fi

if [[ "$OVERLAY" -eq 1 ]]; then
  start_overlay
  log "yellow overlay ON (fallback only)"
else
  log "done — system cursor only (no yellow overlay)"
fi
