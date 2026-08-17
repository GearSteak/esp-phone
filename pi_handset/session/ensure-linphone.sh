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
  local p r
  for p in /usr/bin/linphonecsh /usr/local/bin/linphonecsh \
    "$(command -v linphonecsh 2>/dev/null)"
  do
    [[ -z "$p" || ! -e "$p" ]] && continue
    [[ "$p" == *digivice-linphonecsh* ]] && continue
    r="$(readlink -f "$p" 2>/dev/null || echo "$p")"
    [[ "$r" == *digivice-linphonecsh* ]] && continue
    return 0
  done
  p="$(dpkg -L linphone-cli linphone-nogtk linphone 2>/dev/null \
    | grep '/linphonecsh$' | grep -v digivice | head -n1 || true)"
  [[ -n "$p" && -e "$p" ]] && return 0
  return 1
}

real_csh() {
  local p r
  for p in /usr/bin/linphonecsh /usr/local/bin/linphonecsh \
    "$(command -v linphonecsh 2>/dev/null)"
  do
    [[ -z "$p" || ! -e "$p" ]] && continue
    [[ "$p" == *digivice-linphonecsh* ]] && continue
    r="$(readlink -f "$p" 2>/dev/null || echo "$p")"
    [[ "$r" == *digivice-linphonecsh* ]] && continue
    echo "$p"
    return 0
  done
  p="$(dpkg -L linphone-cli linphone-nogtk linphone 2>/dev/null \
    | grep '/linphonecsh$' | grep -v digivice | head -n1 || true)"
  if [[ -n "$p" && -e "$p" ]]; then
    echo "$p"
    return 0
  fi
  p="$(find /usr/bin /usr/local/bin /usr/lib /usr/libexec -name linphonecsh 2>/dev/null \
    | grep -v digivice | head -n1 || true)"
  if [[ -n "$p" && -e "$p" ]]; then
    echo "$p"
    return 0
  fi
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
LOCATE_ONLY=0
for a in "$@"; do
  [[ "$a" == "--doctor" || "$a" == "doctor" ]] && DOCTOR=1
  [[ "$a" == "--locate-only" || "$a" == "locate" ]] && LOCATE_ONLY=1
done

install_linphonec_wrapper() {
  local wrap_src=""
  for cand in \
    "$PREFIX/session/digivice-linphonec.sh" \
    "$(dirname "$0")/digivice-linphonec.sh" \
    /opt/esp-handset/session/digivice-linphonec.sh
  do
    [[ -f "$cand" ]] && wrap_src="$cand" && break
  done
  if [[ -n "$wrap_src" ]]; then
    install -m 755 "$wrap_src" /usr/local/bin/digivice-linphonec
    log "wrapper → /usr/local/bin/digivice-linphonec"
  fi
  local cbin=""
    for cand in \
    /usr/bin/linphonec \
    /usr/local/bin/linphonec \
    "$(command -v linphonec 2>/dev/null)" \
    "$(dpkg -L linphone-cli 2>/dev/null | grep '/linphonec$' | grep -v daemon | head -n1 || true)"
  do
    [[ -z "$cand" || "$cand" == *digivice-linphonec* ]] && continue
    if [[ -e "$cand" ]]; then
      cbin="$cand"
      break
    fi
  done
  if [[ -n "$cbin" ]]; then
    echo "$cbin" >/etc/esp-handset/linphonec.bin
    chmod 644 /etc/esp-handset/linphonec.bin 2>/dev/null || true
    log "linphonec pin $cbin"
    if [[ ! -e /usr/local/bin/linphonec ]]; then
      ln -sfn "$cbin" /usr/local/bin/linphonec 2>/dev/null || true
    fi
  else
    log "linphonec binary not found (calls will use linphonecsh)"
  fi
}

install_wrapper() {
  local wrap_src=""
  for cand in \
    "$PREFIX/session/digivice-linphonecsh.sh" \
    "$(dirname "$0")/digivice-linphonecsh.sh" \
    /opt/esp-handset/session/digivice-linphonecsh.sh
  do
    [[ -f "$cand" ]] && wrap_src="$cand" && break
  done
  if [[ -n "$wrap_src" ]]; then
    install -m 755 "$wrap_src" /usr/local/bin/digivice-linphonecsh
    log "wrapper → /usr/local/bin/digivice-linphonecsh"
    install_linphonec_wrapper
  else
    # Inline fallback so Update always leaves Digivice a stable binary name
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
[[ -n "$REAL" && -e "$REAL" ]] || { echo "linphonecsh not found" >&2; exit 127; }
exec "$REAL" "$@"
WRAP
    chmod 755 /usr/local/bin/digivice-linphonecsh
    log "wrapper → /usr/local/bin/digivice-linphonecsh (inline)"
    install_linphonec_wrapper
  fi
}

pin_bin() {
  local bin="$1"
  [[ -n "$bin" && -e "$bin" ]] || return 1
  [[ "$bin" == *digivice-linphonecsh* ]] && return 1
  local resolved
  resolved="$(readlink -f "$bin" 2>/dev/null || echo "$bin")"
  [[ "$resolved" == *digivice-linphonecsh* ]] && return 1
  write_status "ok $bin"
  echo "$bin" >/etc/esp-handset/linphone.bin
  chmod 644 /etc/esp-handset/linphone.bin 2>/dev/null || true
  RUN_AS="${SUDO_USER:-${DIGIVICE_USER:-}}"
  if [[ -n "$RUN_AS" && "$RUN_AS" != "root" ]]; then
    HOME_AS="$(getent passwd "$RUN_AS" | cut -d: -f6)"
    if [[ -n "$HOME_AS" ]]; then
      mkdir -p "$HOME_AS/.esp-handset"
      echo "$bin" >"$HOME_AS/.esp-handset/linphone.bin"
      chown "$RUN_AS:$RUN_AS" "$HOME_AS/.esp-handset/linphone.bin" 2>/dev/null || true
    fi
  fi
  ln -sfn "$bin" /usr/local/bin/linphonecsh 2>/dev/null || true
  if [[ ! -e /usr/bin/linphonecsh ]]; then
    ln -sfn "$bin" /usr/bin/linphonecsh 2>/dev/null || true
  fi
  install_wrapper
  return 0
}

if [[ "$DOCTOR" -eq 1 ]]; then
  doctor
  exit 0
fi

log "=== ensure start $(date -Is 2>/dev/null || date) ==="
install_wrapper

if have_bin; then
  BIN="$(real_csh)"
  log "already present: $BIN"
  pin_bin "$BIN"
  if [[ "$LOCATE_ONLY" -eq 1 ]]; then
    exit 0
  fi
else
  if [[ "$LOCATE_ONLY" -eq 1 ]]; then
    BIN="$(real_csh || true)"
    if [[ -n "$BIN" && -e "$BIN" ]]; then
      pin_bin "$BIN"
      log "locate-only OK $BIN"
      exit 0
    fi
    log "locate-only: not found"
    write_status "missing"
    exit 2
  fi
  install_cli
fi

if ! have_bin; then
  log "FAILED — linphonecsh still missing"
  write_status "missing"
  doctor | tee -a "$LOG"
  echo ""
  echo "====================================================="
  echo " Digivice VoIP FAILED: linphonecsh not installed"
  echo "====================================================="
  exit 2
fi

BIN="$(real_csh)"
log "OK $BIN"
pin_bin "$BIN"

RUN_AS="${SUDO_USER:-}"
if [[ -z "$RUN_AS" || "$RUN_AS" == "root" ]]; then
  RUN_AS="${DIGIVICE_USER:-}"
fi

# Warm daemon as Digivice user (pipe is per-uid)
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
