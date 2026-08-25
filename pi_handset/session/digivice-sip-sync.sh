#!/usr/bin/env bash
# Keep /etc and ~/.esp-handset sip.env in sync; never clobber a saved password.
# Regenerate linphonerc after install/update. Optional register probe.
#
#   digivice-sip-sync                 # sync files + linphonerc (as user)
#   sudo digivice-sip-sync            # during full-update
#   digivice-sip-sync --probe         # sync + short register test (Settings Test SIP)
#   digivice-sip-sync --files-only    # sync files only (early full-update)
set -u
set +e

MODE="${1:-}"
PROBE=0
FILES_ONLY=0
case "$MODE" in
  --probe) PROBE=1 ;;
  --files-only) FILES_ONLY=1 ;;
  --help|-h)
    echo "Usage: digivice-sip-sync [--files-only | --probe]"
    exit 0
    ;;
esac

if [[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" ]]; then
  RUN_USER="$SUDO_USER"
  RUN_HOME="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
else
  RUN_USER="${USER:-$(id -un)}"
  RUN_HOME="${HOME:-$(getent passwd "$RUN_USER" 2>/dev/null | cut -d: -f6)}"
fi
[[ -z "$RUN_HOME" ]] && RUN_HOME="/home/$RUN_USER"

ETC_ENV="/etc/esp-handset/sip.env"
HOME_ENV="$RUN_HOME/.esp-handset/sip.env"
LOG_DIR="$RUN_HOME/.esp-handset"
STATUS_FILE="$LOG_DIR/sip-sync.status"
LOG="$LOG_DIR/sip-sync.log"
REPO_SEED="${DIGIVICE_SIP_SEED:-}"
PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"

log() { echo "[sip-sync] $*" | tee -a "$LOG"; }

mkdir -p "$LOG_DIR" /etc/esp-handset 2>/dev/null || true
touch "$LOG" 2>/dev/null || true
if [[ "$(id -u)" -eq 0 ]]; then
  chown "$RUN_USER:$RUN_USER" "$LOG_DIR" "$LOG" 2>/dev/null || true
fi

_sip_field() {
  local file="$1" key="$2"
  grep "^${key}=" "$file" 2>/dev/null | head -n1 | cut -d= -f2- | sed 's/\r$//' | tr -d '[:space:]'
}

_is_placeholder_pass() {
  local pass="$1"
  [[ -z "$pass" ]] && return 0
  case "$pass" in
    YOUR_*|your_*|CHANGE_ME*|change_me*|Ping927Ld) return 0 ;;
  esac
  return 1
}

_is_placeholder_user() {
  local user="$1"
  [[ -z "$user" ]] && return 0
  case "$user" in
    YOUR_*|your_*|CHANGE_ME*|change_me*) return 0 ;;
  esac
  return 1
}

_is_real_env() {
  local f="$1"
  [[ -f "$f" ]] || return 1
  local u p
  u="$(_sip_field "$f" SIP_USER)"
  p="$(_sip_field "$f" SIP_PASS)"
  _is_placeholder_user "$u" && return 1
  _is_placeholder_pass "$p" && return 1
  [[ -n "$(_sip_field "$f" SIP_SERVER)" ]] || return 1
  return 0
}

_score_env() {
  local f="$1"
  [[ -f "$f" ]] || { echo 0; return; }
  _is_real_env "$f" && echo 10 || echo 1
}

_pick_source() {
  local best="" score=0 s f
  for f in "$HOME_ENV" "$ETC_ENV" "$REPO_SEED"; do
    [[ -n "$f" && -f "$f" ]] || continue
    s="$(_score_env "$f")"
    if [[ "$s" -gt "$score" ]]; then
      score="$s"
      best="$f"
    elif [[ "$s" -eq "$score" && "$s" -gt 0 && "$f" == "$HOME_ENV" ]]; then
      best="$f"
    fi
  done
  echo "$best"
}

