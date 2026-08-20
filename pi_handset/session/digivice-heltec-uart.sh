#!/usr/bin/env bash
# Heltec Tracker notify panel on Pi GPIO UART (externally powered Heltec).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CFG="/boot/firmware/config.txt"
[[ -f "$CFG" ]] || CFG="/boot/config.txt"
CMDLINE="/boot/firmware/cmdline.txt"
[[ -f "$CMDLINE" ]] || CMDLINE="/boot/cmdline.txt"
ENV_FILE="/etc/esp-handset/env"

log() { echo "[heltec-uart] $*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

log "Enable Pi UART on GPIO 14/15 (Heltec RX/TX)"
if [[ -f "$CFG" ]]; then
  grep -q '^enable_uart=1' "$CFG" 2>/dev/null || echo 'enable_uart=1' >>"$CFG"
  grep -q '^dtoverlay=disable-bt' "$CFG" 2>/dev/null || echo 'dtoverlay=disable-bt' >>"$CFG"
fi

log "Remove serial console from cmdline (frees /dev/serial0)"
if [[ -f "$CMDLINE" ]]; then
  sed -i \
    -e 's/\console=serial0[^ ]*//g' \
    -e 's/\console=ttyAMA0[^ ]*//g' \
    -e 's/\console=ttyS0[^ ]*//g' \
    "$CMDLINE"
fi

systemctl disable --now serial-getty@serial0.service 2>/dev/null || true
systemctl disable --now serial-getty@ttyAMA0.service 2>/dev/null || true
systemctl disable --now serial-getty@ttyS0.service 2>/dev/null || true

mkdir -p /etc/esp-handset
touch "$ENV_FILE"
grep -q '^ESP_BRIDGE_UART=' "$ENV_FILE" 2>/dev/null || echo 'ESP_BRIDGE_UART=1' >>"$ENV_FILE"
grep -q '^ESP_BRIDGE_PORT=' "$ENV_FILE" 2>/dev/null || echo 'ESP_BRIDGE_PORT=/dev/esp-bridge-uart' >>"$ENV_FILE"

for src in /dev/serial0 /dev/ttyAMA0 /dev/ttyS0; do
  if [[ -e "$src" ]]; then
    ln -sfn "$src" /dev/esp-bridge-uart
    log "symlink /dev/esp-bridge-uart → $src"
    break
  fi
done

log "Done — reboot. Heltec: Pi TX→Heltec RX, Pi RX←Heltec TX, common GND, Heltec on battery."
log "WARN: if SIM7600 uses GPIO UART, use USB for modem OR Heltec on USB instead."
