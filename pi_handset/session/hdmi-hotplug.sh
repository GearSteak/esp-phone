#!/usr/bin/env bash
# Enable HDMI when a monitor is plugged in after boot.
#
# Pi + vc4 KMS only configures outputs that exist at X start. Late cable/
# monitor power needs xrandr --auto (or a reboot). This is installed as
# digivice-hdmi-hotplug and runs from udev on DRM hotplug.
#
#   digivice-hdmi-hotplug           # enable now
#   sudo digivice-hdmi-hotplug --install
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
LOG_DIR="${HOME:-/tmp}/.esp-handset"
LOG="${LOG_DIR}/hdmi-hotplug.log"
LOCK=/run/digivice-hdmi-hotplug.lock
DEBOUNCE_SEC=2

INSTALL=0
for a in "$@"; do
  case "$a" in
    --install|install) INSTALL=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
  esac
done

log() {
  mkdir -p "$LOG_DIR" 2>/dev/null || true
  echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG" 2>/dev/null || echo "[hdmi-hotplug] $*"
}

gui_user() {
  local u="${SUDO_USER:-}"
  if [[ -z "$u" || "$u" == "root" ]]; then
    u="$(logname 2>/dev/null || true)"
  fi
  if [[ -z "$u" || "$u" == "root" ]]; then
    for c in pi isaac; do
      if id "$c" >/dev/null 2>&1; then u=$c; break; fi
    done
  fi
  if [[ -z "$u" || "$u" == "root" ]]; then
    u="$(awk -F: '$3>=1000 && $3<65534 {print $1; exit}' /etc/passwd 2>/dev/null || true)"
  fi
  echo "${u:-pi}"
}

install_hooks() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run: sudo digivice-hdmi-hotplug --install" >&2
    exit 1
  fi
  local u home xauth
  u="$(gui_user)"
  home="$(getent passwd "$u" | cut -d: -f6 || echo "/home/$u")"
  xauth="${home}/.Xauthority"

  install -m 755 "$0" "$PREFIX/session/hdmi-hotplug.sh" 2>/dev/null || true
  if [[ -f "$(dirname "$0")/hdmi-hotplug.sh" ]]; then
    install -m 755 "$(dirname "$0")/hdmi-hotplug.sh" "$PREFIX/session/hdmi-hotplug.sh"
  fi
  # Prefer installed copy for the symlink target
  if [[ -f "$PREFIX/session/hdmi-hotplug.sh" ]]; then
    install -m 755 "$PREFIX/session/hdmi-hotplug.sh" /usr/local/bin/digivice-hdmi-hotplug
  else
    install -m 755 "$0" /usr/local/bin/digivice-hdmi-hotplug
  fi

  # Firmware help (FKMS / picky monitors; harmless under pure KMS)
  local bootcfg=""
  for c in /boot/firmware/config.txt /boot/config.txt; do
    [[ -f "$c" ]] && bootcfg="$c" && break
  done
  if [[ -n "$bootcfg" ]]; then
    sed -i -E 's/^dtoverlay=vc4-kms-v3d(|,.*)$/dtoverlay=vc4-kms-v3d/' "$bootcfg" || true
    grep -qE '^hdmi_force_hotplug=' "$bootcfg" || echo "hdmi_force_hotplug=1" >>"$bootcfg"
    grep -qE '^hdmi_drive=' "$bootcfg" || echo "hdmi_drive=2" >>"$bootcfg"
    # Ignore firmware "blank if no cable at boot" behaviour on some images
    grep -qE '^hdmi_blanking=' "$bootcfg" || echo "hdmi_blanking=1" >>"$bootcfg"
  fi

  cat >/etc/udev/rules.d/99-digivice-hdmi-hotplug.rules <<'EOF'
# Digivice — enable HDMI when a monitor is attached after boot
ACTION=="change", SUBSYSTEM=="drm", ENV{HOTPLUG}=="1", \
  RUN+="/bin/systemctl --no-block start digivice-hdmi-hotplug.service"
