#!/usr/bin/env bash
# Hard-start Digivice — clears recovery/desktop mode and launches phone UI.
# Use when Return-to-Phone / autostart appear to do nothing.
#
#   digivice-start
#   sudo digivice-start   # ok; drops to desktop user
set +e

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
USER_NAME="${SUDO_USER:-$USER}"
if [[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
  USER_NAME="$SUDO_USER"
fi
# Prefer a real desktop user over root when launched oddly
if [[ "$USER_NAME" == "root" || -z "$USER_NAME" ]]; then
  for u in gearsteak pi isaac; do
    if id "$u" >/dev/null 2>&1; then
      USER_NAME="$u"
      break
    fi
  done
fi
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
[[ -n "$USER_HOME" ]] || USER_HOME="/home/$USER_NAME"

LOG_DIR="$USER_HOME/.esp-handset"
mkdir -p "$LOG_DIR" /etc/esp-handset
LOG="$LOG_DIR/handset.log"

log() { echo "[$(date '+%H:%M:%S')] digivice-start: $*" | tee -a "$LOG"; }

# Clear boot recovery flag that forces desktop forever
for f in \
  /boot/firmware/digivice-desktop \
  /boot/digivice-desktop \
  /boot/firmware/DIGIVICE-DESKTOP \
  /boot/DIGIVICE-DESKTOP
do
  if [[ -f "$f" ]]; then
    if [[ "$(id -u)" -eq 0 ]]; then
      rm -f "$f" 2>/dev/null || true
    else
      sudo -n rm -f "$f" 2>/dev/null || true
    fi
    log "removed boot flag $f"
  fi
done

mkdir -p "$USER_HOME/.esp-handset"
echo phone >"$USER_HOME/.esp-handset/session_mode"
if [[ "$(id -u)" -eq 0 ]]; then
  echo phone >/etc/esp-handset/ui_mode 2>/dev/null || true
else
  echo phone | sudo -n tee /etc/esp-handset/ui_mode >/dev/null 2>&1 || true
fi
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset/session_mode" 2>/dev/null || true

# Digivice owns SPI — kill desktop mirror + any prior UI
pkill -9 -f desktop_spi_mirror.py 2>/dev/null || true
pkill -9 -f handset_app.py 2>/dev/null || true
rm -f /tmp/digivice-st7789.lock /run/digivice-st7789.lock 2>/dev/null || true
sleep 0.5

export DISPLAY="${DISPLAY:-:0}"
if [[ -z "${XAUTHORITY:-}" ]]; then
  if [[ -f "$USER_HOME/.Xauthority" ]]; then
    export XAUTHORITY="$USER_HOME/.Xauthority"
  fi
fi
export HOME="$USER_HOME"
export USER="$USER_NAME"
export ESP_HANDSET_KIOSK=1
export ESP_HANDSET_SKIP_PIN=1
export ESP_HANDSET_PREFIX="$PREFIX"
export PYTHONPATH="${PREFIX}${PYTHONPATH:+:$PYTHONPATH}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
if [[ -f /etc/esp-handset/env ]]; then
  set -a
  # shellcheck source=/dev/null
  source /etc/esp-handset/env 2>/dev/null || true
  set +a
  # Re-assert after env (env must not drop PYTHONPATH)
  export PYTHONPATH="${PREFIX}${PYTHONPATH:+:$PYTHONPATH}"
fi

log "DISPLAY=$DISPLAY XAUTHORITY=${XAUTHORITY:-none} user=$USER_NAME PREFIX=$PREFIX"
log "PYTHONPATH=$PYTHONPATH"

# Prove package import before launching (this was the silent killer).
if [[ "$(id -u)" -eq 0 ]]; then
  sudo -u "$USER_NAME" -H env \
    HOME="$USER_HOME" \
    PYTHONPATH="$PREFIX" \
    /usr/bin/python3 -c "import esp_handset; print('esp_handset OK', esp_handset.__file__)" \
    >>"$LOG" 2>&1
  preflight_rc=$?
else
  env HOME="$USER_HOME" PYTHONPATH="$PREFIX" \
    /usr/bin/python3 -c "import esp_handset; print('esp_handset OK', esp_handset.__file__)" \
    >>"$LOG" 2>&1
  preflight_rc=$?
fi
if [[ "$preflight_rc" -ne 0 ]]; then
  log "FATAL: python cannot import esp_handset from $PREFIX"
  ls -la "$PREFIX" >>"$LOG" 2>&1 || true
  ls -la "$PREFIX/esp_handset" >>"$LOG" 2>&1 || true
  tail -20 "$LOG"
  exit 1
fi

PHONE=/usr/local/bin/handset-phone
[[ -x "$PHONE" ]] || PHONE=handset-phone

log "launching $PHONE…"

run_as_user() {
  sudo -u "$USER_NAME" -H env \
    DISPLAY="$DISPLAY" \
    XAUTHORITY="${XAUTHORITY:-$USER_HOME/.Xauthority}" \
    HOME="$USER_HOME" \
    USER="$USER_NAME" \
    ESP_HANDSET_KIOSK=1 \
    ESP_HANDSET_SKIP_PIN=1 \
    ESP_HANDSET_PREFIX="$PREFIX" \
    PYTHONPATH="$PREFIX" \
    QT_QPA_PLATFORM=xcb \
    PATH="/usr/local/bin:/usr/bin:/bin:$PATH" \
    "$@"
}

if [[ "$(id -u)" -eq 0 ]]; then
  run_as_user bash -c "nohup $PHONE >>\"\$HOME/.esp-handset/handset.log\" 2>&1 & echo started pid=\$!"
else
  nohup env \
    DISPLAY="$DISPLAY" \
    XAUTHORITY="${XAUTHORITY:-$USER_HOME/.Xauthority}" \
    HOME="$USER_HOME" \
    ESP_HANDSET_KIOSK=1 \
    ESP_HANDSET_SKIP_PIN=1 \
    ESP_HANDSET_PREFIX="$PREFIX" \
    PYTHONPATH="$PREFIX" \
    QT_QPA_PLATFORM=xcb \
    "$PHONE" >>"$LOG" 2>&1 &
  echo "started pid=$!"
fi

# Import + Qt can take a few seconds on Pi Zero 2 W
ok=0
for i in 1 2 3 4 5 6 7 8; do
  sleep 1
  if pgrep -f handset_app.py >/dev/null 2>&1; then
    ok=1
    break
  fi
done

if [[ "$ok" -eq 1 ]]; then
  log "OK: handset_app.py is running"
  pgrep -af handset_app.py | tee -a "$LOG"
  exit 0
fi

log "FAIL: handset_app.py not running — last log lines:"
tail -60 "$LOG" | tee -a /dev/stderr
exit 1
