#!/usr/bin/env bash
# Passwordless CardKB daemon control (sudoers allowlists this binary).
# Digivice reads CardKB in-process; stop the systemd unit so they don't fight.
#   sudo digivice-cardkb-ctl stop
#   sudo digivice-cardkb-ctl start
set -e
op="${1:-}"
case "$op" in
  stop|start)
    systemctl "$op" cardkb-inputd.service
    ;;
  *)
    echo "usage: $0 start|stop" >&2
    exit 2
    ;;
esac
