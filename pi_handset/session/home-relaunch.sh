#!/usr/bin/env bash
# Digivice Home button → return to phone UI (safe path).
#
# Called from digi-buttons-inputd (runs as root). Must NEVER start Digivice
# as root — that crashes the X session. Also avoids bash -lc, xrandr thrash,
# and overlapping launches that OOM / wedge SPI on Pi Zero 2 W.
#
#   digivice-home-relaunch
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
LOCK="${DIGI_HOME_LOCK:-/run/digivice-home-relaunch.lock}"
# Prefer user log under their home once we know the user

resolve_gui_user() {
  if [[ -n "${DIGI_GUI_USER:-}" && "${DIGI_GUI_USER}" != "root" ]]; then
    echo "$DIGI_GUI_USER"
    return 0
  fi
  # Active graphical session owner
  if command -v loginctl >/dev/null 2>&1; then
    local sid uid name
    while read -r sid; do
      [[ -z "$sid" ]] && continue
      uid="$(loginctl show-session "$sid" -p User --value 2>/dev/null || true)"
      [[ -z "$uid" || "$uid" == "0" ]] && continue
      name="$(getent passwd "$uid" | cut -d: -f1)"
      if [[ -n "$name" && "$name" != "root" ]]; then
        local t
        t="$(loginctl show-session "$sid" -p Type --value 2>/dev/null || true)"
        case "$t" in
          x11|wayland|mir|tty) echo "$name"; return 0 ;;
        esac
        echo "$name"
        return 0
      fi
    done < <(loginctl list-sessions --no-legend 2>/dev/null | awk '{print $1}')
  fi
  # Owner of .Xauthority
  local p
  for p in /home/*/.Xauthority; do
    [[ -f "$p" ]] || continue
    local u
    u="$(stat -c '%U' "$p" 2>/dev/null || true)"
    if [[ -n "$u" && "$u" != "root" ]]; then
      echo "$u"
      return 0
    fi
  done
  for u in pi isaac; do
    id "$u" >/dev/null 2>&1 && echo "$u" && return 0
  done
  echo "pi"
}

# --- privilege drop: Digivice must run as the desktop user ---
if [[ "$(id -u)" -eq 0 ]]; then
  USER_NAME="$(resolve_gui_user)"
  USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6 || echo /home/"$USER_NAME")"
  AUTH="${XAUTHORITY:-$USER_HOME/.Xauthority}"
  [[ -f "$AUTH" ]] || AUTH="$USER_HOME/.Xauthority"
  DISP="${DISPLAY:-:0}"
  mkdir -p "$USER_HOME/.esp-handset" 2>/dev/null || true
  chown "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset" 2>/dev/null || true
  echo "phone" >"$USER_HOME/.esp-handset/session_mode" 2>/dev/null || true
  echo "phone" >/etc/esp-handset/ui_mode 2>/dev/null || true
  chown "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset/session_mode" 2>/dev/null || true
  exec sudo -u "$USER_NAME" -H env \
    HOME="$USER_HOME" \
    USER="$USER_NAME" \
    LOGNAME="$USER_NAME" \
    DISPLAY="$DISP" \
    XAUTHORITY="$AUTH" \
    ESP_HANDSET_PREFIX="$PREFIX" \
    ESP_HANDSET_SKIP_LAYOUT=1 \
    ESP_HANDSET_SKIP_PIN=1 \
    ESP_HANDSET_KIOSK=1 \
    QT_QPA_PLATFORM=xcb \
    PATH="/usr/local/bin:/usr/bin:/bin" \
    bash "$0" "$@"
fi

# --- running as GUI user ---
LOG_DIR="${HOME}/.esp-handset"
mkdir -p "$LOG_DIR" 2>/dev/null || true
LOG="$LOG_DIR/home-relaunch.log"
log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

# Single-flight lock (user-writable fallback if /run not writable)
if ! exec 9>"$LOCK" 2>/dev/null; then
  LOCK="$LOG_DIR/home-relaunch.lock"
  exec 9>"$LOCK" 2>/dev/null || true
fi
if command -v flock >/dev/null 2>&1; then
  if ! flock -n 9; then
    log "HOME ignored — relaunch already in progress"
    exit 0
  fi
fi

if pgrep -f "handset_app.py" >/dev/null 2>&1; then
  log "HOME ignored — Digivice already running"
  exit 0
fi

log "HOME → Digivice (user=$(id -un) DISPLAY=${DISPLAY:-?} auth=${XAUTHORITY:-?})"

# Mode files
echo phone >"$LOG_DIR/session_mode" 2>/dev/null || true
if [[ -w /etc/esp-handset/ui_mode ]] 2>/dev/null; then
  echo phone >/etc/esp-handset/ui_mode 2>/dev/null || true
elif command -v sudo >/dev/null 2>&1; then
  echo phone | sudo -n tee /etc/esp-handset/ui_mode >/dev/null 2>&1 || true
fi

# Stop desktop SPI mirror cleanly (SIGKILL races wedge the bus on Zero 2 W)
stop_mirror() {
  local m
  for m in \
    /usr/local/bin/digivice-desktop-mirror \
    "$PREFIX/session/desktop-spi-mirror.sh" \
    /opt/esp-handset/session/desktop-spi-mirror.sh
  do
    if [[ -x "$m" ]] || [[ -f "$m" ]]; then
      bash "$m" stop >>"$LOG" 2>&1 || true
      break
    fi
  done
  # polite then firm
  pkill -TERM -f "desktop_spi_mirror.py" 2>/dev/null || true
  local i
  for i in 1 2 3 4 5 6; do
    pgrep -f "desktop_spi_mirror.py" >/dev/null 2>&1 || break
    sleep 0.25
  done
  pkill -KILL -f "desktop_spi_mirror.py" 2>/dev/null || true
  rm -f /tmp/digivice-st7789.lock /run/digivice-st7789.lock 2>/dev/null || true
  sleep 0.6
}

stop_mirror

# Skip xrandr layout surgery — thrashing outputs from Home has frozen sessions
export ESP_HANDSET_SKIP_LAYOUT=1
export ESP_HANDSET_SKIP_PIN=1
export ESP_HANDSET_KIOSK=1
export DISPLAY="${DISPLAY:-:0}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
# Prefer X11 even if a Wayland var leaked into the service env
unset WAYLAND_DISPLAY 2>/dev/null || true

# Launch Digivice (handset-session phone → exec python)
if [[ -x /usr/local/bin/handset-session ]]; then
  log "exec handset-session phone"
  exec /usr/local/bin/handset-session phone >>"$LOG" 2>&1
elif [[ -x /usr/local/bin/handset-phone ]]; then
  log "exec handset-phone"
  exec /usr/local/bin/handset-phone >>"$LOG" 2>&1
elif [[ -f "$PREFIX/session/handset-session.sh" ]]; then
  log "exec $PREFIX/session/handset-session.sh phone"
  exec bash "$PREFIX/session/handset-session.sh" phone >>"$LOG" 2>&1
fi

log "ERROR: handset-session / handset-phone missing"
exit 1
