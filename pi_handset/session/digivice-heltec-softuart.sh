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

install_pigpio_source() {
  log "Building pigpio from source (apt package unavailable)…"
  apt-get install -y git make gcc python3-dev 2>&1 | tail -n 5 || true
  local dir
  dir="$(mktemp -d /tmp/pigpio-build.XXXXXX)"
  if git clone --depth 1 https://github.com/joan2937/pigpio "$dir/pigpio" 2>&1; then
    if make -C "$dir/pigpio" -j"$(nproc 2>/dev/null || echo 2)" 2>&1 \
      && make -C "$dir/pigpio" install 2>&1; then
      ldconfig 2>/dev/null || true
      if [[ -x /usr/local/bin/pigpiod ]]; then
        ln -sf /usr/local/bin/pigpiod /usr/bin/pigpiod 2>/dev/null || true
      fi
      pigpiod 2>/dev/null || true
      log "pigpio source build OK"
      return 0
    fi
  fi
  log "ERROR: pigpio source build failed"
  return 1
}

apt-get update -qq 2>&1 | tail -n 3 || log "WARN: apt-get update failed"
if ! apt-get install -y pigpio python3-pigpio; then
  log "WARN: apt install pigpio python3-pigpio failed"
  if [[ "${DIGIVICE_HELTEC_APT_ONLY:-0}" != "1" ]]; then
    log "trying source build (skipped when DIGIVICE_HELTEC_APT_ONLY=1)"
    install_pigpio_source || true
  fi
fi
systemctl enable --now pigpiod 2>&1 || true
if ! command -v pigpiod >/dev/null 2>&1; then
  if [[ "${DIGIVICE_HELTEC_APT_ONLY:-0}" != "1" ]]; then
    install_pigpio_source || true
  fi
fi
if ! command -v pigpiod >/dev/null 2>&1; then
  log "ERROR: pigpiod binary still missing after apt + source"
elif ! python3 -c "import pigpio" 2>/dev/null; then
  log "ERROR: python3-pigpio import failed — apt: python3-pigpio, or pigpio source build"
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
