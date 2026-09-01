#!/usr/bin/env bash
# Digivice Heltec soft-UART (battery powered) — NOT USB, NOT serial0, NOT CardKB I2C.
#
#   Pi pin 16 BCM23 TX  →  Heltec GPIO44 RX
#   Pi pin 18 BCM24 RX  ←  Heltec GPIO43 TX
#   Pi GND              →  Heltec GND
#   Heltec power        =  LiPo only (no USB to Pi — pops the polyfuse)
set +e
set -u

ENV_FILE="/etc/esp-handset/env"

log() { echo "[heltec-softuart] $*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

log "Install pigpio for bit-bang UART"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq 2>&1 | tail -n 3 || log "WARN: apt-get update failed"
if ! apt-get install -y pigpio python3-pigpio; then
  log "ERROR: apt install pigpio python3-pigpio failed — run: sudo apt-get update && sudo apt-get install -y pigpio python3-pigpio"
fi
systemctl enable --now pigpiod 2>&1 || true
if ! command -v pigpiod >/dev/null 2>&1; then
  log "ERROR: pigpiod binary still missing after apt install"
elif ! python3 -c "import pigpio" 2>/dev/null; then
  log "ERROR: python3-pigpio import failed after apt install"
elif ! python3 -c "import pigpio; pi=pigpio.pi(); ok=pi.connected; pi.stop(); import sys; sys.exit(0 if ok else 1)" 2>/dev/null; then
  log "WARN: pigpiod not connected — trying systemctl start pigpiod"
  systemctl start pigpiod 2>/dev/null || pigpiod 2>/dev/null || true
else
  log "pigpio OK (daemon connected)"
fi

mkdir -p /etc/esp-handset
touch "$ENV_FILE"
# Clear conflicting bridge modes
sed -i \
  -e '/^ESP_BRIDGE_UART=/d' \
  -e '/^ESP_BRIDGE_PORT=\/dev\/esp-bridge/d' \
  -e '/^ESP_BRIDGE_SOFTUART=/d' \
  -e '/^ESP_BRIDGE_SOFT_TX=/d' \
  -e '/^ESP_BRIDGE_SOFT_RX=/d' \
  -e '/^ESP_BRIDGE_SOFT_BAUD=/d' \
  "$ENV_FILE" 2>/dev/null || true

cat >>"$ENV_FILE" <<'EOF'
ESP_BRIDGE_SOFTUART=1
ESP_BRIDGE_SOFT_TX=23
ESP_BRIDGE_SOFT_RX=24
ESP_BRIDGE_SOFT_BAUD=9600
EOF

# Ensure handset session loads /etc/esp-handset/env
log "Wrote soft-UART env → $ENV_FILE"
log "Wire: Pi16→Heltec44, Pi18←Heltec43, GND, Heltec on LiPo — NO USB to Pi"
log "Flash: pio run -e heltec-wireless-tracker-gateway -t upload  (USB only while flashing, then unplug)"
log "Reboot Digivice session after: sudo bash pi_handset/session/full-update.sh"
