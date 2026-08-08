#!/usr/bin/env bash
# Restore HDMI after an old Digivice install used vc4-kms-v3d,nohdmi.
# Does NOT uninstall Digivice or force a desktop-only life.
#
#   sudo digivice-recover-hdmi              # HDMI on, SPI panel stays enabled
#   sudo digivice-recover-hdmi --keep-phone # also force session_mode=phone
#   sudo digivice-recover-hdmi --desktop-once  # this login only (session desktop)
#   sudo reboot
#
set -euo pipefail

KEEP_PHONE=0
DESKTOP_ONCE=0
for arg in "$@"; do
  case "$arg" in
    --keep-phone) KEEP_PHONE=1 ;;
    --desktop-once) DESKTOP_ONCE=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run: sudo digivice-recover-hdmi" >&2
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

# HDMI ON — strip ,nohdmi only. Keep SPI Digivice block so both can work.
if grep -qE '^dtoverlay=vc4-kms-v3d' "$BOOTCFG"; then
  sed -i -E 's/^dtoverlay=vc4-kms-v3d(|,.*)$/dtoverlay=vc4-kms-v3d/' "$BOOTCFG"
  echo "  vc4-kms-v3d → HDMI enabled (removed nohdmi if present)"
else
  echo "dtoverlay=vc4-kms-v3d" >>"$BOOTCFG"
  echo "  added dtoverlay=vc4-kms-v3d"
fi

# Un-comment Digivice SPI lines if a prior recovery commented them out
if grep -q '# --- ESP Digivice display' "$BOOTCFG"; then
  awk '
    BEGIN { inb=0 }
    /# --- ESP Digivice display/ { inb=1; print; next }
    /# --- END ESP Digivice display/ { inb=0; print; next }
    {
      if (inb && $0 ~ /^# dt/) {
        sub(/^# /, "", $0)
        print
      } else if (inb && $0 ~ /^# dtoverlay/) {
        sub(/^# /, "", $0)
        print
      } else print
    }
  ' "$BOOTCFG" >"${BOOTCFG}.tmp" && mv "${BOOTCFG}.tmp" "$BOOTCFG"
  echo "  Digivice SPI block left active (2\" + HDMI)"
fi

mkdir -p "$USER_HOME/.esp-handset" /etc/esp-handset
if [[ "$KEEP_PHONE" -eq 1 ]]; then
  echo phone >"$USER_HOME/.esp-handset/session_mode"
  echo phone >/etc/esp-handset/ui_mode
  echo "  session_mode=phone (Digivice default)"
elif [[ "$DESKTOP_ONCE" -eq 1 ]]; then
  echo desktop >"$USER_HOME/.esp-handset/session_mode"
  echo desktop >/etc/esp-handset/ui_mode
  echo "  session_mode=desktop (change later with: handset-session set-phone)"
else
  # Preserve whatever they had (phone or desktop)
  if [[ ! -f "$USER_HOME/.esp-handset/session_mode" ]]; then
    echo phone >"$USER_HOME/.esp-handset/session_mode"
    echo "  session_mode=phone (created default)"
  else
    echo "  session_mode unchanged ($(tr -d '[:space:]' <"$USER_HOME/.esp-handset/session_mode"))"
  fi
fi
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset/session_mode" 2>/dev/null || true
chown "$USER_NAME:$USER_NAME" /etc/esp-handset/ui_mode 2>/dev/null || true
chmod 664 /etc/esp-handset/ui_mode 2>/dev/null || true

pkill -f handset_app.py 2>/dev/null || true

echo ""
echo "Done. Reboot:"
echo "  sudo reboot"
echo "Digivice default: handset-session set-phone"
echo "Leave Digivice for desktop app: handset-desktop (or F12)"
