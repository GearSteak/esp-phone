#!/usr/bin/env bash
# Configure Digivice for SIM7600 on Pi GPIO UART (/dev/serial0).
#   digivice-modem-uart
#
set +e
set -u

log() { echo "[modem-uart] $*"; }

mkdir -p /etc/esp-handset 2>/dev/null || true
echo uart >/etc/esp-handset/modem-backend
touch /etc/esp-handset/modem-uart
log "modem-backend=uart"

# Prefer primary UART for HAT TX/RX (GPIO 14/15)
BOOTCFG=""
for c in /boot/firmware/config.txt /boot/config.txt; do
  [[ -f "$c" ]] && BOOTCFG="$c" && break
done
if [[ -n "$BOOTCFG" ]]; then
  if ! grep -qE '^enable_uart=1' "$BOOTCFG"; then
    echo "" >>"$BOOTCFG"
    echo "# Digivice SIM7600 GPIO UART" >>"$BOOTCFG"
    echo "enable_uart=1" >>"$BOOTCFG"
    log "added enable_uart=1 to $BOOTCFG (reboot needed)"
  else
    log "enable_uart=1 already set"
  fi
  # Don't force dtoverlay changes — serial0 alias is enough on most images
fi

# Symlink Digivice expects
if [[ -e /dev/serial0 ]]; then
  ln -sfn /dev/serial0 /dev/sim7600-at
  log "linked /dev/sim7600-at → /dev/serial0"
elif [[ -e /dev/ttyAMA0 ]]; then
  ln -sfn /dev/ttyAMA0 /dev/sim7600-at
  log "linked /dev/sim7600-at → /dev/ttyAMA0"
elif [[ -e /dev/ttyS0 ]]; then
  ln -sfn /dev/ttyS0 /dev/sim7600-at
  log "linked /dev/sim7600-at → /dev/ttyS0"
else
  log "WARN: no serial0/ttyAMA0/ttyS0 yet — enable UART and reboot"
fi

# Dialout for GUI user
for u in pi isaac; do
  id "$u" >/dev/null 2>&1 && usermod -aG dialout "$u" 2>/dev/null || true
done

log "HAT checklist: PWR→3V3 (not D6), wait ~20s after power"
log "Test:  echo -ne 'AT\\r' > /dev/serial0   then Settings→Network→Reconnect"
log "Done. Reboot if enable_uart was just added, then: handset-phone"
