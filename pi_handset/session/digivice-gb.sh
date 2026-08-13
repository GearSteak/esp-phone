#!/usr/bin/env bash
# Digivice Game Boy / GBC launcher.
# Digivice owns the 2" SPI panel — hand it off cleanly, run the emu, then
# always bring Digivice back (EXIT trap). Bad handoff blanks the panel forever.
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

# Ensure drop-folder + README exist (idempotent)
if [[ -x /usr/local/bin/digivice-gb-roms-dir ]]; then
  /usr/local/bin/digivice-gb-roms-dir >/dev/null 2>&1 || true
elif [[ -f "$PREFIX/session/ensure-gb-roms.sh" ]]; then
  bash "$PREFIX/session/ensure-gb-roms.sh" >/dev/null 2>&1 || true
fi

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

write_mode() {
  local m="$1"
  echo "$m" >/etc/esp-handset/ui_mode 2>/dev/null || true
  echo "$m" >"${HOME}/.esp-handset/session_mode" 2>/dev/null || true
  for h in /home/*/.esp-handset; do
    [[ -d "$h" ]] && echo "$m" >"$h/session_mode" 2>/dev/null || true
  done
}

spi_drm_mode() {
  if [[ -f /etc/esp-handset/spi-mode ]] \
    && grep -qi instructables /etc/esp-handset/spi-mode 2>/dev/null; then
    return 0
  fi
  if [[ -f /etc/esp-handset/display-mode ]] \
    && grep -qi instructables /etc/esp-handset/display-mode 2>/dev/null; then
    return 0
  fi
  [[ "${ESP_HANDSET_SPI_BACKEND:-}" == "drm" ]] && return 0
  if [[ -f /etc/esp-handset/spi-backend ]] \
    && grep -qi '^drm' /etc/esp-handset/spi-backend 2>/dev/null; then
    return 0
  fi
  if [[ -f /etc/esp-handset/env ]] \
    && grep -q 'ESP_HANDSET_SPI_BACKEND=drm' /etc/esp-handset/env 2>/dev/null; then
    return 0
  fi
  return 1
}

spi_userspace_on() {
  if spi_drm_mode; then
    return 1
  fi
  if [[ -f /etc/esp-handset/spi-userspace ]] \
    || [[ "${ESP_HANDSET_SPI_BACKEND:-}" == "userspace" ]] \
    || grep -q 'ESP_HANDSET_SPI_BACKEND=userspace' /etc/esp-handset/env 2>/dev/null; then
    return 0
  fi
  # spidev present + no DRM flag → treat as userspace (Digivice paints SPI)
  if [[ -e /dev/spidev0.0 || -e /dev/spidev0.1 ]]; then
    return 0
  fi
  return 1
}

mirror_bin() {
  for m in \
    /usr/local/bin/digivice-desktop-mirror \
    "$PREFIX/session/desktop-spi-mirror.sh" \
    "$(dirname "$0")/desktop-spi-mirror.sh"
  do
    if [[ -f "$m" || -x "$m" ]]; then
      echo "$m"
      return 0
    fi
  done
  echo ""
}

clear_spi_locks() {
  rm -f /tmp/digivice-st7789.lock /run/digivice-st7789.lock \
    "${HOME}/.esp-handset/st7789.lock" 2>/dev/null || true
}

stop_spi_mirror() {
  local m
  m="$(mirror_bin)"
  if [[ -n "$m" ]]; then
    bash "$m" stop >>"$LOG" 2>&1 || true
  fi
  pkill -TERM -f "desktop_spi_mirror.py" 2>/dev/null || true
  sleep 0.3
  pkill -KILL -f "desktop_spi_mirror.py" 2>/dev/null || true
  clear_spi_locks
}

start_spi_mirror() {
  local m
  m="$(mirror_bin)"
  if [[ -z "$m" ]]; then
    log "WARN: desktop-spi-mirror.sh missing"
    return 1
  fi
  clear_spi_locks
  sleep 0.4
  bash "$m" start >>"$LOG" 2>&1 || true
  sleep 0.6
  if bash "$m" status >>"$LOG" 2>&1; then
    log "SPI mirror running (desktop → 2\" panel)"
    return 0
  fi
  log "WARN: SPI mirror failed — retry"
  clear_spi_locks
  sleep 0.5
  bash "$m" start >>"$LOG" 2>&1 || true
  sleep 0.8
  bash "$m" status >>"$LOG" 2>&1
}

activate_spi_drm() {
  local s
  for s in \
    /usr/local/bin/digivice-spi-drm-activate \
    "$PREFIX/session/spi-drm-activate.sh"
  do
    if [[ -x "$s" || -f "$s" ]]; then
      log "SPI DRM activate: $s"
      bash "$s" >>"$LOG" 2>&1 || true
      return 0
    fi
  done
  return 1
}

# After Digivice has exited: put something on the 2\" panel for the emu
prepare_panel_for_emu() {
  if spi_drm_mode; then
    log "panel: DRM/Instructables — activate SPI head"
    stop_spi_mirror
    activate_spi_drm || true
    return 0
  fi
  if spi_userspace_on; then
    log "panel: userspace SPI — start desktop mirror AFTER Digivice exit"
    # Digivice must already be gone; do NOT start mirror while it holds SPI
    start_spi_mirror || log "ERROR: mirror down — SPI may stay blank until Digivice returns"
    return 0
  fi
  log "panel: no SPI userspace/DRM flags — emu on X11 only"
}

# Free SPI so Digivice can paint again
release_panel_for_digivice() {
  stop_spi_mirror
  if spi_drm_mode; then
    activate_spi_drm || true
  fi
  clear_spi_locks
  sleep 0.6
}

return_to_digivice() {
  log "Returning to Digivice…"
  write_mode phone
  rm -f /run/digivice-gb-rom 2>/dev/null || true
  release_panel_for_digivice
  # Prefer handset-session so SPI/layout matches normal boot
  if command -v handset-phone >/dev/null 2>&1; then
    exec handset-phone
  fi
  if [[ -x /usr/local/bin/handset-session ]]; then
    exec /usr/local/bin/handset-session phone
  fi
  if [[ -f "$PREFIX/session/handset-session.sh" ]]; then
    exec bash "$PREFIX/session/handset-session.sh" phone
  fi
  log "FATAL: handset-phone missing"
  exit 1
}

# Always recover Digivice even if emu crashes / script is interrupted
RECOVERED=0
on_exit() {
  local ec=$?
  if [[ "$RECOVERED" -eq 1 ]]; then
    return 0
  fi
  RECOVERED=1
  log "cleanup (exit=$ec) — force Digivice recovery"
  write_mode phone
  # Don't leave emu fighting Digivice for X11/SPI
  pkill -TERM -f 'retroarch|mgba-sdl|mgba-qt|\bmgba\b' 2>/dev/null || true
  sleep 0.2
  release_panel_for_digivice
  # If Digivice already up (or we're about to exec), skip
  if pgrep -f "handset_app.py" >/dev/null 2>&1; then
    log "Digivice already running"
    return 0
  fi
  # Background relaunch if we can't exec (already in exit path)
  if command -v handset-phone >/dev/null 2>&1; then
    nohup handset-phone >>"$LOG" 2>&1 &
    log "spawned handset-phone pid=$!"
  fi
}
trap on_exit EXIT INT TERM

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
  RECOVERED=1
  return_to_digivice
fi

CFG_DIR="${HOME}/.esp-handset"
CFG="$CFG_DIR/retroarch-gb.cfg"
mkdir -p "$CFG_DIR"

# Prefer SDL2 on X11 — avoid KMS/DRM drivers that can blank the SPI panel
cat >"$CFG" <<'EOF'
video_driver = "sdl2"
video_fullscreen = "true"
video_windowed_fullscreen = "true"
video_smooth = "false"
video_font_enable = "false"
video_vsync = "true"
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
log "ROM=$ROM DISPLAY=$DISPLAY HOME=$HOME"
if spi_drm_mode; then
  log "SPI mode=drm"
elif spi_userspace_on; then
  log "SPI mode=userspace"
else
  log "SPI mode=unknown"
fi

# 1) Set GB button map BEFORE Digivice exits (daemon polls mode file)
write_mode gb

# 2) Wait for Digivice to release SPI (UI quits after launching us)
log "Waiting for Digivice UI to exit (SPI release)…"
for i in $(seq 1 50); do
  if ! pgrep -f "handset_app.py" >/dev/null 2>&1; then
    log "Digivice exited after ${i}×0.2s"
    break
  fi
  sleep 0.2
done
if pgrep -f "handset_app.py" >/dev/null 2>&1; then
  log "Digivice still up — soft-stop so SPI can be handed off"
  pkill -TERM -f "handset_app.py" 2>/dev/null || true
  sleep 1.2
fi
if pgrep -f "handset_app.py" >/dev/null 2>&1; then
  log "Digivice stubborn — KILL (last resort)"
  pkill -KILL -f "handset_app.py" 2>/dev/null || true
  sleep 0.8
fi
clear_spi_locks
sleep 0.5

# 3) Only NOW put desktop/emu pixels on the 2\" panel
prepare_panel_for_emu

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
    log "RetroArch core=$CORE (sdl2 fullscreen)"
    # Explicit SDL2 video; fall back without --appendconfig quirks
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

# Normal path: disable EXIT trap relaunch duplicate, then exec Digivice
RECOVERED=1
trap - EXIT INT TERM
return_to_digivice
