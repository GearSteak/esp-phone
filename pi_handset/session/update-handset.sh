#!/usr/bin/env bash
# Digivice software update: git pull + install UI/scripts (skips display install by default).
#
#   digivice-update              # pull + install into /opt/esp-handset
#   digivice-update --check      # print local/remote revs only
#   digivice-update --restart    # after install, relaunch Digivice UI
#   digivice-update --full       # also re-run install-display (can undo userspace SPI)
#
# Env:
#   ESP_HANDSET_REPO   repo path (default: discover or clone)
#   ESP_HANDSET_GIT_URL  https://github.com/GearSteak/esp-phone.git
#   ESP_HANDSET_PREFIX /opt/esp-handset
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
GIT_URL="${ESP_HANDSET_GIT_URL:-https://github.com/GearSteak/esp-phone.git}"
BRANCH="${ESP_HANDSET_BRANCH:-main}"
LOG_DIR="${HOME:-/tmp}/.esp-handset"
LOG="${LOG_DIR}/update.log"
CHECK_ONLY=0
RESTART=0
FULL=0

for a in "$@"; do
  case "$a" in
    --check) CHECK_ONLY=1 ;;
    --restart) RESTART=1 ;;
    --full) FULL=1 ;;
    -h|--help)
      sed -n '2,16p' "$0"
      exit 0
      ;;
  esac
done

mkdir -p "$LOG_DIR" 2>/dev/null || true
log() {
  echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG" 2>/dev/null || echo "[update] $*"
}

