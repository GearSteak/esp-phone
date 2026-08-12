#!/usr/bin/env bash
# Digivice Home button → return to phone UI (minimal, isolated).
#
# Started by digivice-home-request.service (NOT as a child of the GPIO
# daemon). Spawning Qt from digi-buttons-inputd was freezing / crashing
# Pi Zero 2 W (SPI fight + same cgroup OOM).
#
#   digivice-home-relaunch
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
REQ=/run/digivice-home-request
LOCK="${DIGI_HOME_LOCK:-/run/digivice-home-relaunch.lock}"

# Clear request so the next Home press can recreate / retrigger the path unit
rm -f "$REQ" 2>/dev/null || true

resolve_gui_user() {
  if [[ -n "${DIGI_GUI_USER:-}" && "${DIGI_GUI_USER}" != "root" ]]; then
    echo "$DIGI_GUI_USER"
    return 0
  fi
  if command -v loginctl >/dev/null 2>&1; then
    local sid uid name
    while read -r sid; do
      [[ -z "$sid" ]] && continue
      uid="$(loginctl show-session "$sid" -p User --value 2>/dev/null || true)"
      [[ -z "$uid" || "$uid" == "0" ]] && continue
      name="$(getent passwd "$uid" | cut -d: -f1)"
      if [[ -n "$name" && "$name" != "root" ]]; then
        echo "$name"
        return 0
      fi
    done < <(loginctl list-sessions --no-legend 2>/dev/null | awk '{print $1}')
  fi
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

mem_available_kb() {
  awk '/MemAvailable:/ {print $2; exit}' /proc/meminfo 2>/dev/null || echo 0
}

# --- privilege drop ---
if [[ "$(id -u)" -eq 0 ]]; then
  USER_NAME="$(resolve_gui_user)"
  USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6 || echo /home/"$USER_NAME")"
  AUTH="${XAUTHORITY:-$USER_HOME/.Xauthority}"
  [[ -f "$AUTH" ]] || AUTH="$USER_HOME/.Xauthority"
  DISP="${DISPLAY:-:0}"
  mkdir -p "$USER_HOME/.esp-handset" /etc/esp-handset 2>/dev/null || true
  chown "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset" 2>/dev/null || true
  echo phone >"$USER_HOME/.esp-handset/session_mode" 2>/dev/null || true
  echo phone >/etc/esp-handset/ui_mode 2>/dev/null || true
  chown "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset/session_mode" 2>/dev/null || true

  # Stop SPI mirror as root (may need to signal processes) BEFORE user Qt starts
  for m in \
    /usr/local/bin/digivice-desktop-mirror \
    "$PREFIX/session/desktop-spi-mirror.sh"
  do
    if [[ -f "$m" ]]; then
      bash "$m" stop >/dev/null 2>&1 || true
      break
    fi
  done
  pkill -TERM -f "desktop_spi_mirror.py" 2>/dev/null || true
  sleep 0.8
  pkill -KILL -f "desktop_spi_mirror.py" 2>/dev/null || true
  rm -f /tmp/digivice-st7789.lock /run/digivice-st7789.lock 2>/dev/null || true
  # Let the SPI / DRM stack settle — rushing this wedged Zero 2 W
  sleep 1.5

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
    ESP_HANDSET_MINIMAL_LAUNCH=1 \
    QT_QPA_PLATFORM=xcb \
    PATH="/usr/local/bin:/usr/bin:/bin" \
    bash "$0" "$@"
fi

# --- GUI user ---
LOG_DIR="${HOME}/.esp-handset"
mkdir -p "$LOG_DIR" 2>/dev/null || true
LOG="$LOG_DIR/home-relaunch.log"
log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

if ! exec 9>"$LOCK" 2>/dev/null; then
  LOCK="$LOG_DIR/home-relaunch.lock"
  exec 9>"$LOCK" 2>/dev/null || true
fi
if command -v flock >/dev/null 2>&1; then
  if ! flock -n 9; then
    log "HOME ignored — already in progress"
    exit 0
  fi
fi

if pgrep -f "handset_app.py" >/dev/null 2>&1; then
  log "HOME ignored — Digivice already running"
  exit 0
fi

AVAIL="$(mem_available_kb)"
log "HOME → Digivice minimal (user=$(id -un) DISPLAY=${DISPLAY:-?} mem_avail_kb=$AVAIL)"
if [[ "${AVAIL:-0}" -gt 0 && "${AVAIL}" -lt 70000 ]]; then
  log "WARN: very low memory (${AVAIL} kB) — Digivice may OOM; continuing anyway"
fi

echo phone >"$LOG_DIR/session_mode" 2>/dev/null || true

export ESP_HANDSET_SKIP_LAYOUT=1
export ESP_HANDSET_SKIP_PIN=1
export ESP_HANDSET_KIOSK=1
export ESP_HANDSET_MINIMAL_LAUNCH=1
export DISPLAY="${DISPLAY:-:0}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
unset WAYLAND_DISPLAY 2>/dev/null || true
unset ESP_ST7789_SPEED ESP_ST7789_SWAP ESP_ST7789_INVERT 2>/dev/null || true

# Extra settle after mirror stop (root phase already waited)
sleep 0.5

APP=""
for c in \
  "$PREFIX/handset_app.py" \
  /opt/esp-handset/handset_app.py
do
  if [[ -f "$c" ]]; then
    APP="$c"
    break
  fi
done

if [[ -z "$APP" ]]; then
  log "ERROR: handset_app.py missing under $PREFIX"
  exit 1
fi

# Minimal launch: do NOT call handset-session phone (ensure-buttons / layout /
# cursor helpers are too heavy and racy from the Home button path).

log "exec python3 $APP (PYTHONPATH=$PREFIX)"
export PYTHONPATH="${PREFIX}:${PYTHONPATH:-}"
# nice: don't starve X
if command -v ionice >/dev/null 2>&1; then
  exec ionice -c 3 nice -n 5 /usr/bin/python3 "$APP" >>"$LOG" 2>&1
fi
exec nice -n 5 /usr/bin/python3 "$APP" >>"$LOG" 2>&1
