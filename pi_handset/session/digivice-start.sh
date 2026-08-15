#!/usr/bin/env bash
# Hard-start Digivice — clears recovery/desktop mode and launches phone UI.
# Use when Return-to-Phone / autostart appear to do nothing.
#
#   digivice-start
#   sudo digivice-start   # ok; drops to desktop user
set +e

USER_NAME="${SUDO_USER:-$USER}"
if [[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
  USER_NAME="$SUDO_USER"
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
    rm -f "$f" 2>/dev/null || true
    log "removed boot flag $f"
  fi
done

echo phone >"$USER_HOME/.esp-handset/session_mode"
echo phone >/etc/esp-handset/ui_mode 2>/dev/null || true
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset/session_mode" 2>/dev/null || true

pkill -9 -f desktop_spi_mirror.py 2>/dev/null || true
pkill -9 -f handset_app.py 2>/dev/null || true
rm -f /tmp/digivice-st7789.lock /run/digivice-st7789.lock 2>/dev/null || true
sleep 0.4

export DISPLAY="${DISPLAY:-:0}"
if [[ -z "${XAUTHORITY:-}" ]]; then
  if [[ -f "$USER_HOME/.Xauthority" ]]; then
    export XAUTHORITY="$USER_HOME/.Xauthority"
  fi
fi
export HOME="$USER_HOME"
export ESP_HANDSET_KIOSK=1
export ESP_HANDSET_SKIP_PIN=1
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"

log "DISPLAY=$DISPLAY XAUTHORITY=${XAUTHORITY:-none} user=$USER_NAME"
log "launching handset-phone…"

PHONE=/usr/local/bin/handset-phone
[[ -x "$PHONE" ]] || PHONE=handset-phone

if [[ "$(id -u)" -eq 0 ]]; then
  # Never run Qt Digivice as root
  exec sudo -u "$USER_NAME" -H env \
    DISPLAY="$DISPLAY" \
    XAUTHORITY="${XAUTHORITY:-$USER_HOME/.Xauthority}" \
    HOME="$USER_HOME" \
    ESP_HANDSET_KIOSK=1 \
    ESP_HANDSET_SKIP_PIN=1 \
    QT_QPA_PLATFORM=xcb \
    PATH="/usr/local/bin:/usr/bin:/bin:$PATH" \
    bash -c "nohup $PHONE >>\"\$HOME/.esp-handset/handset.log\" 2>&1 & echo started pid=\$!"
fi

nohup "$PHONE" >>"$LOG" 2>&1 &
echo "started pid=$!"
sleep 1
if pgrep -f handset_app.py >/dev/null 2>&1; then
  log "OK: handset_app.py is running"
  pgrep -af handset_app.py | tee -a "$LOG"
else
  log "FAIL: handset_app.py not running — last log lines:"
  tail -40 "$LOG" | tee -a /dev/stderr
  exit 1
fi
exit 0
