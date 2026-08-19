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
  apt-cache policy linphone-cli liblinphone12 2>&1 | head -n 30 || true
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
  local codename arch key
  codename="$(os_codename)"
  arch="$(os_arch)"
  log "Debian $codename ($arch) for linphone-cli + liblinphone12…"
  apt-get install -y debian-archive-keyring 2>&1 | tee -a "$LOG" | tail -n 8 || true
  key=""
  for cand in \
    /usr/share/keyrings/debian-archive-keyring.gpg \
    /usr/share/keyrings/debian-archive-keyring.pgp
  do
    [[ -f "$cand" ]] && key="$cand" && break
  done
  rm -f /etc/apt/sources.list.d/digivice-voip-debian.list
  if [[ -n "$key" ]]; then
    cat >/etc/apt/sources.list.d/digivice-voip-debian.sources <<EOF
Types: deb
URIs: http://deb.debian.org/debian
Suites: ${codename}
Components: main
Architectures: ${arch}
Signed-By: ${key}
EOF
  else
    log "WARN: no debian-archive-keyring — trusted=yes for VoIP debs only"
    echo "deb [arch=${arch} trusted=yes] http://deb.debian.org/debian ${codename} main" \
      >/etc/apt/sources.list.d/digivice-voip-debian.list
  fi
  cat >/etc/apt/preferences.d/digivice-voip-debian <<'EOF'
Package: *
Pin: origin deb.debian.org
Pin-Priority: 1

Package: /linphone|liblinphone|libbctoolbox|libbellesip|libbelr|libbelcard|liblime|libmediastreamer|libortp|libbcmatroska|libbcg729|libbzrtp|belcard-data|bellesip-data/
Pin: origin deb.debian.org
Pin-Priority: 990
EOF
  apt-get update -qq 2>&1 | tee -a "$LOG" | tail -n 20
}

_pool_latest() {
  local pool="$1" regex="$2" hit
  hit="$(curl -fsSL "$pool" 2>/dev/null | grep -oE "$regex" | sort -V | tail -n1 || true)"
  [[ -z "$hit" ]] && hit="$(wget -q -O - "$pool" 2>/dev/null | grep -oE "$regex" | sort -V | tail -n1 || true)"
  [[ -n "$hit" ]] && echo "${pool%/}/$hit"
}

_fetch_deb() {
  local url="$1" dest="$2"
  [[ -n "$url" ]] || return 1
  log "get $(basename "$url")"
  curl -fL --retry 3 -o "$dest" "$url" 2>>"$LOG" \
    || wget -q -O "$dest" "$url" 2>>"$LOG"
  [[ -s "$dest" ]]
}

download_debs_fallback() {
  # Raspbian has no linphone-cli. Fetch the Debian armhf stack, including
  # liblinphone12 (installing only linphone-cli.deb leaves it uninstallable).
  local arch tmp pool url f
  arch="$(os_arch)"
  tmp=/var/tmp/digivice-voip
  mkdir -p "$tmp"
  log "Direct .deb fallback arch=$arch"
  cd "$tmp" || return 1
  rm -f ./*.deb 2>/dev/null || true

  pool=http://deb.debian.org/debian/pool/main
  _fetch_deb "$(_pool_latest "$pool/l/linphone" "linphone-common_[^\"<> ]+_all\\.deb")" \
    "$tmp/linphone-common.deb" || return 1
  _fetch_deb "$(_pool_latest "$pool/l/linphone" "liblinphone12_[^\"<> ]+_${arch}\\.deb")" \
    "$tmp/liblinphone12.deb" || return 1
  _fetch_deb "$(_pool_latest "$pool/l/linphone" "linphone-cli_[^\"<> ]+_${arch}\\.deb")" \
    "$tmp/linphone-cli.deb" || return 1
  for spec in \
    "b/bctoolbox|libbctoolbox2_[^\"<> ]+_${arch}\\.deb" \
    "b/belle-sip|libbellesip3_[^\"<> ]+_${arch}\\.deb" \
    "b/belr|libbelr1_[^\"<> ]+_${arch}\\.deb" \
    "b/belcard|libbelcard1_[^\"<> ]+_${arch}\\.deb" \
    "l/lime|liblime1_[^\"<> ]+_${arch}\\.deb" \
    "m/mediastreamer2|libmediastreamer2-14_[^\"<> ]+_${arch}\\.deb" \
    "o/ortp|libortp16_[^\"<> ]+_${arch}\\.deb" \
    "b/bcmatroska2|libbcmatroska2-5_[^\"<> ]+_${arch}\\.deb" \
    "b/bcg729|libbcg729-0_[^\"<> ]+_${arch}\\.deb" \
    "b/bzrtp|libbzrtp1_[^\"<> ]+_${arch}\\.deb"
  do
    url="$(_pool_latest "$pool/${spec%%|*}" "${spec##*|}")"
    f="$tmp/$(basename "${url:-x}")"
    _fetch_deb "$url" "$f" || log "WARN: skip ${spec##*|}"
  done

  log "apt-get install local linphone debs…"
  apt-get install -y "$tmp"/*.deb 2>&1 | tee -a "$LOG"
  if ! have_bin; then
    dpkg -i "$tmp"/*.deb 2>&1 | tee -a "$LOG" || true
    apt-get install -y -f 2>&1 | tee -a "$LOG" || true
  fi
}

install_cli() {
  export DEBIAN_FRONTEND=noninteractive
  if [[ "$DEBS_ONLY" -eq 1 ]]; then
    log "debs-only: skip apt repo (that hang) — fetch Debian .debs"
    rm -f /etc/apt/sources.list.d/digivice-voip-debian.list \
      /etc/apt/sources.list.d/digivice-voip-debian.sources
    download_debs_fallback || true
    return 0
  fi
  log "apt-get update…"
  apt-get update -qq 2>&1 | tee -a "$LOG" | tail -n 8

  ensure_debian_voip_repo

  log "apt-get install linphone-cli liblinphone12…"
  apt-get install -y linphone-cli liblinphone12 linphone-common 2>&1 | tee -a "$LOG" || true

  if ! have_bin; then
    log "searching apt for linphone packages…"
    apt-cache policy linphone-cli liblinphone12 2>&1 | tee -a "$LOG" | head -n 40 || true
    apt-cache search linphone 2>&1 | tee -a "$LOG" | head -n 40 || true
    apt-get install -y linphone-nogtk 2>&1 | tee -a "$LOG" || true
  fi

  if ! have_bin; then
    download_debs_fallback || true
  fi
}

DOCTOR=0
LOCATE_ONLY=0
DEBS_ONLY=0
for a in "$@"; do
  [[ "$a" == "--doctor" || "$a" == "doctor" ]] && DOCTOR=1
  [[ "$a" == "--locate-only" || "$a" == "locate" ]] && LOCATE_ONLY=1
  [[ "$a" == "--debs" || "$a" == "debs" ]] && DEBS_ONLY=1
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
