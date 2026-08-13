#!/usr/bin/env bash
# Digivice Game Boy / GBC launcher — SAFE stub.
#
# External RetroArch/mgba handoff blanked the SPI panel and could kill/relaunch
# Digivice in a loop. Play is disabled in the UI until we have an in-process emu.
#
# If somehow invoked: refuse, restore phone mode, return to Digivice.
# Override (dev only):  DIGIVICE_GB_FORCE=1 digivice-gb /path/to.gb
# Kill switch file:     ~/.esp-handset/gb-disabled  (always refuses)
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
LOG_DIR="${HOME:-/tmp}/.esp-handset"
mkdir -p "$LOG_DIR" /etc/esp-handset 2>/dev/null || true
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

clear_spi_locks() {
  rm -f /tmp/digivice-st7789.lock /run/digivice-st7789.lock \
    "${HOME}/.esp-handset/st7789.lock" 2>/dev/null || true
}

stop_spi_mirror() {
  for m in \
    /usr/local/bin/digivice-desktop-mirror \
    "$PREFIX/session/desktop-spi-mirror.sh"
  do
    if [[ -f "$m" || -x "$m" ]]; then
      bash "$m" stop >>"$LOG" 2>&1 || true
      break
    fi
  done
  pkill -TERM -f "desktop_spi_mirror.py" 2>/dev/null || true
  sleep 0.2
  pkill -KILL -f "desktop_spi_mirror.py" 2>/dev/null || true
  clear_spi_locks
}

return_to_digivice() {
  write_mode phone
  rm -f /run/digivice-gb-rom 2>/dev/null || true
  stop_spi_mirror
  sleep 0.3
  if pgrep -f "handset_app.py" >/dev/null 2>&1; then
    log "Digivice already running — done"
    exit 0
  fi
  if command -v handset-phone >/dev/null 2>&1; then
    log "Returning to Digivice (no emu)"
    exec handset-phone
  fi
  exit 0
}

# Single instance — a second digivice-gb must not kill Digivice
LOCK=/run/digivice-gb.lock
exec 9>"$LOCK" 2>/dev/null || exec 9>"${LOG_DIR}/digivice-gb.lock"
if ! flock -n 9; then
  log "Another digivice-gb holds the lock — abort (no Digivice kill)"
  exit 0
fi

log "=== digivice-gb (safe stub) ==="

# Always refuse external emu unless explicitly forced AND kill-switch absent
if [[ -f "${HOME}/.esp-handset/gb-disabled" ]] \
  || [[ -f /etc/esp-handset/gb-disabled ]]; then
  log "gb-disabled present — refuse emu"
  return_to_digivice
fi

if [[ "${DIGIVICE_GB_FORCE:-0}" != "1" ]]; then
  log "External GB emu disabled (SPI handoff unsafe). UI Play is a no-op."
  log "Dev override: DIGIVICE_GB_FORCE=1 digivice-gb <rom>"
  # Seed kill switch so accidental / old wrappers stay off
  touch "${HOME}/.esp-handset/gb-disabled" 2>/dev/null || true
  return_to_digivice
fi

# --- force path only (dev) — still never kill Digivice ---
ROM="${1:-}"
if [[ -z "$ROM" && -f /run/digivice-gb-rom ]]; then
  ROM="$(tr -d '\r\n' </run/digivice-gb-rom)"
fi
if [[ -z "$ROM" && -f "${HOME}/.esp-handset/gb-rom" ]]; then
  ROM="$(tr -d '\r\n' <"${HOME}/.esp-handset/gb-rom")"
fi
if [[ -z "$ROM" || ! -f "$ROM" ]]; then
  log "FORCE but ROM missing"
  return_to_digivice
fi

export DISPLAY="${DISPLAY:-:0}"
log "FORCE emu ROM=$ROM — waiting for Digivice to exit on its own (no kill)"
write_mode gb
for i in $(seq 1 40); do
  if ! pgrep -f "handset_app.py" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done
if pgrep -f "handset_app.py" >/dev/null 2>&1; then
  log "Digivice still up — abort FORCE (will not kill UI)"
  write_mode phone
  exit 0
fi

stop_spi_mirror
# userspace mirror for X11 emu
if [[ -f /etc/esp-handset/spi-userspace ]] || [[ -e /dev/spidev0.0 ]]; then
  m=/usr/local/bin/digivice-desktop-mirror
  [[ -f "$m" ]] || m="$PREFIX/session/desktop-spi-mirror.sh"
  if [[ -f "$m" ]]; then
    bash "$m" start >>"$LOG" 2>&1 || true
  fi
fi

CFG="${HOME}/.esp-handset/retroarch-gb.cfg"
mkdir -p "${HOME}/.esp-handset"
cat >"$CFG" <<'EOF'
video_driver = "sdl2"
video_fullscreen = "true"
video_windowed_fullscreen = "true"
video_smooth = "false"
input_player1_a = "x"
input_player1_b = "z"
input_player1_start = "enter"
input_player1_select = "rshift"
input_exit_emulator = "nul"
EOF

CORE=""
for c in \
  /usr/lib/aarch64-linux-gnu/libretro/gambatte_libretro.so \
  /usr/lib/arm-linux-gnueabihf/libretro/gambatte_libretro.so \
  /usr/lib/*/libretro/gambatte_libretro.so
do
  for hit in $c; do
    [[ -f "$hit" ]] && CORE="$hit" && break 2
  done
done

if command -v retroarch >/dev/null 2>&1 && [[ -n "$CORE" ]]; then
  log "FORCE RetroArch $CORE"
  retroarch -L "$CORE" --config "$CFG" --fullscreen "$ROM" || true
elif command -v mgba-sdl >/dev/null 2>&1; then
  mgba-sdl -f "$ROM" || true
else
  log "No emu binary"
fi

return_to_digivice
