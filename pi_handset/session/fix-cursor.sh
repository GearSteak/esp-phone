#!/usr/bin/env bash
# Make the desktop mouse cursor visible again (Pi vc4 often loses HW cursor).
#
#   digivice-fix-cursor           # for current X session
#   sudo digivice-fix-cursor --permanent   # Xorg software cursor on next login
#
set +e
set -u
export DISPLAY="${DISPLAY:-:0}"
PERM=0
for a in "$@"; do
  [[ "$a" == "--permanent" || "$a" == "-p" ]] && PERM=1
done

if [[ -z "${XAUTHORITY:-}" ]]; then
  for a in "${HOME}/.Xauthority" /home/*/.Xauthority; do
    if [[ -f $a ]]; then
      export XAUTHORITY="$(ls $a 2>/dev/null | head -n1)"
      break
    fi
  done
fi

echo "[fix-cursor] DISPLAY=$DISPLAY"

# Stop cursor hiders
pkill -x unclutter 2>/dev/null || true
pkill -f 'unclutter' 2>/dev/null || true

if command -v xsetroot >/dev/null 2>&1; then
  xsetroot -cursor_name left_ptr 2>/dev/null \
    || xsetroot -cursor_name arrow 2>/dev/null \
    || true
  echo "[fix-cursor] xsetroot left_ptr"
fi

if command -v gsettings >/dev/null 2>&1; then
  gsettings set org.gnome.desktop.interface cursor-size 32 2>/dev/null || true
  gsettings set org.gnome.desktop.interface cursor-theme 'Adwaita' 2>/dev/null || true
fi

if command -v xdotool >/dev/null 2>&1; then
  xdotool mousemove_relative -- 2 0 2>/dev/null
  xdotool mousemove_relative -- -2 0 2>/dev/null
fi

# Wayland / labwc: prefer starting a thick X cursor on Xwayland or fall through
# Permanent Xorg software cursor
if [[ "$PERM" -eq 1 ]]; then
  if [[ "$(id -u)" -ne 0 ]]; then
    exec sudo -n bash "$0" --permanent 2>/dev/null || exec sudo bash "$0" --permanent
  fi
  mkdir -p /etc/X11/xorg.conf.d
  cat >/etc/X11/xorg.conf.d/20-digivice-swcursor.conf <<'EOF'
# Digivice: force software mouse cursor (vc4 hardware plane often blank)
Section "Device"
    Identifier "Digivice modesetting"
    Driver "modesetting"
    Option "SWcursor" "true"
EndSection
EOF
  apt-get install -y xbitmaps x11-xserver-utils 2>/dev/null || true
  echo "[fix-cursor] wrote /etc/X11/xorg.conf.d/20-digivice-swcursor.conf"
  echo "  Log out/in or reboot for full effect (or switch session to X11)."
fi

# Hint: force X11 desktop on Bookworm if using labwc without visible cursor
if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
  echo "[fix-cursor] Wayland session detected ($WAYLAND_DISPLAY)."
  echo "  If still invisible: Raspberry menu → reboot to 'X11' (not Wayland),"
  echo "  or:  sudo raspi-config → Advanced → Wayland → X11"
fi

echo "[fix-cursor] done — move the mouse. Still gone? sudo digivice-fix-cursor --permanent"
