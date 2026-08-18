#!/usr/bin/env bash
# Digivice Settings → Update button.
# git pull + stage install to /opt/esp-handset.staging (live /opt untouched).
# Does NOT kill Digivice or swap /opt — the UI exits, then digivice-apply-update runs.
#
#   digivice-gui-update
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"

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
  self="${BASH_SOURCE[0]:-$0}"
  wrap="/usr/local/bin/digivice-gui-update"
  if [[ -x "$wrap" ]]; then
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
      "$wrap" "$@"
  fi
  if [[ -f "$self" ]]; then
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
      bash "$self" "$@"
  fi
  echo "ERROR: need passwordless sudo for digivice-gui-update"
  echo "  Fix once (SSH): cd ~/esp-phone && git pull && sudo bash pi_handset/session/full-update.sh"
  exit 1
fi

run() {
  if command -v stdbuf >/dev/null 2>&1; then
    stdbuf -oL -eL "$@"
  else
    "$@"
  fi
}

echo "[gui-update] pull + STAGE only  $(date -Iseconds)"
echo "[gui-update] will NOT kill Digivice or swap /opt (UI does that after exit)"

export ESP_HANDSET_SOFT_SERVICES=1
export ESP_HANDSET_STAGE=1

REPO="$(find_repo || true)"

# Prefer the *repo* updater after a prior pull when present (self-heal).
if [[ -n "${REPO:-}" && -f "$REPO/pi_handset/session/update-handset.sh" ]]; then
  UPDATER=(bash "$REPO/pi_handset/session/update-handset.sh")
elif [[ -x /usr/local/bin/digivice-update ]]; then
  UPDATER=(/usr/local/bin/digivice-update)
elif [[ -f "$PREFIX/session/update-handset.sh" ]]; then
  UPDATER=(bash "$PREFIX/session/update-handset.sh")
else
  echo "ERROR: digivice-update missing"
  echo "  sudo digivice-full-update"
  exit 1
fi

run env ESP_HANDSET_SOFT_SERVICES=1 ESP_HANDSET_STAGE=1 "${UPDATER[@]}"
rc=$?

# Refresh apply helper into /usr/local (small scripts — safe while UI runs)
if [[ -n "${REPO:-}" ]]; then
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
  if [[ -f "$REPO/pi_handset/session/update-handset.sh" ]]; then
    install -m 755 "$REPO/pi_handset/session/update-handset.sh" \
      /usr/local/bin/digivice-update
  fi
fi

if [[ ${rc:-1} -eq 0 && ! -f "${PREFIX}.staging/.ready" ]]; then
  echo "[gui-update] staging marker missing — install-only stage retry"
  if [[ -n "${REPO:-}" && -f "$REPO/pi_handset/session/update-handset.sh" ]]; then
    run env ESP_HANDSET_SOFT_SERVICES=1 ESP_HANDSET_STAGE=1 \
      bash "$REPO/pi_handset/session/update-handset.sh" --install-only
    rc=$?
  fi
fi

if [[ ${rc:-1} -eq 0 && -f "${PREFIX}.staging/.ready" ]]; then
  echo "[gui-update] STAGED OK — exit 0; Digivice will apply after it quits"
  echo "staged $(date -Iseconds)" >"${HOME:-/tmp}/.esp-handset/last_gui_update" 2>/dev/null || true
  for h in /home/*/.esp-handset; do
    [[ -d "$h" ]] && echo "staged $(date -Iseconds)" >"$h/last_gui_update" 2>/dev/null || true
  done
  # VoIP: install/find linphonecsh during Settings→Update (no SSH needed)
  ENSURE=""
  for cand in \
    "${REPO:-}/pi_handset/session/ensure-linphone.sh" \
    "${PREFIX}.staging/session/ensure-linphone.sh" \
    "$PREFIX/session/ensure-linphone.sh" \
    /usr/local/bin/digivice-ensure-linphone
  do
    if [[ -n "$cand" && -f "$cand" ]]; then
      ENSURE="$cand"
      break
    fi
  done
  if [[ -n "$ENSURE" ]]; then
    echo "[gui-update] ensuring Linphone (VoIP)…"
    install -m 755 "$ENSURE" /usr/local/bin/digivice-ensure-linphone 2>/dev/null || true
    RUN_AS="${SUDO_USER:-}"
    [[ -z "$RUN_AS" || "$RUN_AS" == "root" ]] && RUN_AS="$(logname 2>/dev/null || true)"
    SUDO_USER="${RUN_AS:-pi}" DIGIVICE_USER="${RUN_AS:-pi}" \
      bash /usr/local/bin/digivice-ensure-linphone \
      >>"${HOME:-/tmp}/.esp-handset/linphone-ensure.log" 2>&1 \
      || echo "[gui-update] WARN: ensure-linphone failed (apply will retry)"
  fi
  # Intentionally do NOT schedule apply here — double-apply + pkill crashed Pi Zero.
  exit 0
fi

echo "[gui-update] FAILED rc=${rc:-1}"
echo "[gui-update] Digivice left running; live /opt not swapped."
exit "${rc:-1}"
