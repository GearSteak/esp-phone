#!/usr/bin/env bash
# Apply staged Digivice update AFTER the UI has exited cleanly.
# Swaps /opt/esp-handset.staging → /opt/esp-handset, then relaunches handset-phone.
#
#   digivice-apply-update
#
# Never KILL the UI by default (SPI teardown on Pi Zero 2 W hard-crashed the board).
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
STAGE="${PREFIX}.staging"
BAK="${PREFIX}.bak"
LOCK="/run/digivice-apply-update.lock"
LOG_DIR="${HOME:-/tmp}/.esp-handset"
mkdir -p "$LOG_DIR" 2>/dev/null || true
LOG="$LOG_DIR/apply-update.log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK" 2>/dev/null || exec 9>"$LOG_DIR/apply-update.lock"
  if ! flock -n 9; then
    log "apply already running — exit"
    exit 0
  fi
fi

resolve_gui_user() {
  if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    echo "$SUDO_USER"; return 0
  fi
  if [[ -n "${DIGI_GUI_USER:-}" && "${DIGI_GUI_USER}" != "root" ]]; then
    echo "$DIGI_GUI_USER"; return 0
  fi
  local p u
  for p in /home/*/.Xauthority; do
    [[ -f "$p" ]] || continue
    u="$(stat -c '%U' "$p" 2>/dev/null || true)"
    if [[ -n "$u" && "$u" != "root" ]]; then
      echo "$u"; return 0
    fi
  done
  for u in pi isaac; do
    id "$u" >/dev/null 2>&1 && echo "$u" && return 0
  done
  echo "pi"
}

log "=== digivice-apply-update ==="

# Wait for Digivice to exit on its own (UI schedules us, then quits).
for i in $(seq 1 60); do
  if ! pgrep -f "handset_app.py" >/dev/null 2>&1; then
    log "UI gone (waited ${i}×0.25s)"
    break
  fi
  sleep 0.25
done

# Soft TERM only — never KILL (that raced SPI and crashed Pi Zero)
if pgrep -f "handset_app.py" >/dev/null 2>&1; then
  log "UI still up — sending TERM (no KILL)"
  pkill -TERM -f "handset_app.py" 2>/dev/null || true
  for i in $(seq 1 20); do
    pgrep -f "handset_app.py" >/dev/null 2>&1 || break
    sleep 0.25
  done
fi
if pgrep -f "handset_app.py" >/dev/null 2>&1; then
  log "WARN: UI still running — continuing swap anyway (no KILL)"
fi

# Extra settle for SPI / framebuffer
sleep 1.0

install_live_from_repo() {
  local REPO ROOT
  REPO=""
  if [[ -n "${ESP_HANDSET_REPO:-}" && -d "${ESP_HANDSET_REPO}/pi_handset/esp_handset" ]]; then
    REPO="$ESP_HANDSET_REPO"
  elif [[ -f /etc/esp-handset/repo.path ]]; then
    REPO="$(tr -d '[:space:]' </etc/esp-handset/repo.path)"
  fi
  if [[ -z "$REPO" || ! -d "$REPO/pi_handset/esp_handset" ]]; then
    for d in "${HOME}/esp-phone" /home/*/esp-phone /opt/esp-phone; do
      if [[ -d "$d/pi_handset/esp_handset" ]]; then
        REPO="$d"
        break
      fi
    done
  fi
  [[ -n "$REPO" && -d "$REPO/pi_handset/esp_handset" ]] || return 1
  ROOT="$REPO/pi_handset"
  log "Install live from $REPO → $PREFIX"
  mkdir -p "$PREFIX" "$PREFIX/session"
  cp -a "$ROOT/esp_handset" "$PREFIX/"
  cp -a "$ROOT/session/." "$PREFIX/session/" 2>/dev/null || true
  install -m 755 "$ROOT/esp_handset/handset_app.py" "$PREFIX/handset_app.py"
  install -m 755 "$ROOT/esp_handset/buttons_inputd.py" "$PREFIX/buttons_inputd.py"
  install -m 755 "$ROOT/session/handset-session.sh" "$PREFIX/session/handset-session.sh"
  install -m 755 "$ROOT/session/handset-session.sh" /usr/local/bin/handset-session
  for pair in \
    "gui-update.sh:digivice-gui-update" \
    "update-handset.sh:digivice-update" \
    "home-relaunch.sh:digivice-home-relaunch" \
    "apply-update.sh:digivice-apply-update" \
    "full-update.sh:digivice-full-update" \
    "power.sh:digivice-power" \
    "desktop-spi-mirror.sh:digivice-desktop-mirror" \
    "ensure-buttons.sh:digivice-ensure-buttons" \
    "digivice-audio-doctor.sh:digivice-audio-doctor" \
    "digivice-audio-usb.sh:digivice-audio-usb" \
    "digivice-audio-fix.sh:digivice-audio-fix"
  do
    src="${pair%%:*}"
    dst="${pair##*:}"
    if [[ -f "$ROOT/session/$src" ]]; then
      install -m 755 "$ROOT/session/$src" "$PREFIX/session/$src"
      install -m 755 "$ROOT/session/$src" "/usr/local/bin/$dst"
    fi
  done
  cat >/usr/local/bin/handset-phone <<'EOF'
#!/bin/bash
exec /usr/local/bin/handset-session phone
EOF
  chmod +x /usr/local/bin/handset-phone
  return 0
}

