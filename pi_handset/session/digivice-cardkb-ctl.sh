#!/usr/bin/env bash
# Pause/resume CardKB I2C without destroying the uinput keyboard.
# labwc (Pi OS Wayland) will not type keys from a keyboard created after login.
#   sudo digivice-cardkb-ctl stop   # Digivice owns I2C
#   sudo digivice-cardkb-ctl start  # Linux desktop owns I2C
set -e
op="${1:-}"
PAUSE=/tmp/digivice-cardkb.pause
case "$op" in
  stop)
    echo 1 >"$PAUSE"
    chmod 666 "$PAUSE" 2>/dev/null || true
    # Keep the unit up so Digivice-CardKB stays on the seat
    systemctl start cardkb-inputd.service 2>/dev/null || true
    ;;
  start)
    rm -f "$PAUSE"
    systemctl start cardkb-inputd.service 2>/dev/null || true
    ;;
  *)
    echo "usage: $0 start|stop" >&2
    exit 2
    ;;
esac
