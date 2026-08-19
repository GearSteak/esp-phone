#!/usr/bin/env bash
# Pause/resume CardKB I2C without destroying the uinput keyboard.
# labwc (Pi OS Wayland) will not type keys from a keyboard created after login.
#   sudo digivice-cardkb-ctl stop   # Digivice owns I2C
#   sudo digivice-cardkb-ctl start  # Linux desktop owns I2C
set -e
op="${1:-}"
PAUSE_DIR=/run/digivice
PAUSE="$PAUSE_DIR/cardkb.pause"
LEGACY=/tmp/digivice-cardkb.pause
mkdir -p "$PAUSE_DIR" 2>/dev/null || true
chmod 0777 "$PAUSE_DIR" 2>/dev/null || true
case "$op" in
  stop)
    echo 1 >"$PAUSE"
    chmod 666 "$PAUSE" 2>/dev/null || true
    # Keep the unit up so Digivice-CardKB stays on the seat
    systemctl start cardkb-inputd.service 2>/dev/null || true
    ;;
  start)
    rm -f "$PAUSE" "$LEGACY"
    systemctl start cardkb-inputd.service 2>/dev/null || true
    ;;
  *)
    echo "usage: $0 start|stop" >&2
    exit 2
    ;;
esac