if [[ "$(id -u)" -ne 0 ]]; then
  log "Elevating for apply…"
  exec sudo -n env \
    HOME="${HOME}" \
    SUDO_USER="${SUDO_USER:-$USER}" \
    USER="${USER}" \
    DISPLAY="${DISPLAY:-:0}" \
    XAUTHORITY="${XAUTHORITY:-}" \
    ESP_HANDSET_PREFIX="$PREFIX" \
    ESP_HANDSET_REPO="${ESP_HANDSET_REPO:-}" \
    PATH="/usr/local/bin:/usr/bin:/bin:$PATH" \
    bash "$0" "$@"
fi

if [[ -d "$STAGE" && -f "$STAGE/.ready" ]]; then
  log "Swapping staged tree into $PREFIX"
  rm -rf "$BAK"
  if [[ -d "$PREFIX" ]]; then
    mv "$PREFIX" "$BAK" || {
      log "mv bak failed — rsync fallback"
      rm -rf "$BAK"
    }
  fi
  if ! mv "$STAGE" "$PREFIX"; then
    log "mv stage failed — trying rsync"
    mkdir -p "$PREFIX"
    if command -v rsync >/dev/null 2>&1; then
      rsync -a --delete "$STAGE"/ "$PREFIX"/
    else
      cp -a "$STAGE"/. "$PREFIX"/
    fi
    rm -rf "$STAGE"
  fi
  rm -f "$PREFIX/.ready" 2>/dev/null || true
  if [[ -f "$PREFIX/session/handset-session.sh" ]]; then
    install -m 755 "$PREFIX/session/handset-session.sh" /usr/local/bin/handset-session
  fi
  for pair in \
    gui-update.sh:digivice-gui-update \
    update-handset.sh:digivice-update \
    home-relaunch.sh:digivice-home-relaunch \
    apply-update.sh:digivice-apply-update \
    digivice-gb.sh:digivice-gb \
    digivice-stop-gb.sh:digivice-stop-gb \
    ensure-gb-wrappers.sh:digivice-ensure-gb \
    full-update.sh:digivice-full-update \
    digivice-audio-doctor.sh:digivice-audio-doctor \
    digivice-audio-usb.sh:digivice-audio-usb \
    digivice-audio-fix.sh:digivice-audio-fix
  do
    src="${pair%%:*}"
    dst="${pair##*:}"
    if [[ -f "$PREFIX/session/$src" ]]; then
      install -m 755 "$PREFIX/session/$src" "/usr/local/bin/$dst"
    fi
  done
  # Force stop-gb + SPI cleanup every apply (even if old staging missed the file)
  if [[ -f "$PREFIX/session/ensure-gb-wrappers.sh" ]]; then
    bash "$PREFIX/session/ensure-gb-wrappers.sh" >>"$LOG" 2>&1 || true
  elif [[ -f /usr/local/bin/digivice-ensure-gb ]]; then
    bash /usr/local/bin/digivice-ensure-gb >>"$LOG" 2>&1 || true
  else
    # Last resort: install stop-gb from any known path
    for s in \
      "$PREFIX/session/digivice-stop-gb.sh" \
      /opt/esp-handset/session/digivice-stop-gb.sh \
      /home/*/esp-phone/pi_handset/session/digivice-stop-gb.sh
    do
      # shellcheck disable=SC2086
      for hit in $s; do
        if [[ -f "$hit" ]]; then
          install -m 755 "$hit" /usr/local/bin/digivice-stop-gb
          break 2
        fi
      done
    done
  fi
  log "digivice-stop-gb → $(command -v digivice-stop-gb 2>/dev/null || echo MISSING)"
  cat >/usr/local/bin/handset-phone <<'EOF'
#!/bin/bash
exec /usr/local/bin/handset-session phone
EOF
  chmod +x /usr/local/bin/handset-phone
  log "Swap OK"
else
  log "No staging dir — install from repo while UI is down"
  install_live_from_repo || {
    log "ERROR: nothing to apply"
    exit 1
  }
fi

if [[ ! -f "$PREFIX/handset_app.py" && ! -f "$PREFIX/esp_handset/handset_app.py" ]]; then
  log "ERROR: handset_app missing after apply"
  if [[ -d "$BAK" ]]; then
    log "Restoring $BAK"
    rm -rf "$PREFIX"
    mv "$BAK" "$PREFIX"
  fi
  exit 4
fi

echo "ok $(date -Iseconds)" >"$LOG_DIR/last_update" 2>/dev/null || true
echo "ok $(date -Iseconds)" >/etc/esp-handset/last_update 2>/dev/null || true

# Relaunch like typing handset-phone in a terminal (NOT home-relaunch — that path crashed)
USER_NAME="$(resolve_gui_user)"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6 || echo /home/"$USER_NAME")"

# GUI updates used to wipe audio-fix from sudoers — restore every apply
if [[ -d /etc/sudoers.d ]]; then
  cat >/etc/sudoers.d/esp-handset-update <<EOF
# Digivice (apply-update) — Update / Power / Audio / Modem
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-update
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-full-update
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-gui-update
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-apply-update
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-power
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-ensure-buttons
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-ensure-gb
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-stop-gb
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-modem-uart
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-modem-doctor
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-audio-doctor
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-audio-usb
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-audio-fix
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/update-handset.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/full-update.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/gui-update.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/apply-update.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/power.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/ensure-buttons.sh
EOF
  chmod 440 /etc/sudoers.d/esp-handset-update
  log "sudoers restored (incl. digivice-audio-fix)"
fi

AUTH="${XAUTHORITY:-$USER_HOME/.Xauthority}"
[[ -f "$AUTH" ]] || AUTH="$USER_HOME/.Xauthority"
DISP="${DISPLAY:-:0}"
mkdir -p "$USER_HOME/.esp-handset" 2>/dev/null || true
echo phone >"$USER_HOME/.esp-handset/session_mode" 2>/dev/null || true
echo phone >/etc/esp-handset/ui_mode 2>/dev/null || true
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset" \
  "$USER_HOME/.esp-handset/session_mode" 2>/dev/null || true

log "Relaunch: sudo -u $USER_NAME handset-phone  DISPLAY=$DISP"
sleep 0.8
# Detach fully so this script can exit
nohup sudo -u "$USER_NAME" -H env \
  DISPLAY="$DISP" \
  XAUTHORITY="$AUTH" \
  HOME="$USER_HOME" \
  USER="$USER_NAME" \
  LOGNAME="$USER_NAME" \
  ESP_HANDSET_SKIP_LAYOUT=1 \
  ESP_HANDSET_SKIP_PIN=1 \
  PATH="/usr/local/bin:/usr/bin:/bin" \
  bash -c 'nohup handset-phone >>"$HOME/.esp-handset/handset.log" 2>&1 </dev/null &' \
  >/dev/null 2>&1 || \
nohup env DISPLAY="$DISP" XAUTHORITY="$AUTH" HOME="$USER_HOME" \
  ESP_HANDSET_SKIP_LAYOUT=1 \
  handset-phone >>"$USER_HOME/.esp-handset/handset.log" 2>&1 </dev/null &

log "Relaunch scheduled"
exit 0