EOF

  cat >/etc/systemd/system/digivice-hdmi-hotplug.service <<EOF
[Unit]
Description=Digivice enable HDMI after cable hotplug
After=display-manager.service graphical.target
# Avoid thrashing when many DRM change events fire
StartLimitIntervalSec=10
StartLimitBurst=3

[Service]
Type=oneshot
User=root
Environment=DISPLAY=:0
Environment=XAUTHORITY=$xauth
Environment=HOME=$home
Environment=ESP_HANDSET_PREFIX=$PREFIX
# Let EDID settle
ExecStartPre=/bin/sleep 1
ExecStart=/usr/local/bin/digivice-hdmi-hotplug
TimeoutStartSec=30

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable digivice-hdmi-hotplug.service 2>/dev/null || true
  udevadm control --reload-rules 2>/dev/null || true
  udevadm trigger --subsystem-match=drm 2>/dev/null || true
  log "installed udev+systemd for HDMI hotplug (user=$u)"
  echo "OK: digivice-hdmi-hotplug installed. Plug HDMI — should light within ~2s."
  echo "    Manual: digivice-hdmi-hotplug"
  echo "    If still dark after plug: digivice-hdmi-hotplug && digivice-unfuck-displays"
  # Run once now
  /usr/local/bin/digivice-hdmi-hotplug || true
  exit 0
}

if [[ "$INSTALL" -eq 1 ]]; then
  install_hooks
fi

# --- Enable outputs (idempotent) ---
# Debounce concurrent udev storms
if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK" 2>/dev/null || exec 9>/tmp/digivice-hdmi-hotplug.lock
  if ! flock -n 9; then
    # Another instance is running — skip
    exit 0
  fi
fi

# If invoked as root via systemd, drop privileges for xrandr when possible
run_x() {
  local u home xauth
  u="$(gui_user)"
  home="$(getent passwd "$u" | cut -d: -f6 || echo "/home/$u")"
  xauth="${XAUTHORITY:-$home/.Xauthority}"
  export DISPLAY="${DISPLAY:-:0}"
  export XAUTHORITY="$xauth"
  if [[ "$(id -u)" -eq 0 ]] && id "$u" >/dev/null 2>&1 && [[ "$u" != "root" ]]; then
    sudo -u "$u" env DISPLAY="$DISPLAY" XAUTHORITY="$xauth" HOME="$home" "$@"
  else
    env DISPLAY="$DISPLAY" XAUTHORITY="$xauth" "$@"
  fi
}

log "hotplug run uid=$(id -u) DISPLAY=${DISPLAY:-:0}"

# Brief settle (udev often fires before EDID is ready)
sleep "$DEBOUNCE_SEC"

if command -v xrandr >/dev/null 2>&1; then
  if run_x xrandr --query >/dev/null 2>&1; then
    run_x xrandr --auto >/dev/null 2>&1
    # Explicit HDMI/DP — "connected" heads that have no mode yet
    while read -r line; do
      name="${line%% *}"
      case "$name" in
        HDMI*|hdmi*|DP-*|DisplayPort*)
          run_x xrandr --output "$name" --auto --on >/dev/null 2>&1
          # Prefer first HDMI as primary so Digivice/desktop appear there
          run_x xrandr --output "$name" --primary >/dev/null 2>&1
          log "enabled $name"
          ;;
      esac
    done < <(run_x xrandr --query 2>/dev/null | awk '/ connected/{print}')
    # Leave SPI/Unknown panels alone if present (dual-head DRM installs)
    log "xrandr done"
    run_x xrandr --query 2>/dev/null | awk '/ connected|disconnected|Screen /{print}' | tee -a "$LOG" >/dev/null
  else
    log "xrandr cannot talk to X (session not up yet?) — will retry on next event"
  fi
elif command -v wlr-randr >/dev/null 2>&1; then
  run_x wlr-randr 2>/dev/null | while read -r line; do
    :
  done
  log "wlr-randr present — ran generic on"
else
  log "no xrandr — install x11-xserver-utils"
fi

exit 0