real_user() {
  if [[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    echo "$SUDO_USER"
  else
    echo "${USER:-pi}"
  fi
}

real_home() {
  local u
  u="$(real_user)"
  getent passwd "$u" 2>/dev/null | cut -d: -f6 || echo "/home/$u"
}

as_user() {
  # Run git as the handset user so the checkout stays owned correctly
  if [[ "$(id -u)" -eq 0 ]]; then
    local u
    u="$(real_user)"
    if [[ "$u" != "root" ]] && id "$u" >/dev/null 2>&1; then
      sudo -u "$u" env HOME="$(real_home)" "$@"
      return $?
    fi
  fi
  "$@"
}

find_repo() {
  if [[ -n "${ESP_HANDSET_REPO:-}" ]]; then
    if [[ -d "${ESP_HANDSET_REPO}/.git" ]] || [[ -d "${ESP_HANDSET_REPO}/pi_handset" ]]; then
      echo "$ESP_HANDSET_REPO"
      return 0
    fi
  fi
  local p
  for p in /etc/esp-handset/repo.path "$(real_home)/.esp-handset/repo.path"; do
    if [[ -f "$p" ]]; then
      local r
      r="$(tr -d '[:space:]' <"$p" | sed 's|^file://||')"
      if [[ -n "$r" && ( -d "$r/.git" || -d "$r/pi_handset" ) ]]; then
        echo "$r"
        return 0
      fi
    fi
  done
  local d
  for d in \
    "$(real_home)/esp-phone" \
    "$(real_home)/esp phone" \
    /home/*/esp-phone \
    /opt/esp-phone \
    /opt/src/esp-phone
  do
    if [[ -d "$d/.git" ]] || [[ -d "$d/pi_handset" ]]; then
      echo "$d"
      return 0
    fi
  done
  return 1
}

remember_repo() {
  local dest="$1"
  mkdir -p "$(real_home)/.esp-handset" 2>/dev/null || true
  echo "$dest" >"$(real_home)/.esp-handset/repo.path" 2>/dev/null || true
  if [[ "$(id -u)" -eq 0 ]]; then
    mkdir -p /etc/esp-handset
    echo "$dest" >/etc/esp-handset/repo.path
  elif sudo -n true 2>/dev/null; then
    echo "$dest" | sudo -n tee /etc/esp-handset/repo.path >/dev/null 2>&1 || true
  fi
}

ensure_repo() {
  local repo
  if repo="$(find_repo)"; then
    echo "$repo"
    return 0
  fi
  local dest="${ESP_HANDSET_REPO:-$(real_home)/esp-phone}"
  log "No local repo — cloning $GIT_URL → $dest"
  mkdir -p "$(dirname "$dest")"
  if ! as_user git clone --branch "$BRANCH" --depth 1 "$GIT_URL" "$dest" 2>&1 | tee -a "$LOG"; then
    log "ERROR: git clone failed (network / git?)"
    return 1
  fi
  remember_repo "$dest"
  echo "$dest"
}

install_tree() {
  local REPO="$1"
  local ROOT="$REPO/pi_handset"
  if [[ ! -d "$ROOT/esp_handset" ]]; then
    log "ERROR: missing $ROOT/esp_handset"
    return 1
  fi
  if [[ "$(id -u)" -ne 0 ]]; then
    log "ERROR: install needs root"
    return 1
  fi

  local USER_NAME
  USER_NAME="$(real_user)"

  log "Installing software → $PREFIX (user=$USER_NAME)"
  mkdir -p "$PREFIX" "$PREFIX/session" /etc/esp-handset
  cp -a "$ROOT/esp_handset" "$PREFIX/"
  cp -a "$ROOT/session/." "$PREFIX/session/" 2>/dev/null || true
  install -m 755 "$ROOT/esp_handset/hat_inputd.py" "$PREFIX/hat_inputd.py"
  install -m 755 "$ROOT/esp_handset/buttons_inputd.py" "$PREFIX/buttons_inputd.py"
  install -m 755 "$ROOT/esp_handset/cardkb_inputd.py" "$PREFIX/cardkb_inputd.py"
  install -m 755 "$ROOT/esp_handset/t9_keypad_inputd.py" "$PREFIX/t9_keypad_inputd.py"
  install -m 755 "$ROOT/esp_handset/handset_app.py" "$PREFIX/handset_app.py"
  install -m 755 "$ROOT/esp_handset/esp_keyd.py" "$PREFIX/esp_keyd.py"
  install -m 755 "$ROOT/session/handset-session.sh" "$PREFIX/session/handset-session.sh"
  install -m 755 "$ROOT/session/handset-session.sh" /usr/local/bin/handset-session
  for pair in \
    "mirror-displays.sh:digivice-mirror-displays" \
    "digivice-layout.sh:digivice-layout" \
    "restore-desktop-displays.sh:digivice-restore-desktop" \
    "unfuck-displays.sh:digivice-unfuck-displays" \
    "spi-test.sh:digivice-spi-test" \
    "spi-prove.sh:digivice-spi-prove" \
    "spi-blank.sh:digivice-spi-blank" \
    "desktop-spi-mirror.sh:digivice-desktop-mirror" \
    "update-handset.sh:digivice-update" \
    "ensure-buttons.sh:digivice-ensure-buttons" \
    "fix-cursor.sh:digivice-fix-cursor" \
    "restore-desktop-displays.sh:digivice-restore-desktop" \
    "hdmi-hotplug.sh:digivice-hdmi-hotplug" \
    "gui-update.sh:digivice-gui-update" \
    "power.sh:digivice-power"
  do
    src="${pair%%:*}"
    dst="${pair##*:}"
    if [[ -f "$ROOT/session/$src" ]]; then
      install -m 755 "$ROOT/session/$src" "$PREFIX/session/$src"
      install -m 755 "$ROOT/session/$src" "/usr/local/bin/$dst"
    fi
  done

  if [[ -d "$ROOT/display" ]]; then
    cp -a "$ROOT/display" "$PREFIX/"
    install -m 755 "$ROOT/display/recover-hdmi.sh" /usr/local/bin/digivice-recover-hdmi 2>/dev/null || true
    install -m 755 "$ROOT/display/set-panel-rotation.sh" /usr/local/bin/digivice-set-rotation 2>/dev/null || true
    install -m 755 "$ROOT/display/spi-doctor.sh" /usr/local/bin/digivice-spi-doctor 2>/dev/null || true
    install -m 755 "$ROOT/display/install-spi-userspace.sh" /usr/local/bin/digivice-install-spi-userspace 2>/dev/null || true
  fi

  if [[ -d /etc/sudoers.d ]]; then
    cat >/etc/sudoers.d/esp-handset-update <<EOF
# Digivice Settings → Update / Power (passwordless)
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-update
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-full-update
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-gui-update
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-power
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/update-handset.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/full-update.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/gui-update.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/power.sh
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-ensure-buttons
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/ensure-buttons.sh
EOF
    chmod 440 /etc/sudoers.d/esp-handset-update
  fi
  if [[ -f "$ROOT/session/gui-update.sh" ]]; then
    install -m 755 "$ROOT/session/gui-update.sh" "$PREFIX/session/gui-update.sh"
    install -m 755 "$ROOT/session/gui-update.sh" /usr/local/bin/digivice-gui-update
  fi
  if [[ -f "$ROOT/session/power.sh" ]]; then
    install -m 755 "$ROOT/session/power.sh" "$PREFIX/session/power.sh"
    install -m 755 "$ROOT/session/power.sh" /usr/local/bin/digivice-power
  fi
  if [[ -x /usr/local/bin/digivice-hdmi-hotplug ]]; then
    /usr/local/bin/digivice-hdmi-hotplug --disable 2>&1 | tee -a "$LOG" || true
  fi
  if [[ -f "$ROOT/session/fix-screens.sh" ]]; then
    install -m 755 "$ROOT/session/fix-screens.sh" "$PREFIX/session/fix-screens.sh"
    install -m 755 "$ROOT/session/fix-screens.sh" /usr/local/bin/digivice-fix-screens
  fi

  remember_repo "$REPO"

  # GUI Settings update: copy binaries only — do not rewrite/restart input daemons
  # mid-flight (that felt like a crash / "corruption" on the 2" panel).
  if [[ "${ESP_HANDSET_SOFT_SERVICES:-0}" == "1" ]]; then
    log "Soft services: skip ensure-buttons / keyd restart (GUI update)"
  else
    # Buttons MUST be on boot — rewrite unit + enable (update used to only restart)
    if [[ -f "$PREFIX/session/ensure-buttons.sh" ]]; then
      bash "$PREFIX/session/ensure-buttons.sh" 2>&1 | tee -a "$LOG" || true
    else
      systemctl daemon-reload 2>/dev/null || true
      systemctl enable digi-buttons-inputd.service 2>/dev/null || true
      systemctl restart digi-buttons-inputd.service 2>/dev/null || true
    fi
    systemctl enable esp-keyd.service 2>/dev/null || true
    systemctl restart esp-keyd.service 2>/dev/null || true
  fi

  if [[ "$FULL" -eq 1 ]]; then
    log "FULL: re-running install-display.sh (may undo userspace SPI)"
    bash "$ROOT/display/install-display.sh" 2>&1 | tee -a "$LOG" || true
  else
    log "Skipped display install (safe). Userspace SPI left alone."
  fi

  log "Install OK"
  return 0
}

# --- main ---
log "=== digivice-update start ==="

# Elevate early so install path is simple; still do git as real user when root.
if [[ "$(id -u)" -ne 0 ]]; then
  if sudo -n true 2>/dev/null; then
    log "Elevating with sudo -n…"
    exec sudo -n env \
      ESP_HANDSET_PREFIX="$PREFIX" \
      ESP_HANDSET_REPO="${ESP_HANDSET_REPO:-}" \
      ESP_HANDSET_GIT_URL="$GIT_URL" \
      ESP_HANDSET_BRANCH="$BRANCH" \
      HOME="$(real_home)" \
      SUDO_USER="$(real_user)" \
      DISPLAY="${DISPLAY:-:0}" \
      bash "$0" "$@"
  fi
  log "WARN: no passwordless sudo — pull only; install will fail for /opt"
fi

REPO="$(ensure_repo)" || exit 1
export ESP_HANDSET_REPO="$REPO"
log "Repo: $REPO"

if [[ -d "$REPO/.git" ]]; then
  log "Fetching $BRANCH…"
  as_user git -C "$REPO" remote set-url origin "$GIT_URL" 2>/dev/null || true
  if ! as_user git -C "$REPO" fetch --prune origin "$BRANCH" 2>&1 | tee -a "$LOG"; then
    log "ERROR: git fetch failed (network / GitHub?). Refusing to reset or install."
    log "  Working tree left untouched. Try again when online, or:"
    log "  sudo digivice-full-update"
    exit 2
  fi

  LOCAL="$(as_user git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo '?')"
  REMOTE="$(as_user git -C "$REPO" rev-parse --short "origin/$BRANCH" 2>/dev/null || echo '?')"
  log "Local  $LOCAL"
  log "Remote $REMOTE"

  if [[ "$CHECK_ONLY" -eq 1 ]]; then
    if [[ "$LOCAL" != "$REMOTE" && "$REMOTE" != "?" ]]; then
      log "Update available"
      exit 0
    fi
    log "Up to date"
    exit 0
  fi

  if [[ "$REMOTE" == "?" ]]; then
    log "ERROR: origin/$BRANCH missing after fetch — abort (no install)"
    exit 2
  fi

  log "Syncing working tree to origin/$BRANCH…"
  # Tracked local edits only — never stash -u (that hid/corrupted untracked files)
  as_user git -C "$REPO" stash push -m "digivice-update auto-stash" 2>/dev/null || true
  as_user git -C "$REPO" checkout "$BRANCH" 2>/dev/null \
    || as_user git -C "$REPO" checkout -B "$BRANCH" "origin/$BRANCH"
  if ! as_user git -C "$REPO" reset --hard "origin/$BRANCH" 2>&1 | tee -a "$LOG"; then
    log "ERROR: git reset --hard failed — tree may be dirty; NOT installing"
    exit 3
  fi
  LOCAL="$(as_user git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo '?')"
  log "Now at $LOCAL"
else
  log "WARN: not a git checkout — install only from existing tree"
  if [[ "$CHECK_ONLY" -eq 1 ]]; then
    log "No git metadata"
    exit 0
  fi
fi

if [[ "$(id -u)" -ne 0 ]]; then
  log "ERROR: need root (or passwordless sudo digivice-update) to install"
  log "  sudo digivice-update   OR   re-run install-handset once to seed sudoers"
  exit 1
fi

# Soft mode (GUI Settings update): install files only; defer button-daemon rewrite
# so Digivice keys stay alive until the UI restarts itself.
SOFT_SERVICES="${ESP_HANDSET_SOFT_SERVICES:-0}"

install_tree "$REPO"
rc=$?
if [[ $rc -ne 0 ]]; then
  log "Update FAILED (exit $rc)"
  exit "$rc"
fi

# Sanity: installed tree must look like Digivice
if [[ ! -f "$PREFIX/esp_handset/handset_app.py" && ! -f "$PREFIX/handset_app.py" ]]; then
  log "ERROR: install missing handset_app.py — refusing success"
  exit 4
fi
if [[ ! -x /usr/local/bin/handset-session && ! -x /usr/local/bin/handset-phone ]]; then
  log "ERROR: handset-session/phone missing after install"
  exit 4
fi

REV="$(as_user git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo '?')"
STAMP="ok rev=$REV $(date -Iseconds)"
mkdir -p "$(real_home)/.esp-handset" /etc/esp-handset
echo "$STAMP" >"$(real_home)/.esp-handset/last_update" 2>/dev/null || true
echo "$STAMP" >/etc/esp-handset/last_update 2>/dev/null || true
chown "$(real_user):$(real_user)" "$(real_home)/.esp-handset/last_update" 2>/dev/null || true

log "Update complete. $STAMP"

if [[ "$RESTART" -eq 1 ]]; then
  log "Restarting Digivice UI…"
  export DISPLAY="${DISPLAY:-:0}"
  UH="$(real_home)"
  UU="$(real_user)"
  XA="${XAUTHORITY:-$UH/.Xauthority}"
  nohup bash -c "
    sleep 0.8
    pkill -f handset_app.py 2>/dev/null || true
    sleep 0.5
    export DISPLAY=\"${DISPLAY:-:0}\"
    export XAUTHORITY=\"$XA\"
    export HOME=\"$UH\"
    if id \"$UU\" >/dev/null 2>&1 && [[ \"\$(id -u)\" -eq 0 ]]; then
      sudo -u \"$UU\" -H env DISPLAY=\"${DISPLAY:-:0}\" XAUTHORITY=\"$XA\" HOME=\"$UH\" \
        bash -lc 'handset-phone 2>/dev/null || handset-session phone'
    else
      handset-phone 2>/dev/null || handset-session phone
    fi
  " >>"$LOG" 2>&1 &
fi

exit 0
