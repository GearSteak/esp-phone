#!/usr/bin/env bash
# Start pigpiod for Heltec soft-UART — must run as root (GPIO). No password prompts.
set +e
set -u

log() { echo "[ensure-pigpiod] $*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  if sudo -n true 2>/dev/null; then
    exec sudo -n env ESP_HANDSET_PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}" \
      /usr/local/bin/digivice-ensure-pigpiod "$@"
  fi
  if [[ -f /opt/esp-handset/session/digivice-ensure-pigpiod.sh ]]; then
    exec sudo -n env ESP_HANDSET_PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}" \
      bash /opt/esp-handset/session/digivice-ensure-pigpiod.sh "$@"
  fi
  log "need root — run: sudo digivice-ensure-pigpiod"
  exit 1
fi

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
UNIT_SRC="$PREFIX/session/digivice-pigpiod.service"
UNIT_DST="/etc/systemd/system/digivice-pigpiod.service"

pigpio_connected() {
  python3 -c "import pigpio; pi=pigpio.pi(); ok=pi.connected; pi.stop(); import sys; sys.exit(0 if ok else 1)" 2>/dev/null
}

find_pigpiod() {
  for bin in /usr/local/bin/pigpiod /usr/bin/pigpiod pigpiod; do
    if [[ -x "$bin" ]] || command -v "$bin" >/dev/null 2>&1; then
      command -v "$bin" 2>/dev/null || echo "$bin"
      return 0
    fi
  done
  return 1
}

install_unit() {
  if [[ -f "$UNIT_SRC" ]]; then
    install -m 644 "$UNIT_SRC" "$UNIT_DST"
  elif [[ ! -f "$UNIT_DST" ]]; then
    log "ERROR: $UNIT_SRC missing"
    return 1
  fi
  systemctl daemon-reload 2>/dev/null || true
  systemctl enable digivice-pigpiod.service 2>/dev/null || true
  return 0
}

if pigpio_connected; then
  log "already connected"
  exit 0
fi

install_unit || true
systemctl start digivice-pigpiod.service 2>/dev/null || true
sleep 0.5
if pigpio_connected; then
  log "started via digivice-pigpiod.service"
  exit 0
fi

# Fallback: stock unit name from apt
systemctl enable --now pigpiod 2>/dev/null || true
systemctl start pigpiod 2>/dev/null || true
sleep 0.4
if pigpio_connected; then
  log "started via pigpiod.service"
  exit 0
fi

bin="$(find_pigpiod || true)"
if [[ -z "$bin" ]]; then
  log "ERROR: pigpiod binary not found"
  exit 1
fi

pkill -x pigpiod 2>/dev/null || true
sleep 0.2
"$bin" 2>/dev/null &
sleep 0.5
if pigpio_connected; then
  log "started direct ($bin)"
  exit 0
fi

log "ERROR: pigpiod still not connected"
exit 1
