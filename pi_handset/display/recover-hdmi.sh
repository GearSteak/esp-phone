#!/usr/bin/env bash
# Restore normal Raspberry Pi HDMI + desktop session after Digivice install.
# Safe to re-run. Does NOT reinstall the OS or wipe your packages.
#
#   sudo digivice-recover-hdmi
#   sudo reboot
#
set -euo pipefail

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

# Turn HDMI back on
if grep -qE '^dtoverlay=vc4-kms-v3d' "$BOOTCFG"; then
  sed -i -E 's/^dtoverlay=vc4-kms-v3d(|,.*)$/dtoverlay=vc4-kms-v3d/' "$BOOTCFG"
  echo "  vc4-kms-v3d → HDMI enabled (removed nohdmi)"
else
  echo "dtoverlay=vc4-kms-v3d" >>"$BOOTCFG"
  echo "  added dtoverlay=vc4-kms-v3d"
fi

# Comment out Digivice SPI block so tiny panel is not the only forced surface
if grep -q '# --- ESP Digivice display' "$BOOTCFG"; then
  # Comment every line inside the block (keep markers so install can rewrite cleanly)
  awk '
    BEGIN { inb=0 }
    /# --- ESP Digivice display/ { inb=1; print; next }
    /# --- END ESP Digivice display/ { inb=0; print; next }
    {
      if (inb && $0 !~ /^#/) print "# " $0
      else print
    }
  ' "$BOOTCFG" >"${BOOTCFG}.tmp" && mv "${BOOTCFG}.tmp" "$BOOTCFG"
  echo "  commented Digivice SPI block (HDMI-only until you re-enable)"
fi

# Boot into normal desktop, not Digivice kiosk
mkdir -p "$USER_HOME/.esp-handset" /etc/esp-handset
echo desktop >"$USER_HOME/.esp-handset/session_mode"
echo desktop >/etc/esp-handset/ui_mode
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset/session_mode" 2>/dev/null || true
chown "$USER_NAME:$USER_NAME" /etc/esp-handset/ui_mode 2>/dev/null || true
chmod 664 /etc/esp-handset/ui_mode 2>/dev/null || true
echo "  session_mode=desktop (no phone autostart)"

# Stop any running Digivice UI
pkill -f handset_app.py 2>/dev/null || true
pkill -f "/opt/esp-handset/handset_app.py" 2>/dev/null || true

echo ""
echo "Done. Reboot now:"
echo "  sudo reboot"
echo ""
echo "After HDMI works, optionally re-enable SPI panel (keeps HDMI):"
echo "  sudo bash /opt/esp-handset/display/install-display.sh && sudo reboot"
echo "Launch Digivice anytime from desktop:  handset-phone"
echo "Exit Digivice:  handset-desktop   or F12 in the UI"
