#!/usr/bin/env bash
# Digivice carts: keep USB automount, kill the "what would you like to do?" dialog.
#
#   sudo digivice-suppress-usb-prompt
#
# PCManFM (Pi OS File Manager) uses autorun=1 by default → prompt on insert.
# Digivice still needs mount_removable=1 so carts appear under /media/…
#
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  if sudo -n true 2>/dev/null; then
    exec sudo -n bash "$0" "$@"
  fi
  echo "[suppress-usb-prompt] need root" >&2
  exit 1
fi

log() { echo "[suppress-usb-prompt] $*"; }

resolve_gui_user() {
  if [[ -n "${DIGI_GUI_USER:-}" ]]; then
    echo "$DIGI_GUI_USER"
    return
  fi
  if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != root ]]; then
    echo "$SUDO_USER"
    return
  fi
  for u in pi isaac; do
    if id "$u" >/dev/null 2>&1; then
      echo "$u"
      return
    fi
  done
  # first non-system login user with a home
  getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 { print $1; exit }'
}

USER_NAME="$(resolve_gui_user)"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6 || echo /home/"$USER_NAME")"
if [[ -z "$USER_NAME" || ! -d "$USER_HOME" ]]; then
  log "WARN: no GUI user home — skip"
  exit 0
fi

patch_pcmanfm_conf() {
  local conf="$1"
  mkdir -p "$(dirname "$conf")"
  if [[ ! -f "$conf" ]]; then
    cat >"$conf" <<'EOF'
[config]
bm_open_method=0

[volume]
mount_on_startup=1
mount_removable=1
autorun=0
EOF
    return
  fi
  # Ensure [volume] section exists, then set keys (keep mounts on)
  if ! grep -q '^\[volume\]' "$conf"; then
    printf '\n[volume]\nmount_on_startup=1\nmount_removable=1\nautorun=0\n' >>"$conf"
  fi
  if grep -q '^autorun=' "$conf"; then
    sed -i 's/^autorun=.*/autorun=0/' "$conf"
  else
    sed -i '/^\[volume\]/a autorun=0' "$conf"
  fi
  if grep -q '^mount_removable=' "$conf"; then
    sed -i 's/^mount_removable=.*/mount_removable=1/' "$conf"
  else
    sed -i '/^\[volume\]/a mount_removable=1' "$conf"
  fi
  if grep -q '^mount_on_startup=' "$conf"; then
    sed -i 's/^mount_on_startup=.*/mount_on_startup=1/' "$conf"
  else
    sed -i '/^\[volume\]/a mount_on_startup=1' "$conf"
  fi
}

CFG_ROOT="$USER_HOME/.config/pcmanfm"
mkdir -p "$CFG_ROOT"
# Common Pi OS / LXDE profile names + anything already present
PROFILES=(LXDE-pi LXDE default rpd-x pi)
shopt -s nullglob
for d in "$CFG_ROOT"/*/; do
  base="$(basename "$d")"
  PROFILES+=("$base")
done
shopt -u nullglob

# unique profiles
declare -A SEEN=()
for p in "${PROFILES[@]}"; do
  [[ -n "${SEEN[$p]:-}" ]] && continue
  SEEN[$p]=1
  conf="$CFG_ROOT/$p/pcmanfm.conf"
  patch_pcmanfm_conf "$conf"
  log "pcmanfm $p → autorun=0 (mount kept)"
done

chown -R "$USER_NAME:$USER_NAME" "$CFG_ROOT" 2>/dev/null || true

# GNOME / some labwc sessions: automount yes, open/ask no
if command -v sudo >/dev/null 2>&1; then
  sudo -u "$USER_NAME" DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
    gsettings set org.gnome.desktop.media-handling automount true 2>/dev/null || true
  sudo -u "$USER_NAME" \
    gsettings set org.gnome.desktop.media-handling automount-open false 2>/dev/null || true
  sudo -u "$USER_NAME" \
    gsettings set org.gnome.desktop.media-handling autorun-never true 2>/dev/null || true
fi

log "done for user $USER_NAME — replug cart or restart session if prompt still appears"
exit 0
