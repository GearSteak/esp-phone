#!/usr/bin/env bash
# Configure Digivice for SIM7600 on Pi GPIO UART (/dev/serial0).
#   digivice-modem-uart
#
# Fixes the usual blockers:
#   - enable_uart=1
#   - remove console=serial0 from cmdline (login shell steals AT port)
#   - stop serial-getty on ttyS0
#   - symlink /dev/sim7600-at + dialout for GUI user
#
set +e
set -u

log() { echo "[modem-uart] $*"; }
NEED_REBOOT=0

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
    NEED_REBOOT=1
  else
    log "enable_uart=1 already set"
  fi
fi

# Serial console on cmdline steals /dev/serial0 (root:tty 600 → Permission denied)
CMDLINE=""
for c in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
  if [[ -f "$c" ]] && grep -qE 'console=(serial0|ttyAMA0|ttyS0)' "$c" 2>/dev/null; then
    CMDLINE="$c"
    break
  fi
done
if [[ -n "$CMDLINE" ]]; then
  cp -a "$CMDLINE" "${CMDLINE}.bak-digivice" 2>/dev/null || true
  # Keep console=tty1; drop UART console tokens (with optional ,baud)
  sed -E -i \
    -e 's/(^|[[:space:]])console=serial0(,[^[:space:]]*)?//g' \
    -e 's/(^|[[:space:]])console=ttyAMA0(,[^[:space:]]*)?//g' \
    -e 's/(^|[[:space:]])console=ttyS0(,[^[:space:]]*)?//g' \
    -e 's/[[:space:]]+/ /g' \
    -e 's/^ //;s/ $//' \
    "$CMDLINE"
  log "removed UART console from $CMDLINE (reboot required)"
  log "  backup: ${CMDLINE}.bak-digivice"
  NEED_REBOOT=1
else
  log "cmdline: no UART console (good)"
fi

# Stop getty holding the port now (permissions still need reboot for clean state)
systemctl disable --now serial-getty@ttyS0.service 2>/dev/null || true
systemctl disable --now serial-getty@serial0.service 2>/dev/null || true
systemctl disable --now serial-getty@ttyAMA0.service 2>/dev/null || true
# Soften perms if getty already released the node
for p in /dev/ttyS0 /dev/serial0 /dev/ttyAMA0; do
  if [[ -e "$p" ]]; then
    chgrp dialout "$p" 2>/dev/null || true
    chmod 660 "$p" 2>/dev/null || true
  fi
done

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

# Dialout for GUI / sudo user
USERS=()
[[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]] && USERS+=("$SUDO_USER")
for u in gearsteak pi isaac; do
  USERS+=("$u")
done
for u in "${USERS[@]}"; do
  id "$u" >/dev/null 2>&1 && usermod -aG dialout "$u" 2>/dev/null || true
done

log "HAT checklist: PWR→3V3 (not D6), UART jumpers both B, wait ~20s after power"
if [[ "$NEED_REBOOT" -eq 1 ]]; then
  log "REBOOT REQUIRED — then Settings→Network→Use GPIO UART → Reconnect"
  log "  sudo reboot"
else
  log "Test: Settings→Network→Reconnect (no SIM needed for AT/GPS)"
fi
log "Done."
