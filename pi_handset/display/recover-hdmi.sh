#!/usr/bin/env bash
# Restore HDMI + stop Digivice from owning the session.
#
#   sudo digivice-recover-hdmi              # config + desktop mode + reboot hint
#   sudo digivice-recover-hdmi --now        # also run xrandr unfuck without reboot
#   sudo digivice-recover-hdmi --keep-phone # keep phone mode (not recommended when dark)
#
set -euo pipefail

KEEP_PHONE=0
NOW=0
for arg in "$@"; do
  case "$arg" in
    --keep-phone) KEEP_PHONE=1 ;;
    --now) NOW=1 ;;
    -h|--help)
      sed -n '2,10p' "$0"
      exit 0
      ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run: sudo digivice-recover-hdmi --now" >&2
  exit 1
fi

USER_NAME="${SUDO_USER:-$USER}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"

BOOTCFG=""
for cand in /boot/firmware/config.txt /boot/config.txt; do
  if [[ -f "$cand" ]]; then
    BOOTCFG="$cand"
    break
  fi
done
if [[ -z "$BOOTCFG" ]]; then
  echo "ERROR: no config.txt" >&2
  exit 1
fi

echo "=== digivice-recover-hdmi ==="
echo "Editing $BOOTCFG"

# HDMI ON — strip ,nohdmi
if grep -qE '^dtoverlay=vc4-kms-v3d' "$BOOTCFG"; then
  sed -i -E 's/^dtoverlay=vc4-kms-v3d(|,.*)$/dtoverlay=vc4-kms-v3d/' "$BOOTCFG"
  echo "  vc4-kms-v3d HDMI enabled"
else
  echo "dtoverlay=vc4-kms-v3d" >>"$BOOTCFG"
  echo "  added dtoverlay=vc4-kms-v3d"
fi

# Help picky monitors
grep -qE '^hdmi_force_hotplug=' "$BOOTCFG" || echo "hdmi_force_hotplug=1" >>"$BOOTCFG"
grep -qE '^hdmi_drive=' "$BOOTCFG" || echo "hdmi_drive=2" >>"$BOOTCFG"

# Un-comment Digivice SPI block if previously disabled
if grep -q '# --- ESP Digivice display' "$BOOTCFG"; then
  awk '
    BEGIN { inb=0 }
    /# --- ESP Digivice display/ { inb=1; print; next }
    /# --- END ESP Digivice display/ { inb=0; print; next }
    {
      if (inb && $0 ~ /^# dt/) { sub(/^# /, "", $0); print }
      else if (inb && $0 ~ /^# dtoverlay/) { sub(/^# /, "", $0); print }
      else print
    }
  ' "$BOOTCFG" >"${BOOTCFG}.tmp" && mv "${BOOTCFG}.tmp" "$BOOTCFG"
fi

mkdir -p "$USER_HOME/.esp-handset" /etc/esp-handset
if [[ "$KEEP_PHONE" -eq 1 ]]; then
  echo phone >"$USER_HOME/.esp-handset/session_mode"
  echo phone >/etc/esp-handset/ui_mode
  echo "  session_mode=phone"
else
  echo desktop >"$USER_HOME/.esp-handset/session_mode"
  echo desktop >/etc/esp-handset/ui_mode
  echo "  session_mode=desktop (Digivice will NOT autostart)"
fi
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset/session_mode" 2>/dev/null || true

pkill -9 -f handset_app.py 2>/dev/null || true

if [[ "$NOW" -eq 1 ]]; then
  export DISPLAY="${DISPLAY:-:0}"
  if [[ -x /usr/local/bin/digivice-unfuck-displays ]]; then
    sudo -u "$USER_NAME" DISPLAY=:0 /usr/local/bin/digivice-unfuck-displays || true
  elif [[ -f /opt/esp-handset/session/unfuck-displays.sh ]]; then
    sudo -u "$USER_NAME" DISPLAY=:0 bash /opt/esp-handset/session/unfuck-displays.sh || true
  fi
fi

echo ""
echo "Done."
echo "  If HDMI is still black:  sudo reboot"
echo "  After reboot you should get desktop (not Digivice)."
echo "  Unfuck once logged in:   digivice-unfuck-displays"
echo "  Phone later:             handset-session set-phone && handset-phone"
