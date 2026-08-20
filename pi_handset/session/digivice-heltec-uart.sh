#!/usr/bin/env bash
# Heltec Tracker on Pi GPIO UART — ONLY if SIM7600 is NOT using /dev/serial0.
#
# Digivice preferred stack (USB audio + UART modem):
#   do NOT run this — put Heltec on USB via a hub instead.
#   See docs/HELTEC_UART_NOTIFY.md
set -euo pipefail

CFG="/boot/firmware/config.txt"
[[ -f "$CFG" ]] || CFG="/boot/config.txt"
CMDLINE="/boot/firmware/cmdline.txt"
[[ -f "$CMDLINE" ]] || CMDLINE="/boot/cmdline.txt"
ENV_FILE="/etc/esp-handset/env"
MODEM_BACKEND="/etc/esp-handset/modem-backend"

log() { echo "[heltec-uart] $*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

backend="$(tr -d '[:space:]' <"$MODEM_BACKEND" 2>/dev/null || true)"
backend="${backend,,}"
if [[ "$backend" == "uart" ]]; then
  log "ABORT: modem-backend=uart — /dev/serial0 belongs to SIM7600."
  log "Use Heltec on USB-C via a hub with the audio stick (docs/HELTEC_UART_NOTIFY.md)."
  exit 1
fi

log "WARNING: This claims GPIO UART for Heltec. Modem must use USB or stay unplugged."
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
# Strip any prior UART-bridge env if re-running after switching stacks
sed -i '/^ESP_BRIDGE_UART=/d;/^ESP_BRIDGE_PORT=\/dev\/esp-bridge-uart/d' "$ENV_FILE" 2>/dev/null || true
echo 'ESP_BRIDGE_UART=1' >>"$ENV_FILE"
echo 'ESP_BRIDGE_PORT=/dev/esp-bridge-uart' >>"$ENV_FILE"

for src in /dev/serial0 /dev/ttyAMA0 /dev/ttyS0; do
  if [[ -e "$src" ]]; then
    ln -sfn "$src" /dev/esp-bridge-uart
    log "symlink /dev/esp-bridge-uart → $src"
    break
  fi
done

log "Done — reboot. Heltec: Pi TX→Heltec RX, Pi RX←Heltec TX, common GND, Heltec on battery."
log "Prefer Digivice stack: modem UART + Heltec USB hub — do not mix both on serial0."
