#!/usr/bin/env bash
# Optional: enable HDMI when a cable is plugged AFTER boot.
#
# IMPORTANT: This used to fight userspace SPI (ST7789) — DRM udev storms
# re-ran xrandr + restarted the SPI mirror, leaving the 2" panel dark/frozen.
#
# Default after full-update: DISABLE the automatic hooks.
# Manual one-shot is still fine when you need late-plug HDMI.
#
#   digivice-hdmi-hotplug                 # one-shot: xrandr --auto for HDMI only
#   sudo digivice-hdmi-hotplug --disable  # *** remove udev/service + force_hotplug ***
#   sudo digivice-hdmi-hotplug --install  # opt-in udev (SPI-safe, no force_hotplug)
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
LOG_DIR="${HOME:-/tmp}/.esp-handset"
LOG="${LOG_DIR}/hdmi-hotplug.log"
LOCK=/run/digivice-hdmi-hotplug.lock
DEBOUNCE_SEC=1

INSTALL=0
DISABLE=0
for a in "$@"; do
  case "$a" in
    --install|install) INSTALL=1 ;;
    --disable|--uninstall|disable|uninstall) DISABLE=1 ;;
    -h|--help)
      sed -n '2,16p' "$0"
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

bootcfg_path() {
  for c in /boot/firmware/config.txt /boot/config.txt; do
    [[ -f "$c" ]] && echo "$c" && return
  done
  echo ""
}

strip_force_hotplug() {
  local bootcfg="$1"
  [[ -z "$bootcfg" || ! -f "$bootcfg" ]] && return
  # Comment out — force_hotplug creates a fake HDMI head that confuses X + SPI mirror
  sed -i -E 's/^hdmi_force_hotplug=.*/# digivice: disabled (broke SPI \/ late modeset)\n# hdmi_force_hotplug=1/' "$bootcfg" 2>/dev/null || true
  sed -i -E 's/^hdmi_blanking=.*/# hdmi_blanking removed by digivice-hdmi-hotplug --disable/' "$bootcfg" 2>/dev/null || true
  # drop duplicate lines that only contain the old value
  sed -i '/^hdmi_force_hotplug=/d' "$bootcfg" 2>/dev/null || true
  log "stripped hdmi_force_hotplug from $bootcfg"
}

disable_hooks() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run: sudo digivice-hdmi-hotplug --disable" >&2
    exit 1
  fi
  systemctl disable --now digivice-hdmi-hotplug.service 2>/dev/null || true
  rm -f /etc/systemd/system/digivice-hdmi-hotplug.service
  rm -f /etc/udev/rules.d/99-digivice-hdmi-hotplug.rules
  systemctl daemon-reload 2>/dev/null || true
  udevadm control --reload-rules 2>/dev/null || true
  strip_force_hotplug "$(bootcfg_path)"
  # Keep digivice-hdmi-hotplug binary for manual one-shot use
  if [[ -f "$(dirname "$0")/hdmi-hotplug.sh" ]]; then
    install -m 755 "$(dirname "$0")/hdmi-hotplug.sh" /usr/local/bin/digivice-hdmi-hotplug
  fi
  echo "OK: automatic HDMI hotplug DISABLED (was fighting the 2\" SPI panel)."
  echo "    Manual when you need it: digivice-hdmi-hotplug"
  echo "    Then: digivice-fix-screens   (or handset-phone)"
  echo "    Reboot recommended if config.txt changed: sudo reboot"
  exit 0
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

  mkdir -p "$PREFIX/session"
  if [[ -f "$(dirname "$0")/hdmi-hotplug.sh" ]]; then
    install -m 755 "$(dirname "$0")/hdmi-hotplug.sh" "$PREFIX/session/hdmi-hotplug.sh"
  elif [[ -f "$0" ]]; then
    install -m 755 "$0" "$PREFIX/session/hdmi-hotplug.sh"
  fi
  install -m 755 "$PREFIX/session/hdmi-hotplug.sh" /usr/local/bin/digivice-hdmi-hotplug

  # Do NOT write hdmi_force_hotplug — it ghosts a black HDMI head
  local bootcfg
  bootcfg="$(bootcfg_path)"
  if [[ -n "$bootcfg" ]]; then
    sed -i -E 's/^dtoverlay=vc4-kms-v3d(|,.*)$/dtoverlay=vc4-kms-v3d/' "$bootcfg" || true
    strip_force_hotplug "$bootcfg"
  fi

  # Rate-limited udev → oneshot. Script itself never kills Digivice / SPI phone mode.
  cat >/etc/udev/rules.d/99-digivice-hdmi-hotplug.rules <<'EOF'
