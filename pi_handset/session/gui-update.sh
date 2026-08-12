#!/usr/bin/env bash
# Digivice Settings → Update button.
# 1) git pull + stage install to /opt/esp-handset.staging (live /opt untouched)
# 2) UI exits and runs digivice-apply-update to swap + relaunch
#
# Never overwrites running Digivice code in /opt — that crashed the Pi.
#
#   digivice-gui-update
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"

# Prefer running the copy from the git repo after we sync it (bootstrap).
find_repo() {
  if [[ -n "${ESP_HANDSET_REPO:-}" && -d "${ESP_HANDSET_REPO}/pi_handset" ]]; then
    echo "$ESP_HANDSET_REPO"; return 0
  fi
  if [[ -f /etc/esp-handset/repo.path ]]; then
    local p
    p="$(tr -d '[:space:]' </etc/esp-handset/repo.path)"
    [[ -d "$p/pi_handset" ]] && echo "$p" && return 0
  fi
  local d
  for d in "${HOME}/esp-phone" /home/*/esp-phone /opt/esp-phone; do
    [[ -d "$d/pi_handset" ]] && echo "$d" && return 0
  done
  return 1
}

if [[ "$(id -u)" -ne 0 ]]; then
  if sudo -n true 2>/dev/null; then
    exec sudo -n env \
      HOME="${HOME}" \
      SUDO_USER="${SUDO_USER:-$USER}" \
      USER="${USER}" \
      DISPLAY="${DISPLAY:-:0}" \
      XAUTHORITY="${XAUTHORITY:-}" \
      ESP_HANDSET_PREFIX="$PREFIX" \
      ESP_HANDSET_REPO="${ESP_HANDSET_REPO:-}" \
      ESP_HANDSET_SOFT_SERVICES=1 \
      ESP_HANDSET_STAGE=1 \
      PATH="/usr/local/bin:/usr/bin:/bin:$PATH" \
      bash "$0" "$@"
  fi
  echo "ERROR: need passwordless sudo for digivice-gui-update"
  echo "  Fix once: sudo digivice-full-update"
  exit 1
fi

run() {
  if command -v stdbuf >/dev/null 2>&1; then
    stdbuf -oL -eL "$@"
  else
    "$@"
  fi
}

echo "[gui-update] pull + STAGE install  $(date -Iseconds)"
echo "[gui-update] live /opt left running until apply-after-exit"

export ESP_HANDSET_SOFT_SERVICES=1
export ESP_HANDSET_STAGE=1

# If repo has a newer update-handset.sh, prefer it (self-heal after git pull below).
REPO="$(find_repo || true)"
UPDATER=""
if [[ -n "${REPO:-}" && -f "$REPO/pi_handset/session/update-handset.sh" ]]; then
  # Pull using repo script first if present — but we need fetch before that.
  # Use installed digivice-update for pull+stage; it will read ESP_HANDSET_STAGE.
  :
fi

if [[ -x /usr/local/bin/digivice-update ]]; then
  UPDATER=(/usr/local/bin/digivice-update)
elif [[ -f "$PREFIX/session/update-handset.sh" ]]; then
  UPDATER=(bash "$PREFIX/session/update-handset.sh")
elif [[ -n "${REPO:-}" && -f "$REPO/pi_handset/session/update-handset.sh" ]]; then
  UPDATER=(bash "$REPO/pi_handset/session/update-handset.sh")
else
  echo "ERROR: digivice-update missing"
  echo "  sudo digivice-full-update"
  exit 1
fi

# Bootstrap: if repo exists, sync git using whatever updater we have, but
# force STAGE so live tree is never overwritten mid-UI.
run env ESP_HANDSET_SOFT_SERVICES=1 ESP_HANDSET_STAGE=1 "${UPDATER[@]}"
rc=$?

# After pull, re-run staging with the *repo* copy of update-handset if it now
# exists and differs — ensures first update after this fix stages correctly.
if [[ ${rc:-1} -eq 0 && -n "${REPO:-}" && -f "$REPO/pi_handset/session/update-handset.sh" ]]; then
  # Install apply helper + new gui scripts into /usr/local immediately (safe)
  if [[ -f "$REPO/pi_handset/session/apply-update.sh" ]]; then
    install -m 755 "$REPO/pi_handset/session/apply-update.sh" \
      /usr/local/bin/digivice-apply-update
    install -m 755 "$REPO/pi_handset/session/apply-update.sh" \
      "$PREFIX/session/apply-update.sh" 2>/dev/null || true
  fi
  if [[ -f "$REPO/pi_handset/session/gui-update.sh" ]]; then
    install -m 755 "$REPO/pi_handset/session/gui-update.sh" \
      /usr/local/bin/digivice-gui-update
  fi
  if [[ -f "$REPO/pi_handset/session/home-relaunch.sh" ]]; then
    install -m 755 "$REPO/pi_handset/session/home-relaunch.sh" \
      /usr/local/bin/digivice-home-relaunch
  fi
  if [[ -f "$REPO/pi_handset/session/update-handset.sh" ]]; then
    install -m 755 "$REPO/pi_handset/session/update-handset.sh" \
      /usr/local/bin/digivice-update
  fi
fi

if [[ ${rc:-1} -eq 0 ]]; then
  if [[ ! -f "${PREFIX}.staging/.ready" ]]; then
    # Old updater ignored STAGE — refuse to claim success if live was mutated
    # mid-flight; still try to stage now from repo while UI is up.
    echo "[gui-update] staging marker missing — staging from repo now"
    if [[ -n "${REPO:-}" && -f "$REPO/pi_handset/session/update-handset.sh" ]]; then
      run env ESP_HANDSET_SOFT_SERVICES=1 ESP_HANDSET_STAGE=1 \
        bash "$REPO/pi_handset/session/update-handset.sh" --install-only
      rc=$?
    fi
  fi
fi

if [[ ${rc:-1} -eq 0 && -f "${PREFIX}.staging/.ready" ]]; then
  echo "[gui-update] STAGED OK — applying after UI exit"
  echo "staged $(date -Iseconds)" >"${HOME:-/tmp}/.esp-handset/last_gui_update" 2>/dev/null || true
  for h in /home/*/.esp-handset; do
    [[ -d "$h" ]] && echo "staged $(date -Iseconds)" >"$h/last_gui_update" 2>/dev/null || true
  done
  # Own the restart even if an older Digivice UI still uses the crashy
  # pkill+handset-phone path — apply waits, swaps, then safe relaunch.
  APPLY=""
  for a in \
    /usr/local/bin/digivice-apply-update \
    "$PREFIX/session/apply-update.sh" \
    "${REPO:-}/pi_handset/session/apply-update.sh"
  do
    if [[ -n "$a" && -f "$a" ]]; then
      APPLY="$a"
      break
    fi
  done
  if [[ -n "$APPLY" ]]; then
    nohup bash -c "
      sleep 1.5
      exec sudo -n bash $(printf %q "$APPLY")
    " >>"${HOME:-/tmp}/.esp-handset/apply-update.log" 2>&1 &
    echo "[gui-update] apply scheduled (pid $!)"
  fi
  exit 0
fi

echo "[gui-update] FAILED rc=${rc:-1}"
echo "[gui-update] Digivice left running; live /opt not swapped."
exit "${rc:-1}"
