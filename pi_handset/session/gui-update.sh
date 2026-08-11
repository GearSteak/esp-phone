#!/usr/bin/env bash
# Digivice Settings → single Update button runner.
# Pulls git, installs to /opt, never kills Digivice mid-run
# (UI restarts itself after this exits 0).
#
#   digivice-gui-update
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"

if [[ "$(id -u)" -ne 0 ]]; then
  if sudo -n true 2>/dev/null; then
    exec sudo -n env \
      HOME="${HOME}" \
      SUDO_USER="${SUDO_USER:-$USER}" \
      USER="${USER}" \
      DISPLAY="${DISPLAY:-:0}" \
      ESP_HANDSET_PREFIX="$PREFIX" \
      ESP_HANDSET_REPO="${ESP_HANDSET_REPO:-}" \
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

echo "[gui-update] pull + install  $(date -Iseconds)"

# git fetch/pull + install to /opt (no mid-run UI kill)
if [[ -x /usr/local/bin/digivice-update ]]; then
  run /usr/local/bin/digivice-update
  rc=$?
elif [[ -f "$PREFIX/session/update-handset.sh" ]]; then
  run bash "$PREFIX/session/update-handset.sh"
  rc=$?
else
  echo "ERROR: digivice-update missing"
  echo "  sudo digivice-full-update"
  exit 1
fi

if [[ ${rc:-1} -eq 0 ]]; then
  echo "[gui-update] OK — Digivice UI will restart"
  echo "ok $(date -Iseconds)" >"${HOME:-/tmp}/.esp-handset/last_gui_update" 2>/dev/null || true
  for h in /home/*/.esp-handset; do
    [[ -d "$h" ]] && echo "ok $(date -Iseconds)" >"$h/last_gui_update" 2>/dev/null || true
  done
else
  echo "[gui-update] FAILED rc=$rc"
fi
exit "${rc:-1}"
