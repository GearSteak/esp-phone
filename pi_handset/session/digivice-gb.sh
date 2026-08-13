#!/usr/bin/env bash
# Digivice Game Boy / GBC launcher.
# Sets button mode=gb, runs RetroArch (gambatte) or mgba, then returns to Digivice.
#
#   digivice-gb /path/to/game.gb
#   digivice-gb              # reads /run/digivice-gb-rom or ~/.esp-handset/gb-rom
#
# Controls (digi-buttons-inputd mode gb):
#   D-pad · Confirm=A · Back=B · Home=Start · Home+Confirm=Select
#   Confirm+Back+Home (hold ~0.5s) = exit
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
LOG_DIR="${HOME:-/tmp}/.esp-handset"
mkdir -p "$LOG_DIR" /etc/esp-handset "$HOME/.esp-handset/roms/gb" 2>/dev/null || true
LOG="$LOG_DIR/gb.log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

write_mode() {
  local m="$1"
  echo "$m" >/etc/esp-handset/ui_mode 2>/dev/null || true
  echo "$m" >"${HOME}/.esp-handset/session_mode" 2>/dev/null || true
  for h in /home/*/.esp-handset; do
    [[ -d "$h" ]] && echo "$m" >"$h/session_mode" 2>/dev/null || true
  done
}

ROM="${1:-}"
if [[ -z "$ROM" && -f /run/digivice-gb-rom ]]; then
  ROM="$(tr -d '\r\n' </run/digivice-gb-rom)"
fi
if [[ -z "$ROM" && -f "${HOME}/.esp-handset/gb-rom" ]]; then
  ROM="$(tr -d '\r\n' <"${HOME}/.esp-handset/gb-rom")"
fi

if [[ -z "$ROM" || ! -f "$ROM" ]]; then
  log "ERROR: ROM missing: ${ROM:-"(none)"}"
  log "Put .gb/.gbc in ~/.esp-handset/roms/gb/ then pick from Games → Game Boy"
  write_mode phone
  exec handset-phone
fi

CFG_DIR="${HOME}/.esp-handset"
CFG="$CFG_DIR/retroarch-gb.cfg"
mkdir -p "$CFG_DIR"

# Minimal RetroArch config matching Digivice GB key map
cat >"$CFG" <<'EOF'
video_fullscreen = "true"
video_windowed_fullscreen = "true"
video_smooth = "false"
video_font_enable = "false"
menu_driver = "rgui"
input_autodetect_enable = "true"
input_player1_up = "up"
input_player1_down = "down"
input_player1_left = "left"
input_player1_right = "right"
input_player1_a = "x"
input_player1_b = "z"
input_player1_start = "enter"
input_player1_select = "rshift"
input_exit_emulator = "nul"
input_toggle_fast_forward = "nul"
input_menu_toggle = "nul"
input_load_state = "nul"
input_save_state = "nul"
pause_nonactive = "false"
EOF

export DISPLAY="${DISPLAY:-:0}"
if [[ -z "${XAUTHORITY:-}" ]]; then
  for a in "${HOME}/.Xauthority" /home/*/.Xauthority; do
    if [[ -f "$a" ]]; then
      export XAUTHORITY="$a"
      break
    fi
  done
fi

log "=== digivice-gb ==="
log "ROM=$ROM DISPLAY=$DISPLAY"

# SPI userspace: mirror X11 desktop to the 2\" panel while Digivice is down
if [[ -f /etc/esp-handset/spi-userspace ]] || [[ -f /etc/esp-handset/spi-backend ]]; then
  for m in \
    /usr/local/bin/digivice-desktop-mirror \
    "$PREFIX/session/desktop-spi-mirror.sh"
  do
    if [[ -f "$m" || -x "$m" ]]; then
      log "SPI mirror start: $m"
      bash "$m" start >>"$LOG" 2>&1 || true
      break
    fi
  done
fi

write_mode gb
log "Waiting for Digivice UI to exit…"
for i in $(seq 1 40); do
  if ! pgrep -f "handset_app.py" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done
sleep 0.4

CORE=""
for c in \
  /usr/lib/aarch64-linux-gnu/libretro/gambatte_libretro.so \
  /usr/lib/arm-linux-gnueabihf/libretro/gambatte_libretro.so \
  /usr/lib/libretro/gambatte_libretro.so \
  /usr/lib/*/libretro/gambatte_libretro.so \
  /usr/lib/aarch64-linux-gnu/libretro/mgba_libretro.so \
  /usr/lib/arm-linux-gnueabihf/libretro/mgba_libretro.so \
  /usr/lib/libretro/mgba_libretro.so
do
  # shellcheck disable=SC2086
  for hit in $c; do
    if [[ -f "$hit" ]]; then
      CORE="$hit"
      break 2
    fi
  done
done

run_emu() {
  if command -v retroarch >/dev/null 2>&1 && [[ -n "$CORE" ]]; then
    log "RetroArch core=$CORE"
    retroarch -L "$CORE" --config "$CFG" --fullscreen "$ROM"
    return $?
  fi
  if command -v mgba-sdl >/dev/null 2>&1; then
    log "mgba-sdl"
    mgba-sdl -f "$ROM"
    return $?
  fi
  if command -v mgba-qt >/dev/null 2>&1; then
    log "mgba-qt"
    mgba-qt "$ROM"
    return $?
  fi
  if command -v mgba >/dev/null 2>&1; then
    log "mgba"
    mgba -f "$ROM"
    return $?
  fi
  return 127
}

run_emu
rc=$?
log "emulator exit rc=$rc"

if [[ $rc -eq 127 ]]; then
  log "No emulator installed. On the Pi run:"
  log "  sudo apt-get install -y retroarch libretro-gambatte"
  log "  # or: sudo apt-get install -y mgba-sdl"
fi

write_mode phone
rm -f /run/digivice-gb-rom 2>/dev/null || true

# Stop desktop SPI mirror before Digivice takes the panel again
if [[ -f /etc/esp-handset/spi-userspace ]] || [[ -f /etc/esp-handset/spi-backend ]]; then
  for m in \
    /usr/local/bin/digivice-desktop-mirror \
    "$PREFIX/session/desktop-spi-mirror.sh"
  do
    if [[ -f "$m" || -x "$m" ]]; then
      bash "$m" stop >>"$LOG" 2>&1 || true
      break
    fi
  done
fi

sleep 0.5
log "Returning to Digivice…"
exec handset-phone