_write_both() {
  local src="$1"
  [[ -f "$src" ]] || return 1
  mkdir -p "$(dirname "$HOME_ENV")" /etc/esp-handset 2>/dev/null || true
  install -m 600 "$src" "$HOME_ENV" 2>/dev/null || {
    cp "$src" "$HOME_ENV"
    chmod 600 "$HOME_ENV" 2>/dev/null || true
  }
  if [[ "$(id -u)" -eq 0 ]]; then
    install -m 600 "$src" "$ETC_ENV" 2>/dev/null || {
      cp "$src" "$ETC_ENV"
      chmod 600 "$ETC_ENV" 2>/dev/null || true
    }
    chown "$RUN_USER:$RUN_USER" "$HOME_ENV" "$ETC_ENV" 2>/dev/null || true
  elif [[ -w /etc/esp-handset ]] || [[ -w "$ETC_ENV" ]]; then
    install -m 600 "$src" "$ETC_ENV" 2>/dev/null || true
  fi
  return 0
}

_seed_placeholder() {
  mkdir -p "$(dirname "$HOME_ENV")"
  cat >"$HOME_ENV" <<'EOF'
SIP_SERVER=sip.zadarma.com
SIP_USER=440892
SIP_PASS=YOUR_SIP_PASSWORD
SIP_DISPLAY=Digivice
SIP_DID=
EOF
  chmod 600 "$HOME_ENV" 2>/dev/null || true
  if [[ "$(id -u)" -eq 0 ]]; then
    install -m 600 "$HOME_ENV" "$ETC_ENV" 2>/dev/null || true
    chown "$RUN_USER:$RUN_USER" "$HOME_ENV" "$ETC_ENV" 2>/dev/null || true
  fi
}

_write_status() {
  echo "$1" >"$STATUS_FILE" 2>/dev/null || true
  if [[ "$(id -u)" -eq 0 ]]; then
    chown "$RUN_USER:$RUN_USER" "$STATUS_FILE" 2>/dev/null || true
  fi
}

_run_user() {
  if [[ "$(id -u)" -eq 0 ]]; then
    sudo -u "$RUN_USER" env HOME="$RUN_HOME" PYTHONPATH="$PREFIX" "$@"
  else
    env PYTHONPATH="${PYTHONPATH:-$PREFIX}" "$@"
  fi
}

_regen_linphonerc() {
  _run_user python3 -c "
from esp_handset import sip_call
p = sip_call._write_linphonerc(sip_call._sip_env())
print(p or '')
" 2>>"$LOG"
}

_probe_register() {
  _run_user python3 -c "
from esp_handset.sip_call import LinphoneEngine, _zadarma_block_reason
eng = LinphoneEngine()
try:
    err = eng.start()
    if err:
        blocked = _zadarma_block_reason()
        print(blocked or err)
    else:
        print('OK registered')
finally:
    eng.stop()
" 2>>"$LOG"
}

log "=== start $(date -Is 2>/dev/null || date) user=$RUN_USER mode=${MODE:-default} ==="

SRC="$(_pick_source)"
if [[ -z "$SRC" ]]; then
  _seed_placeholder
  _write_status "NEEDS_SETUP Open Settings → Accounts → SIP, enter Zadarma SIP password, Save SIP"
  log "seeded placeholder — set password in Settings"
  exit 0
fi

if _is_real_env "$SRC"; then
  _write_both "$SRC"
  log "synced real creds from $SRC"
else
  # Placeholder only — keep whichever file exists, sync both, do not install repo seed over user files.
  _write_both "$SRC"
  _write_status "NEEDS_SETUP Open Settings → Accounts → SIP, enter Zadarma SIP password, Save SIP"
  log "only placeholder creds in $SRC — not overwriting from repo seed"
  exit 0
fi

if [[ "$FILES_ONLY" -eq 1 ]]; then
  _write_status "SYNCED Saved SIP password kept. Run update to finish, then Test SIP in Settings."
  log "files-only done"
  exit 0
fi

_regen_linphonerc
log "linphonerc regenerated"

if [[ "$PROBE" -eq 1 ]]; then
  result="$(_probe_register | tail -n1)"
  result="${result:-register failed}"
  log "probe: $result"
  if [[ "$result" == OK* ]]; then
    _write_status "OK registered — Test SIP in Settings should work"
  else
    _write_status "FAIL $result"
  fi
  echo "$result"
  exit 0
fi

_write_status "SYNCED Password kept. Settings → Accounts → Test SIP"
log "done"
exit 0
