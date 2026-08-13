#!/usr/bin/env bash
# Emergency: stop Game Boy launcher / emu loop and bring Digivice back.
#   digivice-stop-gb
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
LOG_DIR="${HOME:-/tmp}/.esp-handset"
mkdir -p "$LOG_DIR" /etc/esp-handset 2>/dev/null || true
LOG="$LOG_DIR/gb.log"

log() { echo "[$(date '+%H:%M:%S')] stop-gb: $*" | tee -a "$LOG"; }

log "=== digivice-stop-gb ==="

# Kill switch so digivice-gb refuses to run until removed
touch "$LOG_DIR/gb-disabled" 2>/dev/null || true
for h in /home/*/.esp-handset; do
  [[ -d "$h" ]] && touch "$h/gb-disabled" 2>/dev/null || true
done

# Nuke launcher + emulators (do this BEFORE starting Digivice)
pkill -9 -f '/usr/local/bin/digivice-gb' 2>/dev/null || true
pkill -9 -f 'digivice-gb.sh' 2>/dev/null || true
pkill -9 -f 'retroarch' 2>/dev/null || true
pkill -9 -f 'mgba-sdl' 2>/dev/null || true
pkill -9 -f 'mgba-qt' 2>/dev/null || true
pkill -9 -f '/mgba' 2>/dev/null || true
sleep 0.3

# Free SPI
for m in \
  /usr/local/bin/digivice-desktop-mirror \
  "$PREFIX/session/desktop-spi-mirror.sh"
do
  if [[ -f "$m" ]]; then
    bash "$m" stop >>"$LOG" 2>&1 || true
    break
  fi
done
pkill -9 -f 'desktop_spi_mirror.py' 2>/dev/null || true
rm -f /tmp/digivice-st7789.lock /run/digivice-st7789.lock \
  /run/digivice-gb-rom "$LOG_DIR/gb-rom" 2>/dev/null || true
for h in /home/*/.esp-handset; do
  rm -f "$h/gb-rom" 2>/dev/null || true
done

# Force phone mode (gb mode blocks Home→Digivice)
echo phone >/etc/esp-handset/ui_mode 2>/dev/null || true
echo phone >"$LOG_DIR/session_mode" 2>/dev/null || true
for h in /home/*/.esp-handset; do
  [[ -d "$h" ]] && echo phone >"$h/session_mode" 2>/dev/null || true
done

sleep 0.5
log "Starting Digivice…"
if command -v handset-phone >/dev/null 2>&1; then
  # Prefer GUI user
  if [[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    u="$SUDO_USER"
    h="$(getent passwd "$u" | cut -d: -f6)"
    sudo -u "$u" -H env HOME="$h" DISPLAY="${DISPLAY:-:0}" \
      XAUTHORITY="${XAUTHORITY:-$h/.Xauthority}" \
      nohup handset-phone >>"$h/.esp-handset/handset.log" 2>&1 &
  else
    nohup handset-phone >>"$LOG_DIR/handset.log" 2>&1 &
  fi
  log "handset-phone spawned"
else
  log "ERROR: handset-phone missing"
  exit 1
fi

echo "GB stopped. Digivice should return."
echo "Kill switch: ~/.esp-handset/gb-disabled  (delete to re-enable later)"
