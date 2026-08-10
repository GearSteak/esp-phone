#!/usr/bin/env bash
# Digivice Settings → Power (passwordless-friendly).
#
#   digivice-power off|poweroff|shutdown
#   digivice-power restart|reboot
#
set +e
set -u

ACTION="${1:-}"
case "$ACTION" in
  off|poweroff|shutdown|halt) ACTION=poweroff ;;
  restart|reboot) ACTION=reboot ;;
  -h|--help|"")
    echo "Usage: digivice-power off|restart"
    exit 0
    ;;
  *)
    echo "Unknown action: $ACTION (use off or restart)"
    exit 2
    ;;
esac

if [[ "$(id -u)" -ne 0 ]]; then
  if sudo -n true 2>/dev/null; then
    exec sudo -n env \
      HOME="${HOME}" \
      SUDO_USER="${SUDO_USER:-$USER}" \
      PATH="/usr/sbin:/sbin:/usr/bin:/bin:$PATH" \
      bash "$0" "$ACTION"
  fi
  echo "ERROR: need passwordless sudo for digivice-power"
  echo "  Fix: sudo digivice-full-update"
  exit 1
fi

echo "[digivice-power] $ACTION in 1s…"
sync 2>/dev/null || true
sleep 1

if [[ "$ACTION" == "poweroff" ]]; then
  if command -v systemctl >/dev/null 2>&1; then
    systemctl poweroff
  elif [[ -x /sbin/poweroff ]]; then
    /sbin/poweroff
  elif [[ -x /sbin/shutdown ]]; then
    /sbin/shutdown -h now
  else
    echo "ERROR: no poweroff command"
    exit 1
  fi
else
  if command -v systemctl >/dev/null 2>&1; then
    systemctl reboot
  elif [[ -x /sbin/reboot ]]; then
    /sbin/reboot
  elif [[ -x /sbin/shutdown ]]; then
    /sbin/shutdown -r now
  else
    echo "ERROR: no reboot command"
    exit 1
  fi
fi
