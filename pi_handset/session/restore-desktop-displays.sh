#!/usr/bin/env bash
# Restore multi-monitor desktop after Digivice (HDMI-first, never blank).
# Also force a visible mouse cursor — vc4 hardware cursor often vanishes
# after multi-head / SPI layout / Digivice kiosk.
set +e
export DISPLAY="${DISPLAY:-:0}"

# XAUTHORITY for root-ish callers
if [[ -z "${XAUTHORITY:-}" ]]; then
  for a in \
    "${HOME}/.Xauthority" \
    /home/pi/.Xauthority \
    /home/*/.Xauthority
  do
    if [[ -f $a ]]; then
      # shellcheck disable=SC2086
      export XAUTHORITY="$(ls $a 2>/dev/null | head -n1)"
      break
    fi
  done
fi

pkill -f handset_app.py 2>/dev/null || true

if command -v xrandr >/dev/null 2>&1 && xrandr --query >/dev/null 2>&1; then
  xrandr --auto 2>/dev/null || true
  mapfile -t OUTS < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
  HDMI=""
  for o in "${OUTS[@]:-}"; do
    xrandr --output "$o" --auto --on 2>/dev/null || true
    case "$o" in HDMI*|hdmi*) HDMI="${HDMI:-$o}" ;; esac
  done
  if [[ -n "$HDMI" ]]; then
    xrandr --output "$HDMI" --auto --primary --on 2>/dev/null || true
    for o in "${OUTS[@]:-}"; do
      [[ "$o" == "$HDMI" ]] && continue
      xrandr --output "$o" --auto --right-of "$HDMI" 2>/dev/null \
        || xrandr --output "$o" --auto --on 2>/dev/null || true
    done
  fi
fi

# --- visible cursor (hardware plane often broken on Pi after digivice) ---
show_mouse_cursor() {
  # Kill anything that intentionally hides the pointer
  pkill -x unclutter 2>/dev/null || true
  pkill -f unclutter 2>/dev/null || true
  pkill -x unclutter-xfixes 2>/dev/null || true

  # X11: reassert default arrow (needs xbitmaps / xsetroot)
  if command -v xsetroot >/dev/null 2>&1; then
    xsetroot -cursor_name left_ptr 2>/dev/null \
      || xsetroot -cursor_name arrow 2>/dev/null || true
  fi
  if command -v xset >/dev/null 2>&1; then
    xset root -cursor_name left_ptr 2>/dev/null || true
  fi

  # Ensure blanking not eating the screen / pointer weirdness
  if command -v xset >/dev/null 2>&1; then
    xset s off 2>/dev/null || true
    xset -dpms 2>/dev/null || true
  fi

  # LXDE / PIXEL (older)
  if command -v lxappearance >/dev/null 2>&1; then
    :
  fi
  # xfce
  if command -v xfconf-query >/dev/null 2>&1; then
    xfconf-query -c xsettings -p /Gtk/CursorThemeName -s Adwaita 2>/dev/null || true
    xfconf-query -c xsettings -p /Gtk/CursorThemeSize -s 24 2>/dev/null || true
  fi
  # gsettings (gnome / some labwc sessions)
  if command -v gsettings >/dev/null 2>&1; then
    gsettings set org.gnome.desktop.interface cursor-size 32 2>/dev/null || true
    gsettings set org.gnome.desktop.interface cursor-theme 'Adwaita' 2>/dev/null || true
    gsettings set org.gnome.desktop.interface cursor-blink true 2>/dev/null || true
  fi

  # If software-cursor Xorg snippet exists, soft-nudge X clients
  if command -v xdotool >/dev/null 2>&1; then
    # Jiggle once so SW cursor redraws
    xdotool mousemove_relative -- 1 0 2>/dev/null
    xdotool mousemove_relative -- -1 0 2>/dev/null
  fi
}

show_mouse_cursor

# Drop a permanent force-software-cursor conf for next X login if missing
SWC=/etc/X11/xorg.conf.d/20-digivice-swcursor.conf
if [[ ! -f "$SWC" ]] && [[ -w /etc/X11/xorg.conf.d 2>/dev/null || -w /etc/X11 2>/dev/null ]]; then
  mkdir -p /etc/X11/xorg.conf.d 2>/dev/null || true
fi
if [[ -d /etc/X11/xorg.conf.d ]] && [[ ! -f "$SWC" ]] && [[ "$(id -u)" -eq 0 ]]; then
  cat >"$SWC" <<'EOF'
# Digivice: hardware mouse plane often invisible after multi-head on vc4
Section "Device"
    Identifier "Digivice modesetting"
    Driver "modesetting"
    Option "SWcursor" "true"
    Option "ShadowFB" "true"
EndSection
EOF
fi

# Non-root: try write via sudo -n
if [[ ! -f "$SWC" ]] && command -v sudo >/dev/null 2>&1; then
  sudo -n mkdir -p /etc/X11/xorg.conf.d 2>/dev/null || true
  if sudo -n test ! -f "$SWC" 2>/dev/null; then
    sudo -n tee "$SWC" >/dev/null 2>&1 <<'EOF' || true
# Digivice: hardware mouse plane often invisible after multi-head on vc4
Section "Device"
    Identifier "Digivice modesetting"
    Driver "modesetting"
    Option "SWcursor" "true"
    Option "ShadowFB" "true"
EndSection
EOF
  fi
fi

echo "Desktop displays restored (HDMI-first) + cursor reasserted."
