#!/usr/bin/env bash
# NUCLEAR display recovery — HDMI first, all outputs auto, Digivice off.
#
#   digivice-unfuck-displays          # as user with DISPLAY=:0
#   sudo digivice-unfuck-displays     # also fixes config.txt nohdmi + desktop mode
#
set +e
set -u

export DISPLAY="${DISPLAY:-:0}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-}"
LOG="${HOME}/.esp-handset/handset.log"
mkdir -p "${HOME}/.esp-handset" 2>/dev/null
log() { echo "[unfuck] $*" | tee -a "$LOG" >&2; }

log "=== digivice-unfuck-displays ==="

# 1) Kill Digivice kiosk
pkill -9 -f handset_app.py 2>/dev/null || true
pkill -9 -f "python3.*handset" 2>/dev/null || true
echo desktop >"${HOME}/.esp-handset/session_mode" 2>/dev/null || true
if [[ -w /etc/esp-handset ]]; then
  echo desktop >/etc/esp-handset/ui_mode 2>/dev/null || true
fi
log "Digivice killed; session_mode=desktop"

# 2) Backlight
for d in /sys/class/backlight/*; do
  [[ -d "$d" ]] || continue
  echo 0 >"$d/bl_power" 2>/dev/null || true
  [[ -r "$d/max_brightness" ]] && cat "$d/max_brightness" >"$d/brightness" 2>/dev/null || true
done

# 3) Runtime: every connected output ON with native modes — NO scale-from
if command -v xrandr >/dev/null 2>&1 && xrandr --query >/dev/null 2>&1; then
  xrandr --auto 2>/dev/null
  mapfile -t OUTS < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
  log "connected: ${OUTS[*]:-none}"
  HDMI=""
  for o in "${OUTS[@]:-}"; do
    xrandr --output "$o" --auto --on 2>/dev/null
    case "$o" in HDMI*|hdmi*) HDMI="${HDMI:-$o}" ;; esac
  done
  if [[ -n "$HDMI" ]]; then
    xrandr --output "$HDMI" --auto --primary --on 2>/dev/null
    # Put other heads to the right so HDMI is the main workspace
    for o in "${OUTS[@]:-}"; do
      [[ "$o" == "$HDMI" ]] && continue
      xrandr --output "$o" --auto --right-of "$HDMI" 2>/dev/null \
        || xrandr --output "$o" --auto --on 2>/dev/null
    done
    log "HDMI primary=$HDMI — look at monitor now"
  else
    log "no HDMI name in xrandr; all --auto applied"
  fi
  xrandr --query 2>/dev/null | grep -E 'Screen | connected' | tee -a "$LOG" >&2
else
  log "xrandr not talking to X (try: export DISPLAY=:0)"
fi

# 4) Root: config.txt never nohdmi
if [[ "$(id -u)" -eq 0 ]]; then
  for BOOTCFG in /boot/firmware/config.txt /boot/config.txt; do
    [[ -f "$BOOTCFG" ]] || continue
    if grep -qE '^dtoverlay=vc4-kms-v3d' "$BOOTCFG"; then
      sed -i -E 's/^dtoverlay=vc4-kms-v3d(|,.*)$/dtoverlay=vc4-kms-v3d/' "$BOOTCFG"
      log "stripped nohdmi from $BOOTCFG"
    fi
    # NEVER hdmi_force_hotplug — created ghost HDMI head and SPI static on Digivice
    sed -i '/^hdmi_force_hotplug=/d' "$BOOTCFG" 2>/dev/null || true
    if ! grep -qE '^hdmi_drive=' "$BOOTCFG"; then
      echo "hdmi_drive=2" >>"$BOOTCFG"
      log "added hdmi_drive=2"
    fi
    break
  done
  log "as root: reboot recommended if HDMI still black after xrandr"
fi

# Desktop chrome
command -v lxpanelctl >/dev/null 2>&1 && lxpanelctl show 2>/dev/null || true
command -v wmctrl >/dev/null 2>&1 && wmctrl -k off 2>/dev/null || true

log "done. If still black: reboot and run again right after login."
echo "OK — session=desktop, Digivice off, HDMI should be primary."
echo "Return to Digivice later only after SPI works: handset-session set-phone && handset-phone"
