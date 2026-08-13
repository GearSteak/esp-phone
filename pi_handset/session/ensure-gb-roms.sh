#!/usr/bin/env bash
# Ensure Digivice Game Boy ROM drop-folder exists (no ROMs bundled).
#
#   digivice-gb-roms-dir
#   → ~/.esp-handset/roms/gb/
#   → /opt/esp-handset/roms/gb/   (optional shared)
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"

resolve_user() {
  if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    echo "$SUDO_USER"; return 0
  fi
  if [[ -n "${DIGI_GUI_USER:-}" && "${DIGI_GUI_USER}" != "root" ]]; then
    echo "$DIGI_GUI_USER"; return 0
  fi
  for u in pi isaac; do
    id "$u" >/dev/null 2>&1 && echo "$u" && return 0
  done
  if [[ "$(id -u)" -ne 0 ]]; then
    id -un
    return 0
  fi
  echo "pi"
}

USER_NAME="$(resolve_user)"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6 || echo /home/"$USER_NAME")"
ROM_USER="$USER_HOME/.esp-handset/roms/gb"
ROM_OPT="$PREFIX/roms/gb"

mkdir -p "$ROM_USER" "$ROM_OPT" 2>/dev/null || true

README_TXT="# Digivice Game Boy / GBC ROMs
#
# Drop your own .gb / .gbc files in this folder, then:
#   Digivice → Games → Game Boy → pick ROM → Play
#
# No commercial ROMs are included. Supply your own legally.
#
# Also scanned: ~/roms/gb  and  /opt/esp-handset/roms/gb
"

for dir in "$ROM_USER" "$ROM_OPT"; do
  [[ -d "$dir" ]] || continue
  if [[ ! -f "$dir/README.txt" ]]; then
    printf '%s\n' "$README_TXT" >"$dir/README.txt" 2>/dev/null || true
  fi
done

if [[ "$(id -u)" -eq 0 ]]; then
  chown -R "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset" 2>/dev/null || true
  chmod 755 "$ROM_USER" "$ROM_OPT" 2>/dev/null || true
fi

echo "GB ROM folder ready:"
echo "  $ROM_USER"
echo "Copy ROMs with (from your PC):"
echo "  scp game.gb ${USER_NAME}@<pi-ip>:${ROM_USER}/"
exit 0
