#!/usr/bin/env bash
# Install Jellyfin for Digivice media sharing (Fire TV / other clients).
# Service is installed but NOT left enabled on boot — Digivice Share page starts it.
#
#   sudo digivice-ensure-jellyfin
#   sudo digivice-ensure-jellyfin --doctor
#
set +e
set -u

DOCTOR=0
for a in "$@"; do
  [[ "$a" == "--doctor" || "$a" == "doctor" ]] && DOCTOR=1
done

log() { echo "[ensure-jellyfin] $*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  if sudo -n true 2>/dev/null; then
    exec sudo -n bash "$0" "$@"
  fi
  echo "[ensure-jellyfin] need root" >&2
  exit 1
fi

GUI_USER="${SUDO_USER:-${DIGI_GUI_USER:-}}"
if [[ -z "$GUI_USER" || "$GUI_USER" == "root" ]]; then
  GUI_USER="$(logname 2>/dev/null || true)"
fi
if [[ -z "$GUI_USER" || "$GUI_USER" == "root" ]]; then
  for u in pi isaac gear; do
    id "$u" >/dev/null 2>&1 && { GUI_USER=$u; break; }
  done
fi
GUI_HOME="$(getent passwd "${GUI_USER:-pi}" | cut -d: -f6 || echo /home/pi)"
GUI_GROUP="$(id -gn "$GUI_USER" 2>/dev/null || echo "$GUI_USER")"

export DEBIAN_FRONTEND=noninteractive

have_jellyfin() {
  command -v jellyfin >/dev/null 2>&1 \
    || [[ -x /usr/bin/jellyfin ]] \
    || systemctl list-unit-files jellyfin.service 2>/dev/null | grep -q jellyfin
}

codename() {
  if command -v lsb_release >/dev/null 2>&1; then
    lsb_release -cs 2>/dev/null && return
  fi
  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    echo "${VERSION_CODENAME:-bookworm}"
    return
  fi
  echo bookworm
}

install_repo() {
  local arch suite
  arch="$(dpkg --print-architecture)"
  suite="$(codename)"
  case "$suite" in
    bookworm|trixie|bullseye) ;;
    *) suite=bookworm ;;
  esac

  apt-get install -y curl gnupg apt-transport-https ca-certificates lsb-release >/dev/null 2>&1 || true

  mkdir -p /etc/apt/keyrings
  if [[ ! -f /etc/apt/keyrings/jellyfin.gpg ]]; then
    curl -fsSL https://repo.jellyfin.org/jellyfin_team.gpg.key \
      | gpg --dearmor -o /etc/apt/keyrings/jellyfin.gpg \
      || curl -fsSL https://repo.jellyfin.org/debian/jellyfin_team.gpg.key \
      | gpg --dearmor -o /etc/apt/keyrings/jellyfin.gpg \
      || return 1
  fi

  # DEB822 preferred; also write .list for older apt
  cat >/etc/apt/sources.list.d/jellyfin.sources <<EOF
Types: deb
URIs: https://repo.jellyfin.org/debian
Suites: ${suite}
Components: main
Architectures: ${arch}
Signed-By: /etc/apt/keyrings/jellyfin.gpg
EOF

  echo "deb [signed-by=/etc/apt/keyrings/jellyfin.gpg arch=${arch}] https://repo.jellyfin.org/debian ${suite} main" \
    >/etc/apt/sources.list.d/jellyfin.list
}

