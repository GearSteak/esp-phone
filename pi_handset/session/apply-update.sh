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
  [[ -d "$ROOT/Assets" ]] && cp -a "$ROOT/Assets" "$PREFIX/"
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
    "ensure-cardkb.sh:digivice-ensure-cardkb" \
    "digivice-cardkb-ctl.sh:digivice-cardkb-ctl" \
    "digivice-ensure-browser.sh:digivice-ensure-browser" \
    "digivice-suppress-usb-prompt.sh:digivice-suppress-usb-prompt" \
    "digivice-ensure-jellyfin.sh:digivice-ensure-jellyfin" \
    "digivice-jellyfin-ctl.sh:digivice-jellyfin-ctl" \
    "ensure-linphone.sh:digivice-ensure-linphone" \
    "digivice-sip-sync.sh:digivice-sip-sync" \
    "ensure-libretro-cores.sh:digivice-libretro-cores" \
    "digivice-linphonecsh.sh:digivice-linphonecsh" \
    "digivice-linphonec.sh:digivice-linphonec" \
    "digivice-sip-dial.sh:digivice-sip-dial" \
    "digivice-audio-doctor.sh:digivice-audio-doctor" \
    "digivice-i2c-doctor.sh:digivice-i2c-doctor" \
    "digivice-mouse-doctor.sh:digivice-mouse-doctor" \
    "digivice-audio-usb.sh:digivice-audio-usb" \
    "digivice-audio-fix.sh:digivice-audio-fix" \
    "digivice-cm108-beep.sh:digivice-cm108-beep" \
    "digivice-cm108-wake.sh:digivice-cm108-wake" \
    "digivice-start.sh:digivice-start"
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
export DISPLAY="${DISPLAY:-:0}"
if [[ -z "${XAUTHORITY:-}" && -f "${HOME}/.Xauthority" ]]; then
  export XAUTHORITY="${HOME}/.Xauthority"
fi
export ESP_HANDSET_PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
export PYTHONPATH="${ESP_HANDSET_PREFIX}${PYTHONPATH:+:$PYTHONPATH}"
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
    ensure-linphone.sh:digivice-ensure-linphone \
    ensure-cardkb.sh:digivice-ensure-cardkb \
    digivice-cardkb-ctl.sh:digivice-cardkb-ctl \
    digivice-ensure-browser.sh:digivice-ensure-browser \
    digivice-suppress-usb-prompt.sh:digivice-suppress-usb-prompt \
    digivice-ensure-jellyfin.sh:digivice-ensure-jellyfin \
    digivice-jellyfin-ctl.sh:digivice-jellyfin-ctl \
    ensure-libretro-cores.sh:digivice-libretro-cores \
    digivice-linphonecsh.sh:digivice-linphonecsh \
    digivice-linphonec.sh:digivice-linphonec \
    digivice-sip-dial.sh:digivice-sip-dial \
    full-update.sh:digivice-full-update \
    digivice-audio-doctor.sh:digivice-audio-doctor \
    digivice-media-doctor.sh:digivice-media-doctor \
    digivice-mouse-doctor.sh:digivice-mouse-doctor \
    digivice-audio-usb.sh:digivice-audio-usb \
    digivice-audio-fix.sh:digivice-audio-fix \
    digivice-cm108-beep.sh:digivice-cm108-beep \
    digivice-cm108-wake.sh:digivice-cm108-wake \
    digivice-start.sh:digivice-start
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
export DISPLAY="${DISPLAY:-:0}"
if [[ -z "${XAUTHORITY:-}" && -f "${HOME}/.Xauthority" ]]; then
  export XAUTHORITY="${HOME}/.Xauthority"
fi
export ESP_HANDSET_PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
export PYTHONPATH="${ESP_HANDSET_PREFIX}${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/local/bin/handset-session phone
EOF
  chmod +x /usr/local/bin/handset-phone
  if [[ -f "$PREFIX/session/digivice-start.sh" ]]; then
    install -m 755 "$PREFIX/session/digivice-start.sh" /usr/local/bin/digivice-start
  fi
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

