#!/usr/bin/env bash
# Digivice Jellyfin control — start/stop/status/url (+ refresh cart symlink).
#
#   sudo digivice-jellyfin-ctl start|stop|status|url|refresh-cart
#
set +e
set -u

cmd="${1:-status}"

log() { echo "[jellyfin-ctl] $*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  if sudo -n true 2>/dev/null; then
    exec sudo -n bash "$0" "$@"
  fi
  echo "[jellyfin-ctl] need root" >&2
  exit 1
fi

GUI_HOME=""
[[ -f /etc/esp-handset/jellyfin-user-home ]] && GUI_HOME="$(cat /etc/esp-handset/jellyfin-user-home 2>/dev/null | tr -d '\r\n')"
GUI_USER=""
[[ -f /etc/esp-handset/jellyfin-gui-user ]] && GUI_USER="$(cat /etc/esp-handset/jellyfin-gui-user 2>/dev/null | tr -d '\r\n')"
if [[ -z "$GUI_HOME" ]]; then
  GUI_USER="${GUI_USER:-pi}"
  GUI_HOME="$(getent passwd "$GUI_USER" | cut -d: -f6 || echo /home/pi)"
fi

lan_ip() {
  hostname -I 2>/dev/null | awk '{print $1}'
  # fallbacks
  ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}'
}

refresh_cart() {
  mkdir -p /srv/digivice-media
  local mount="" found=""
  for base in /media/"$GUI_USER" /media /run/media/"$GUI_USER"; do
    [[ -d "$base" ]] || continue
    while IFS= read -r -d '' d; do
      if [[ -f "$d/cartridge.json" ]]; then
        found="$d"
        break 2
      fi
    done < <(find "$base" -mindepth 1 -maxdepth 2 -type d -print0 2>/dev/null)
  done
  if [[ -n "$found" ]]; then
    ln -sfn "$found" /srv/digivice-media/cart
    log "cart → $found"
    # readable by jellyfin
    if id jellyfin >/dev/null 2>&1 && command -v setfacl >/dev/null 2>&1; then
      setfacl -R -m u:jellyfin:rX "$found" 2>/dev/null || true
    fi
  else
    rm -f /srv/digivice-media/cart
    log "no cartridge.json mount"
  fi
}

case "$cmd" in
  start)
    refresh_cart
    systemctl start jellyfin.service
    sleep 0.8
    if systemctl is-active --quiet jellyfin.service; then
      ip="$(lan_ip | head -n1)"
      echo "OK running http://${ip:-0.0.0.0}:8096"
      exit 0
    fi
    echo "FAIL start"
    systemctl status jellyfin.service --no-pager -n 15 >&2 || true
    exit 1
    ;;
  stop)
    systemctl stop jellyfin.service
    echo "OK stopped"
    exit 0
    ;;
  status)
    if systemctl is-active --quiet jellyfin.service 2>/dev/null; then
      echo "active"
    elif systemctl list-unit-files jellyfin.service 2>/dev/null | grep -q jellyfin; then
      echo "inactive"
    else
      echo "missing"
    fi
    exit 0
    ;;
  url)
    ip="$(lan_ip | head -n1)"
    if [[ -z "$ip" ]]; then
      echo "http://127.0.0.1:8096"
    else
      echo "http://${ip}:8096"
    fi
    exit 0
    ;;
  refresh-cart)
    refresh_cart
    exit 0
    ;;
  *)
    echo "usage: digivice-jellyfin-ctl start|stop|status|url|refresh-cart" >&2
    exit 2
    ;;
esac
