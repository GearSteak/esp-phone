#!/usr/bin/env bash
# Digivice Settings → Update runner (passwordless-friendly).
# No MessageBox, no killing Digivice mid-run, unbuffered logs to stdout.
#
#   digivice-gui-update              # quick stack update
#   digivice-gui-update --full       # full stack (apt + everything)
#   digivice-gui-update --check      # check only
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
MODE="quick"
CHECK=0
for a in "$@"; do
  case "$a" in
    --full|full) MODE="full" ;;
    --check|check) CHECK=1 ;;
  esac
done

# Always elevable without TTY
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
  echo "  Fix: sudo bash $PREFIX/session/full-update.sh"
  echo "  or:  sudo digivice-full-update"
  exit 1
fi

# Line-buffered tooling when available
run() {
  if command -v stdbuf >/dev/null 2>&1; then
    stdbuf -oL -eL "$@"
  else
    "$@"
  fi
}

echo "[gui-update] mode=$MODE check=$CHECK uid=$(id -u)"
echo "[gui-update] TIME $(date -Iseconds)"

if [[ "$CHECK" -eq 1 ]]; then
  if [[ -x /usr/local/bin/digivice-update ]]; then
    run /usr/local/bin/digivice-update --check
    exit $?
  fi
  if [[ -f "$PREFIX/session/update-handset.sh" ]]; then
    run bash "$PREFIX/session/update-handset.sh" --check
    exit $?
  fi
  echo "ERROR: digivice-update not installed"
  exit 1
fi

# Never --restart from here: Digivice process would die mid-update
if [[ "$MODE" == "full" ]]; then
  if [[ -x /usr/local/bin/digivice-full-update ]]; then
    run /usr/local/bin/digivice-full-update --no-restart
    rc=$?
  elif [[ -f "$PREFIX/session/full-update.sh" ]]; then
    run bash "$PREFIX/session/full-update.sh" --no-restart
    rc=$?
  else
    echo "ERROR: digivice-full-update missing — run once from terminal:"
    echo "  cd ~/esp-phone && git pull && sudo bash pi_handset/session/full-update.sh"
    exit 1
  fi
else
  if [[ -x /usr/local/bin/digivice-update ]]; then
    run /usr/local/bin/digivice-update
    rc=$?
  elif [[ -f "$PREFIX/session/update-handset.sh" ]]; then
    run bash "$PREFIX/session/update-handset.sh"
    rc=$?
  else
    echo "ERROR: digivice-update missing"
    exit 1
  fi
fi

if [[ ${rc:-1} -eq 0 ]]; then
  echo "[gui-update] OK — restart Digivice from Settings or handset-phone"
  # Soft signal for GUI: write flag
  echo "ok $(date -Iseconds)" >"${HOME:-/tmp}/.esp-handset/last_gui_update" 2>/dev/null || true
  for h in /home/*/.esp-handset; do
    [[ -d "$h" ]] && echo "ok $(date -Iseconds)" >"$h/last_gui_update" 2>/dev/null || true
  done
else
  echo "[gui-update] FAILED rc=$rc"
fi
exit "${rc:-1}"