if [[ -f "$PREFIX/session/return-to-phone.desktop" ]]; then
  install -d "$USER_HOME/Desktop" "$USER_HOME/.local/share/applications" 2>/dev/null || true
  install -m 644 "$PREFIX/session/return-to-phone.desktop" \
    "$USER_HOME/Desktop/return-to-phone.desktop" 2>/dev/null || true
  install -m 644 "$PREFIX/session/return-to-phone.desktop" \
    "$USER_HOME/.local/share/applications/return-to-phone.desktop" 2>/dev/null || true
  chmod +x "$USER_HOME/Desktop/return-to-phone.desktop" 2>/dev/null || true
  chown "$USER_NAME:$USER_NAME" "$USER_HOME/Desktop/return-to-phone.desktop" \
    "$USER_HOME/.local/share/applications/return-to-phone.desktop" 2>/dev/null || true
fi
if [[ -f "$PREFIX/session/autostart-phone.desktop" ]]; then
  install -d "$USER_HOME/.config/autostart" 2>/dev/null || true
  install -m 644 "$PREFIX/session/autostart-phone.desktop" \
    "$USER_HOME/.config/autostart/esp-handset-phone.desktop" 2>/dev/null || true
  chown "$USER_NAME:$USER_NAME" \
    "$USER_HOME/.config/autostart/esp-handset-phone.desktop" 2>/dev/null || true
fi

# GUI updates used to wipe audio-fix from sudoers — restore every apply
if [[ -d /etc/sudoers.d ]]; then
  cat >/etc/sudoers.d/esp-handset-update <<EOF
# Digivice (apply-update) — Update / Power / Audio / Modem
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/true
$USER_NAME ALL=(root) NOPASSWD: /bin/true
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-update
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-full-update
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-gui-update
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-apply-update
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-power
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-set-rotation
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-ensure-buttons
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-ensure-cardkb
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-cardkb-ctl
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/systemctl stop cardkb-inputd
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/systemctl stop cardkb-inputd.service
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/systemctl start cardkb-inputd
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/systemctl start cardkb-inputd.service
$USER_NAME ALL=(root) NOPASSWD: /bin/systemctl stop cardkb-inputd
$USER_NAME ALL=(root) NOPASSWD: /bin/systemctl stop cardkb-inputd.service
$USER_NAME ALL=(root) NOPASSWD: /bin/systemctl start cardkb-inputd
$USER_NAME ALL=(root) NOPASSWD: /bin/systemctl start cardkb-inputd.service
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-ensure-browser
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-suppress-usb-prompt
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-ensure-jellyfin
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-jellyfin-ctl
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-ensure-linphone
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-libretro-cores
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-ensure-gb
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-stop-gb
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-modem-uart
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-modem-doctor
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-audio-doctor
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-audio-usb
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-audio-fix
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-cm108-wake
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/update-handset.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/full-update.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/gui-update.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/apply-update.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/power.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/ensure-buttons.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/ensure-cardkb.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/ensure-linphone.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/digivice-ensure-jellyfin.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/digivice-jellyfin-ctl.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/ensure-libretro-cores.sh
EOF
  chmod 440 /etc/sudoers.d/esp-handset-update
  log "sudoers restored (incl. jellyfin / browser)"
fi

# VoIP: Digivice Settings→Update never ran apt — install linphone here
export DEBIAN_FRONTEND=noninteractive
# Always install Digivice's stable VoIP wrappers (even if ensure script missing)
if [[ -f "$PREFIX/session/digivice-linphonecsh.sh" ]]; then
  install -m 755 "$PREFIX/session/digivice-linphonecsh.sh" /usr/local/bin/digivice-linphonecsh
fi
if [[ -f "$PREFIX/session/digivice-linphonec.sh" ]]; then
  install -m 755 "$PREFIX/session/digivice-linphonec.sh" /usr/local/bin/digivice-linphonec
fi
if [[ ! -x /usr/local/bin/digivice-linphonecsh ]]; then
  cat >/usr/local/bin/digivice-linphonecsh <<'WRAP'
