#!/usr/bin/env bash
# Apply a staged Digivice software update AFTER the UI has exited.
# Swaps /opt/esp-handset.staging → /opt/esp-handset, then safe relaunch.
#
#   digivice-apply-update
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

log "=== digivice-apply-update ==="

# Wait for Digivice UI to exit (caller should quit first)
for i in $(seq 1 40); do
  if ! pgrep -f "handset_app.py" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done
if pgrep -f "handset_app.py" >/dev/null 2>&1; then
  log "UI still up — TERM"
  pkill -TERM -f "handset_app.py" 2>/dev/null || true
  sleep 1
fi
if pgrep -f "handset_app.py" >/dev/null 2>&1; then
  log "UI still up — KILL"
  pkill -KILL -f "handset_app.py" 2>/dev/null || true
  sleep 0.5
fi

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
    "ensure-buttons.sh:digivice-ensure-buttons"
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
  # Refresh critical /usr/local wrappers from new tree
  if [[ -f "$PREFIX/session/handset-session.sh" ]]; then
    install -m 755 "$PREFIX/session/handset-session.sh" /usr/local/bin/handset-session
  fi
  for pair in \
    gui-update.sh:digivice-gui-update \
    update-handset.sh:digivice-update \
    home-relaunch.sh:digivice-home-relaunch \
    apply-update.sh:digivice-apply-update \
    full-update.sh:digivice-full-update
  do
    src="${pair%%:*}"
    dst="${pair##*:}"
    if [[ -f "$PREFIX/session/$src" ]]; then
      install -m 755 "$PREFIX/session/$src" "/usr/local/bin/$dst"
    fi
  done
  cat >/usr/local/bin/handset-phone <<'EOF'
#!/bin/bash
exec /usr/local/bin/handset-session phone
EOF
  chmod +x /usr/local/bin/handset-phone
  log "Swap OK"
elif [[ "$(id -u)" -eq 0 ]]; then
  log "No staging dir — install from repo while UI is down"
  install_live_from_repo || {
    log "ERROR: nothing to apply"
    exit 1
  }
else
  # Elevate for install/swap
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

# Sanity
if [[ ! -f "$PREFIX/handset_app.py" && ! -f "$PREFIX/esp_handset/handset_app.py" ]]; then
  log "ERROR: handset_app missing after apply"
  # Try restore bak
  if [[ -d "$BAK" ]]; then
    log "Restoring $BAK"
    rm -rf "$PREFIX"
    mv "$BAK" "$PREFIX"
  fi
  exit 4
fi

echo "ok $(date -Iseconds)" >"$LOG_DIR/last_update" 2>/dev/null || true
echo "ok $(date -Iseconds)" >/etc/esp-handset/last_update 2>/dev/null || true

log "Relaunch Digivice…"
export ESP_HANDSET_SKIP_LAYOUT=1
export ESP_HANDSET_SKIP_PIN=1
if [[ -x /usr/local/bin/digivice-home-relaunch ]]; then
  exec /usr/local/bin/digivice-home-relaunch
elif [[ -f "$PREFIX/session/home-relaunch.sh" ]]; then
  exec bash "$PREFIX/session/home-relaunch.sh"
elif [[ -x /usr/local/bin/handset-phone ]]; then
  exec /usr/local/bin/handset-phone
fi
log "ERROR: no relaunch helper"
exit 1
