#!/usr/bin/env bash
# Ensure Digivice ROM drop-folders exist (no ROMs bundled).
#
#   digivice-gb-roms-dir
#   → ~/.esp-handset/roms/{gb,nes,sms,genesis,gba,chip8}/
#   → /opt/esp-handset/roms/...   (optional shared)
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

SYSTEMS="gb nes sms genesis gba chip8"
EXTS_gb=".gb .gbc"
EXTS_nes=".nes"
EXTS_sms=".sms .gg"
EXTS_genesis=".md .gen"
EXTS_gba=".gba"
EXTS_chip8=".ch8 .c8"

readme_for() {
  local sys="$1"
  local exts="$2"
  cat <<EOF
# Digivice ${sys} ROMs
#
# Drop your own ${exts} files in this folder, then:
#   Digivice → Games → pick system → Play
#
# No commercial ROMs are included. Supply your own legally.
#
# Also scanned: ~/roms/${sys}  and  /opt/esp-handset/roms/${sys}
EOF
}

for sys in $SYSTEMS; do
  ROM_USER="$USER_HOME/.esp-handset/roms/$sys"
  ROM_OPT="$PREFIX/roms/$sys"
  mkdir -p "$ROM_USER" "$ROM_OPT" 2>/dev/null || true
  exts_var="EXTS_${sys}"
  exts="${!exts_var}"
  txt="$(readme_for "$sys" "$exts")"
  for dir in "$ROM_USER" "$ROM_OPT"; do
    [[ -d "$dir" ]] || continue
    if [[ ! -f "$dir/README.txt" ]]; then
      printf '%s\n' "$txt" >"$dir/README.txt" 2>/dev/null || true
    fi
  done
done

if [[ "$(id -u)" -eq 0 ]]; then
  chown -R "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset" 2>/dev/null || true
  chmod -R a+rX "$PREFIX/roms" 2>/dev/null || true
fi

echo "ROM folders ready under:"
echo "  $USER_HOME/.esp-handset/roms/{gb,nes,sms,genesis,gba,chip8}/"
echo "Copy with (from your PC):"
echo "  scp game.gb ${USER_NAME}@<pi-ip>:${USER_HOME}/.esp-handset/roms/gb/"
exit 0