#!/usr/bin/env bash
set +e
REAL=""
for hint in /etc/esp-handset/linphone.bin "${HOME}/.esp-handset/linphone.bin"; do
  [[ -f "$hint" ]] || continue
  cand="$(tr -d '[:space:]' <"$hint" 2>/dev/null || true)"
  [[ -n "$cand" && -x "$cand" ]] && REAL="$cand" && break
done
[[ -z "$REAL" && -x /usr/bin/linphonecsh ]] && REAL=/usr/bin/linphonecsh
[[ -z "$REAL" ]] && REAL="$(dpkg -L linphone-cli 2>/dev/null | grep '/linphonecsh$' | head -n1 || true)"
[[ -n "$REAL" && -e "$REAL" ]] || exit 127
exec "$REAL" "$@"
WRAP
  chmod 755 /usr/local/bin/digivice-linphonecsh
fi
# Pin path if package already present
if command -v linphonecsh >/dev/null 2>&1 || [[ -x /usr/bin/linphonecsh ]]; then
  REAL="$(command -v linphonecsh 2>/dev/null || echo /usr/bin/linphonecsh)"
  echo "$REAL" >/etc/esp-handset/linphone.bin
  echo "$REAL" >"$USER_HOME/.esp-handset/linphone.bin" 2>/dev/null || true
  chown "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset/linphone.bin" 2>/dev/null || true
fi
if command -v linphonec >/dev/null 2>&1 || [[ -e /usr/bin/linphonec ]]; then
  CREAL="$(command -v linphonec 2>/dev/null || echo /usr/bin/linphonec)"
  echo "$CREAL" >/etc/esp-handset/linphonec.bin
  echo "$CREAL" >"$USER_HOME/.esp-handset/linphonec.bin" 2>/dev/null || true
  chown "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset/linphonec.bin" 2>/dev/null || true
fi
if [[ -f "$PREFIX/session/ensure-linphone.sh" ]]; then
  install -m 755 "$PREFIX/session/ensure-linphone.sh" /usr/local/bin/digivice-ensure-linphone
  log "Ensuring linphone-cli (VoIP)…"
  SUDO_USER="$USER_NAME" DIGIVICE_USER="$USER_NAME" \
    bash /usr/local/bin/digivice-ensure-linphone >>"$LOG" 2>&1 \
    || log "WARN: digivice-ensure-linphone failed — check $LOG"
  if [[ -x /usr/local/bin/digivice-sip-sync ]]; then
    sudo -u "$USER_NAME" env HOME="$USER_HOME" ESP_HANDSET_PREFIX="$PREFIX" \
      /usr/local/bin/digivice-sip-sync >>"$LOG" 2>&1 || true
  fi
elif ! command -v linphonecsh >/dev/null 2>&1 && [[ ! -x /usr/bin/linphonecsh ]]; then
  log "Installing linphone-cli (no ensure script yet)…"
  apt-get update -qq >>"$LOG" 2>&1 || true
  apt-get install -y linphone-cli >>"$LOG" 2>&1 \
    || log "WARN: apt install linphone-cli failed"
fi

# In-Digivice Browser — WebEngine often missing on Pi OS ARM; WebKit usually works
if [[ -f "$PREFIX/session/digivice-ensure-browser.sh" ]]; then
  install -m 755 "$PREFIX/session/digivice-ensure-browser.sh" /usr/local/bin/digivice-ensure-browser
  log "Ensuring Digivice Browser (WebKit / WebEngine)…"
  bash /usr/local/bin/digivice-ensure-browser >>"$LOG" 2>&1 \
    || log "WARN: digivice-ensure-browser — check $LOG (Browser may still use WebKit after reboot)"
else
  log "Ensuring Digivice Browser deps…"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq >>"$LOG" 2>&1 || true
  apt-get install -y python3-pyqt5.qtwebkit >>"$LOG" 2>&1 || true
  apt-get install -y python3-pyqt5.qtwebengine >>"$LOG" 2>&1 || true
fi