# Digivice optional HDMI late-plug (conservative)
ACTION=="change", SUBSYSTEM=="drm", ENV{HOTPLUG}=="1", \
  RUN+="/bin/systemctl --no-block start digivice-hdmi-hotplug.service"
EOF

  cat >/etc/systemd/system/digivice-hdmi-hotplug.service <<EOF
[Unit]
Description=Digivice optional HDMI late plug (xrandr only)
After=display-manager.service graphical.target
StartLimitIntervalSec=30
StartLimitBurst=2

[Service]
Type=oneshot
User=root
Environment=DISPLAY=:0
Environment=XAUTHORITY=$xauth
Environment=HOME=$home
Environment=ESP_HANDSET_PREFIX=$PREFIX
ExecStartPre=/bin/sleep 1
ExecStart=/usr/local/bin/digivice-hdmi-hotplug
TimeoutStartSec=20

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  # Enabled but StartLimitBurst keeps storms down; prefer --disable for SPI setups
  systemctl enable digivice-hdmi-hotplug.service 2>/dev/null || true
  udevadm control --reload-rules 2>/dev/null || true
  log "installed optional HDMI hotplug (no force_hotplug; SPI-safe path)"
  echo "OK: late-plug hooks installed (no hdmi_force_hotplug)."
  echo "    Userspace SPI setups should usually: sudo digivice-hdmi-hotplug --disable"
  exit 0
}

if [[ "$DISABLE" -eq 1 ]]; then
  disable_hooks
fi
if [[ "$INSTALL" -eq 1 ]]; then
  install_hooks
fi

# --- One-shot: enable connected HDMI only (never touch SPI / never restart mirror) ---
if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK" 2>/dev/null || exec 9>/tmp/digivice-hdmi-hotplug.lock
  if ! flock -n 9; then
    exit 0
  fi
fi

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

# Skip entirely while Digivice phone UI owns the session (SPI bus/mirrors)
mode_f=""
for mf in \
  "${HOME}/.esp-handset/session_mode" \
  "/home/$(gui_user)/.esp-handset/session_mode" \
  /etc/esp-handset/ui_mode
do
  [[ -f "$mf" ]] && mode_f="$mf" && break
done
mode="phone"
[[ -n "$mode_f" ]] && mode="$(tr -d '[:space:]' <"$mode_f" 2>/dev/null || echo phone)"
if [[ "$mode" == "phone" ]] || pgrep -f "handset_app.py" >/dev/null 2>&1; then
  log "skip hotplug (Digivice phone active) — not touching displays"
  exit 0
fi

log "hotplug one-shot uid=$(id -u) DISPLAY=${DISPLAY:-:0}"
sleep "$DEBOUNCE_SEC"

if command -v xrandr >/dev/null 2>&1 && run_x xrandr --query >/dev/null 2>&1; then
  run_x xrandr --auto >/dev/null 2>&1
  while read -r line; do
    name="${line%% *}"
    case "$name" in
      HDMI*|hdmi*|DP-*|DisplayPort*)
        run_x xrandr --output "$name" --auto --on >/dev/null 2>&1
        log "enabled $name"
        ;;
    esac
  done < <(run_x xrandr --query 2>/dev/null | awk '/ connected/{print}')
  # NEVER restart desktop SPI mirror here — that was blanking the 2" panel in a loop
else
  log "xrandr unavailable"
fi
exit 0
