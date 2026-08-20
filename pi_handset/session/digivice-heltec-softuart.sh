#!/usr/bin/env bash
# Digivice Heltec soft-UART (battery powered) — NOT USB, NOT serial0, NOT CardKB I2C.
#
#   Pi pin 16 BCM23 TX  →  Heltec GPIO44 RX
#   Pi pin 18 BCM24 RX  ←  Heltec GPIO43 TX
#   Pi GND              →  Heltec GND
#   Heltec power        =  LiPo only (no USB to Pi — pops the polyfuse)
set -euo pipefail

ENV_FILE="/etc/esp-handset/env"

log() { echo "[heltec-softuart] $*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

log "Install pigpio for bit-bang UART"
apt-get install -y pigpio python3-pigpio 2>/dev/null || true
systemctl enable --now pigpiod 2>/dev/null || true

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