# USB carts: keep automount, suppress "what would you like to do?" dialog
if [[ -f "$PREFIX/session/digivice-suppress-usb-prompt.sh" ]]; then
  install -m 755 "$PREFIX/session/digivice-suppress-usb-prompt.sh" \
    /usr/local/bin/digivice-suppress-usb-prompt
  log "Suppressing USB volume prompt (autorun off, mount kept)…"
  SUDO_USER="$USER_NAME" DIGI_GUI_USER="$USER_NAME" \
    bash /usr/local/bin/digivice-suppress-usb-prompt >>"$LOG" 2>&1 \
    || log "WARN: digivice-suppress-usb-prompt failed — check $LOG"
fi

# Jellyfin — Digivice Share (serve Videos/Music/cart to Fire TV)
if [[ -f "$PREFIX/session/digivice-ensure-jellyfin.sh" ]]; then
  install -m 755 "$PREFIX/session/digivice-ensure-jellyfin.sh" /usr/local/bin/digivice-ensure-jellyfin
  [[ -f "$PREFIX/session/digivice-jellyfin-ctl.sh" ]] \
    && install -m 755 "$PREFIX/session/digivice-jellyfin-ctl.sh" /usr/local/bin/digivice-jellyfin-ctl
  log "Ensuring Jellyfin (Share → Fire TV)…"
  SUDO_USER="$USER_NAME" DIGI_GUI_USER="$USER_NAME" \
    bash /usr/local/bin/digivice-ensure-jellyfin >>"$LOG" 2>&1 \
    || log "WARN: digivice-ensure-jellyfin failed — check $LOG"
fi

# In-UI NES/GB/… cores — Settings→Update never fetched these before
if [[ -f "$PREFIX/session/ensure-libretro-cores.sh" ]]; then
  install -m 755 "$PREFIX/session/ensure-libretro-cores.sh" /usr/local/bin/digivice-libretro-cores
  log "Ensuring libretro cores (NES/GB/SMS/Genesis/GBA)…"
  SUDO_USER="$USER_NAME" DIGI_GUI_USER="$USER_NAME" \
    timeout 240 bash /usr/local/bin/digivice-libretro-cores >>"$LOG" 2>&1 \
    || log "WARN: digivice-libretro-cores failed/timed out — check $LOG"
fi

# Pi headphone jack + USB dongle — mirror playback to both (ALSA tee)
if [[ -f "$PREFIX/session/digivice-analog-audio.sh" ]]; then
  install -m 755 "$PREFIX/session/digivice-analog-audio.sh" /usr/local/bin/digivice-analog-audio
  log "Dual audio (jack + USB when both plugged in)…"
  bash /usr/local/bin/digivice-analog-audio >>"$LOG" 2>&1 || true
  if [[ -x /usr/local/bin/digivice-sip-sync ]]; then
    sudo -u "$USER_NAME" env HOME="$USER_HOME" \
      /usr/local/bin/digivice-sip-sync >>"$LOG" 2>&1 || true
  fi
fi

# Sealed-case CM108: keep wake helper + boot unit after GUI apply
if [[ -f "$PREFIX/session/digivice-cm108-wake.sh" ]]; then
  install -m 755 "$PREFIX/session/digivice-cm108-wake.sh" /usr/local/bin/digivice-cm108-wake
fi
if [[ -f "$PREFIX/session/digivice-cm108-beep.sh" ]]; then
  install -m 755 "$PREFIX/session/digivice-cm108-beep.sh" /usr/local/bin/digivice-cm108-beep
fi
if [[ -f "$PREFIX/session/digivice-cm108-wake.service" ]]; then
  install -m 644 "$PREFIX/session/digivice-cm108-wake.service" \
    /etc/systemd/system/digivice-cm108-wake.service
  systemctl daemon-reload 2>/dev/null || true
  systemctl enable digivice-cm108-wake.service 2>/dev/null || true
fi
if [[ -f "$PREFIX/session/99-digivice-cmedia-nosuspend.rules" ]]; then
  install -m 644 "$PREFIX/session/99-digivice-cmedia-nosuspend.rules" \
    /etc/udev/rules.d/99-digivice-cmedia-nosuspend.rules
  udevadm control --reload-rules 2>/dev/null || true
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
