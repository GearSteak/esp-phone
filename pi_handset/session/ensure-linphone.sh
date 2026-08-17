#!/usr/bin/env bash
# Ensure linphonecsh (VoIP) is installed for Digivice calls.
#   sudo digivice-ensure-linphone
#   sudo digivice-ensure-linphone --doctor
set -u
set +e

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
LOG_DIR="${HOME:-/tmp}/.esp-handset"
[[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" ]] && \
  LOG_DIR="$(getent passwd "$SUDO_USER" | cut -d: -f6)/.esp-handset"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/linphone-ensure.log"

log() { echo "[ensure-linphone] $*" | tee -a "$LOG" >&2; }

if [[ "$(id -u)" -ne 0 ]]; then
  log "need root (try: sudo digivice-ensure-linphone)"
  exit 1
fi

have_bin() {
  command -v linphonecsh >/dev/null 2>&1 && return 0
  [[ -x /usr/bin/linphonecsh ]] && return 0
  [[ -x /usr/local/bin/linphonecsh ]] && return 0
  return 1
}

doctor() {
  echo "=== Digivice Linphone doctor ==="
  echo "date: $(date -Is 2>/dev/null || date)"
  echo "arch: $(uname -m)"
  echo "os: $(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown}")"
  echo "--- binaries ---"
  for b in linphonecsh linphonec linphone-daemon; do
    if command -v "$b" >/dev/null 2>&1; then
      echo "OK  $(command -v "$b")"
    elif [[ -x "/usr/bin/$b" ]]; then
      echo "OK  /usr/bin/$b"
    else
      echo "MISSING  $b"
    fi
  done
  echo "--- apt ---"
  apt-cache policy linphone-cli 2>&1 | head -n 12 || true
  dpkg -l 'linphone*' 2>&1 | head -n 20 || true
  echo "--- sip.env ---"
  for f in /etc/esp-handset/sip.env "${SUDO_USER:+$(getent passwd "$SUDO_USER" | cut -d: -f6)/.esp-handset/sip.env}"; do
    [[ -z "$f" ]] && continue
    if [[ -f "$f" ]]; then
      echo "found $f"
      grep -E '^(SIP_SERVER|SIP_USER|SIP_DISPLAY)=' "$f" 2>/dev/null || true
    fi
  done
  echo "=== end ==="
}

install_cli() {
  export DEBIAN_FRONTEND=noninteractive
  log "apt-get update…"
  apt-get update -qq 2>&1 | tee -a "$LOG" | tail -n 5
  log "apt-get install linphone-cli…"
  # Dedicated transaction so other package failures don't skip VoIP
  if ! apt-get install -y linphone-cli 2>&1 | tee -a "$LOG"; then
    log "WARN: linphone-cli install failed — trying linphone-common + linphone-cli"
    apt-get install -y linphone-common linphone-cli 2>&1 | tee -a "$LOG" || true
  fi
  # Some images only search under a different name
  if ! have_bin; then
    log "searching apt for linphone packages…"
    apt-cache search --names-only '^linphone' 2>&1 | tee -a "$LOG" || true
    apt-get install -y linphone-nogtk 2>&1 | tee -a "$LOG" || true
  fi
}

DOCTOR=0
for a in "$@"; do
  [[ "$a" == "--doctor" || "$a" == "doctor" ]] && DOCTOR=1
done

if [[ "$DOCTOR" -eq 1 ]]; then
  doctor
  exit 0
fi

if have_bin; then
  log "already present: $(command -v linphonecsh 2>/dev/null || echo /usr/bin/linphonecsh)"
else
  install_cli
fi

if ! have_bin; then
  log "FAILED — linphonecsh still missing"
  doctor | tee -a "$LOG"
  exit 2
fi

BIN="$(command -v linphonecsh 2>/dev/null || echo /usr/bin/linphonecsh)"
log "OK $BIN"

# Warm daemon as Digivice user (pipe is per-uid)
RUN_AS="${SUDO_USER:-}"
HOME_AS=""
if [[ -n "$RUN_AS" && "$RUN_AS" != "root" ]]; then
  HOME_AS="$(getent passwd "$RUN_AS" | cut -d: -f6)"
  SIP_ENV="/etc/esp-handset/sip.env"
  [[ -f "$HOME_AS/.esp-handset/sip.env" ]] && SIP_ENV="$HOME_AS/.esp-handset/sip.env"
  # shellcheck disable=SC1090
  set -a
  # shellcheck source=/dev/null
  [[ -f "$SIP_ENV" ]] && . "$SIP_ENV"
  set +a
  sudo -u "$RUN_AS" env HOME="$HOME_AS" "$BIN" init >/dev/null 2>&1 || true
  if [[ -n "${SIP_USER:-}" && -n "${SIP_SERVER:-}" && -n "${SIP_PASS:-}" ]]; then
    sudo -u "$RUN_AS" env HOME="$HOME_AS" \
      "$BIN" register "sip:${SIP_USER}@${SIP_SERVER}" "$SIP_SERVER" "$SIP_PASS" \
      >/dev/null 2>&1 || log "WARN: register failed (Digivice will retry)"
  fi
fi

exit 0
