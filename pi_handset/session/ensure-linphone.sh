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
mkdir -p "$LOG_DIR" /var/tmp/digivice-voip
LOG="$LOG_DIR/linphone-ensure.log"
STATUS_FILE="/etc/esp-handset/linphone.status"
mkdir -p /etc/esp-handset 2>/dev/null || true

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

os_codename() {
  . /etc/os-release 2>/dev/null || true
  echo "${VERSION_CODENAME:-bookworm}"
}

os_arch() {
  dpkg --print-architecture 2>/dev/null || uname -m
}

write_status() {
  echo "$1" >"$STATUS_FILE" 2>/dev/null || true
  chmod 644 "$STATUS_FILE" 2>/dev/null || true
}

doctor() {
  echo "=== Digivice Linphone doctor ==="
  echo "date: $(date -Is 2>/dev/null || date)"
  echo "arch: $(uname -m) / $(os_arch)"
  echo "os: $(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown}")"
  echo "codename: $(os_codename)"
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
  echo "--- PATH ---"
  echo "$PATH"
  echo "--- apt policy ---"
  apt-cache policy linphone-cli 2>&1 | head -n 20 || true
  echo "--- apt-cache search ---"
  apt-cache search --names-only 'linphone' 2>&1 | head -n 30 || true
  echo "--- dpkg ---"
  dpkg -l 'linphone*' 'liblinphone*' 2>&1 | head -n 40 || true
  echo "--- sources ---"
  ls -la /etc/apt/sources.list /etc/apt/sources.list.d/ 2>&1 || true
  grep -hE '^[^#]' /etc/apt/sources.list /etc/apt/sources.list.d/* 2>/dev/null | head -n 40 || true
  echo "--- sip.env ---"
  for f in /etc/esp-handset/sip.env "${SUDO_USER:+$(getent passwd "$SUDO_USER" | cut -d: -f6)/.esp-handset/sip.env}"; do
    [[ -z "$f" ]] && continue
    if [[ -f "$f" ]]; then
      echo "found $f"
      grep -E '^(SIP_SERVER|SIP_USER|SIP_DISPLAY)=' "$f" 2>/dev/null || true
    fi
  done
  echo "--- last ensure log (tail) ---"
  tail -n 40 "$LOG" 2>/dev/null || true
  echo "=== end ==="
}

ensure_debian_voip_repo() {
  local codename arch list
  codename="$(os_codename)"
  arch="$(os_arch)"
  list=/etc/apt/sources.list.d/digivice-voip-debian.list
  # Raspberry Pi OS sometimes omits Debian main packages Digivice needs
  if apt-cache show linphone-cli >/dev/null 2>&1; then
    log "linphone-cli already visible in apt-cache"
    return 0
  fi
  log "Adding Debian $codename main ($arch) for linphone-cli…"
  cat >"$list" <<EOF
# Digivice VoIP — linphone-cli from Debian
deb [arch=${arch}] http://deb.debian.org/debian ${codename} main
deb [arch=${arch}] http://deb.debian.org/debian ${codename}-updates main
EOF
  apt-get update -qq 2>&1 | tee -a "$LOG" | tail -n 15
}

download_debs_fallback() {
  # Last resort: fetch known .debs from Debian pool (bookworm / trixie)
  local codename arch ver base tmp
  codename="$(os_codename)"
  arch="$(os_arch)"
  tmp=/var/tmp/digivice-voip
  mkdir -p "$tmp"
  case "$codename" in
    trixie|forky|sid) ver="5.3.105-5" ;;
    *) ver="5.1.65-4" ;;
  esac
  base="http://deb.debian.org/debian/pool/main/l/linphone"
  log "Direct .deb fallback ver=$ver arch=$arch"
  (
    cd "$tmp" || exit 1
    rm -f linphone-cli_*.deb linphone-common_*.deb 2>/dev/null || true
    curl -fsSL -o "linphone-common_${ver}_all.deb" \
      "${base}/linphone-common_${ver}_all.deb" 2>&1 | tee -a "$LOG" \
      || wget -q -O "linphone-common_${ver}_all.deb" \
        "${base}/linphone-common_${ver}_all.deb" 2>&1 | tee -a "$LOG"
    curl -fsSL -o "linphone-cli_${ver}_${arch}.deb" \
      "${base}/linphone-cli_${ver}_${arch}.deb" 2>&1 | tee -a "$LOG" \
      || wget -q -O "linphone-cli_${ver}_${arch}.deb" \
        "${base}/linphone-cli_${ver}_${arch}.deb" 2>&1 | tee -a "$LOG"
    if [[ ! -f "linphone-cli_${ver}_${arch}.deb" ]]; then
      log "curl failed for linphone-cli_${ver}_${arch}.deb"
      return 1
    fi
    apt-get install -y "./linphone-common_${ver}_all.deb" "./linphone-cli_${ver}_${arch}.deb" \
      2>&1 | tee -a "$LOG"
  )
}

install_cli() {
  export DEBIAN_FRONTEND=noninteractive
  log "apt-get update…"
  apt-get update -qq 2>&1 | tee -a "$LOG" | tail -n 8

  if ! apt-cache show linphone-cli >/dev/null 2>&1; then
    ensure_debian_voip_repo
  fi

  log "apt-get install linphone-cli…"
  if ! apt-get install -y linphone-cli 2>&1 | tee -a "$LOG"; then
    log "WARN: linphone-cli install failed — retry with linphone-common"
    apt-get install -y --fix-missing linphone-common linphone-cli 2>&1 | tee -a "$LOG" || true
  fi

  if ! have_bin; then
    log "searching apt for linphone packages…"
    apt-cache search linphone 2>&1 | tee -a "$LOG" | head -n 40 || true
    apt-get install -y linphone-nogtk 2>&1 | tee -a "$LOG" || true
  fi

  if ! have_bin; then
    download_debs_fallback || true
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

log "=== ensure start $(date -Is 2>/dev/null || date) ==="
if have_bin; then
  log "already present: $(command -v linphonecsh 2>/dev/null || echo /usr/bin/linphonecsh)"
else
  install_cli
fi

if ! have_bin; then
  log "FAILED — linphonecsh still missing"
  write_status "missing"
  doctor | tee -a "$LOG"
  echo ""
  echo "====================================================="
  echo " Digivice VoIP FAILED: linphonecsh not installed"
  echo " Paste this output to debug:"
  echo "   sudo digivice-ensure-linphone --doctor"
  echo " Log: $LOG"
  echo "====================================================="
  exit 2
fi

BIN="$(command -v linphonecsh 2>/dev/null || echo /usr/bin/linphonecsh)"
log "OK $BIN"
write_status "ok $BIN"
# Absolute path Digivice reads first (avoids PATH mismatches)
echo "$BIN" >/etc/esp-handset/linphone.bin
chmod 644 /etc/esp-handset/linphone.bin 2>/dev/null || true
# Symlink into /usr/local/bin if installed elsewhere
if [[ "$BIN" != /usr/local/bin/linphonecsh && "$BIN" != /usr/bin/linphonecsh ]]; then
  ln -sfn "$BIN" /usr/local/bin/linphonecsh 2>/dev/null || true
fi
if [[ ! -x /usr/bin/linphonecsh && -x "$BIN" ]]; then
  ln -sfn "$BIN" /usr/bin/linphonecsh 2>/dev/null || true
fi

# Warm daemon as Digivice user (pipe is per-uid)
RUN_AS="${SUDO_USER:-}"
if [[ -z "$RUN_AS" || "$RUN_AS" == "root" ]]; then
  # full-update may set USER_NAME via env
  RUN_AS="${DIGIVICE_USER:-}"
fi
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