setup_media_access() {
  mkdir -p /etc/esp-handset
  mkdir -p "$GUI_HOME/Videos" "$GUI_HOME/Music" "$GUI_HOME/Audiobooks" \
    "$GUI_HOME/.esp-handset" /srv/digivice-media/cart
  chown -R "$GUI_USER:$GUI_GROUP" "$GUI_HOME/Videos" "$GUI_HOME/Music" "$GUI_HOME/Audiobooks" \
    "$GUI_HOME/.esp-handset" 2>/dev/null || true

  # Jellyfin runs as user jellyfin — allow read of Digivice media trees
  if id jellyfin >/dev/null 2>&1; then
    usermod -aG "$GUI_GROUP" jellyfin 2>/dev/null || true
    usermod -aG video,render,audio jellyfin 2>/dev/null || true
  fi

  # Home must be traversable (x) for group; media dirs readable
  chmod 751 "$GUI_HOME" 2>/dev/null || chmod 755 "$GUI_HOME" 2>/dev/null || true
  chmod -R g+rX "$GUI_HOME/Videos" "$GUI_HOME/Music" "$GUI_HOME/Audiobooks" 2>/dev/null || true

  if ! command -v setfacl >/dev/null 2>&1; then
    apt-get install -y acl >/dev/null 2>&1 || true
  fi
  if command -v setfacl >/dev/null 2>&1 && id jellyfin >/dev/null 2>&1; then
    setfacl -m u:jellyfin:--x "$GUI_HOME" 2>/dev/null || true
    setfacl -R -m u:jellyfin:rX "$GUI_HOME/Videos" "$GUI_HOME/Music" "$GUI_HOME/Audiobooks" 2>/dev/null || true
    setfacl -R -d -m u:jellyfin:rX "$GUI_HOME/Videos" "$GUI_HOME/Music" "$GUI_HOME/Audiobooks" 2>/dev/null || true
  fi

  mkdir -p /srv/digivice-media
  chown root:jellyfin /srv/digivice-media 2>/dev/null || chown root:root /srv/digivice-media
  chmod 755 /srv/digivice-media
  echo "$GUI_HOME" >/etc/esp-handset/jellyfin-user-home
  echo "$GUI_USER" >/etc/esp-handset/jellyfin-gui-user
}

if ! have_jellyfin; then
  log "Installing Jellyfin (official repo)…"
  apt-get update -qq >/dev/null 2>&1 || true
  install_repo || log "WARN: jellyfin repo setup failed"
  apt-get update -qq 2>&1 | tail -n 5
  if ! apt-get install -y jellyfin 2>&1 | tail -n 25; then
    log "apt jellyfin failed — trying official install script…"
    curl -fsSL https://repo.jellyfin.org/install-debuntu.sh -o /tmp/jellyfin-install.sh \
      && bash /tmp/jellyfin-install.sh 2>&1 | tail -n 40 \
      || log "WARN: Jellyfin install failed"
  fi
else
  log "Jellyfin already present"
fi

setup_media_access

# Digivice Share = on demand (save RAM/CPU when not streaming)
if systemctl list-unit-files jellyfin.service 2>/dev/null | grep -q jellyfin; then
  systemctl disable jellyfin.service >/dev/null 2>&1 || true
  # Do not stop if Digivice already started it for a session
  log "jellyfin.service disabled on boot (start from Digivice → Share)"
fi

# Helper ctl
CTL_SRC="$(cd "$(dirname "$0")" && pwd)/digivice-jellyfin-ctl.sh"
if [[ -f "$CTL_SRC" ]]; then
  install -m 755 "$CTL_SRC" /usr/local/bin/digivice-jellyfin-ctl
fi

status_line() {
  if systemctl is-active --quiet jellyfin.service 2>/dev/null; then
    echo "active"
  elif have_jellyfin; then
    echo "installed"
  else
    echo "missing"
  fi
}

echo "$(status_line)" >/etc/esp-handset/jellyfin.status 2>/dev/null || true

if [[ "$DOCTOR" -eq 1 ]]; then
  echo "=== digivice-jellyfin doctor ==="
  echo "user=$GUI_USER home=$GUI_HOME"
  echo "status=$(status_line)"
  systemctl status jellyfin.service --no-pager -n 8 2>&1 || true
  ss -lntp 2>/dev/null | grep -E ':8096|:8920' || netstat -lntp 2>/dev/null | grep 8096 || true
  echo "media: $GUI_HOME/Videos $GUI_HOME/Music"
  echo "=== end ==="
fi

if have_jellyfin; then
  log "OK — first-run wizard once: http://<pi-ip>:8096 (desktop browser)"
  log "Libraries: $GUI_HOME/Videos · Music · Audiobooks"
  exit 0
fi
log "FAIL — jellyfin not installed"
exit 1
