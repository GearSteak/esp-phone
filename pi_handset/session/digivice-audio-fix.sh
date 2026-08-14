#!/usr/bin/env bash
# Digivice: make C-Media USB audio actually stream on Linux (Pi OS Bookworm).
#
# Windows blinks the red LED while playing; Linux often stays solid/silent until
# a USB reset + HDMI sinks are disabled + exclusive ALSA play.
#
#   sudo digivice-audio-fix
#   sudo digivice-audio-fix --beep-only
#
set +e
set -u

log() { echo "[audio-fix] $*"; }

USER_NAME="${SUDO_USER:-}"
if [[ -z "$USER_NAME" || "$USER_NAME" == "root" ]]; then
  USER_NAME="$(logname 2>/dev/null || true)"
fi
if [[ -z "$USER_NAME" || "$USER_NAME" == "root" ]]; then
  for u in gearsteak pi isaac; do
    id "$u" >/dev/null 2>&1 && USER_NAME="$u" && break
  done
fi
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
UID_NUM="$(id -u "$USER_NAME" 2>/dev/null || echo 1000)"
RUNTIME="/run/user/$UID_NUM"

as_user() {
  sudo -u "$USER_NAME" -H env XDG_RUNTIME_DIR="$RUNTIME" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=$RUNTIME/bus" "$@"
}

hard_reset_cmedia() {
  local d sys
  log "Hard-resetting every C-Media USB device…"
  for d in /sys/bus/usb/devices/*; do
    [[ -f "$d/idVendor" ]] || continue
    [[ "$(cat "$d/idVendor" 2>/dev/null)" == "0d8c" ]] || continue
    sys="$(basename "$d")"
    log "  reset $sys (authorized 0→1)"
    if [[ -f "$d/authorized" ]]; then
      echo 0 >"$d/authorized" 2>/dev/null || true
      sleep 0.5
      echo 1 >"$d/authorized" 2>/dev/null || true
    else
      echo "$sys" >/sys/bus/usb/drivers/usb/unbind 2>/dev/null || true
      sleep 0.4
      echo "$sys" >/sys/bus/usb/drivers/usb/bind 2>/dev/null || true
    fi
    sleep 1.5
  done
}

find_usb_card() {
  USB_CARD=""
  while IFS= read -r line; do
    if [[ "$line" =~ ^card\ ([0-9]+): ]]; then
      idx="${BASH_REMATCH[1]}"
      low="$(echo "$line" | tr '[:upper:]' '[:lower:]')"
      echo "$low" | grep -qE 'hdmi|vc4|bcm2835' && continue
      echo "$low" | grep -qE 'usb|device|c-media|audio' || continue
      USB_CARD="$idx"
      log "USB card=$USB_CARD  ($line)"
      return 0
    fi
  done < <(aplay -l 2>/dev/null)
  return 1
}

write_wireplumber_hdmi_off() {
  local dir conf
  for dir in \
    "$USER_HOME/.config/wireplumber/wireplumber.conf.d" \
    /etc/wireplumber/wireplumber.conf.d
  do
    mkdir -p "$dir" 2>/dev/null || continue
    conf="$dir/51-digivice-disable-hdmi.conf"
    cat >"$conf" <<'EOF'
# Digivice — ignore HDMI audio; use USB stick only
monitor.alsa.rules = [
  {
    matches = [
      { node.name = "~alsa_output.*hdmi*" }
      { node.name = "~alsa_output.*vc4*" }
      { device.name = "~alsa_card.*vc4*" }
    ]
    actions = {
      update-props = {
        node.disabled = true
        device.disabled = true
      }
    }
  }
  {
    matches = [
      { node.name = "~alsa_output.*usb*" }
      { node.name = "~alsa_output.*Device*" }
    ]
    actions = {
      update-props = {
        priority.driver = 2000
        priority.session = 2000
      }
    }
  }
]
EOF
    if [[ "$dir" == "$USER_HOME"* ]]; then
      chown -R "$USER_NAME:$USER_NAME" "$USER_HOME/.config/wireplumber" 2>/dev/null || true
    fi
    log "wrote $conf"
  done
}

write_alsa() {
  local c="$1"
  mkdir -p /etc/modprobe.d /etc/esp-handset
  echo "$c" >/etc/esp-handset/alsa-card
  cat >/etc/modprobe.d/digivice-usb-audio.conf <<'EOF'
options snd-usb-audio index=0
EOF
  cat >/etc/asound.conf <<EOF
defaults.pcm.card $c
defaults.ctl.card $c
pcm.!default {
  type plug
  slave.pcm "plughw:$c,0"
}
ctl.!default {
  type hw
  card $c
}
EOF
  if [[ -n "$USER_HOME" ]]; then
    cp -f /etc/asound.conf "$USER_HOME/.asoundrc"
    chown "$USER_NAME:$USER_NAME" "$USER_HOME/.asoundrc" 2>/dev/null || true
  fi
  log "ALSA default → plughw:$c,0"
}

unmute() {
  local c="$1"
  for ctl in Master PCM Speaker Headphone Playback; do
    amixer -c "$c" -q sset "$ctl" 100% unmute 2>/dev/null || true
  done
}

beep_exclusive() {
  local c="$1"
  log "Stopping PipeWire so ALSA can own the USB stick…"
  as_user systemctl --user stop pipewire-pulse wireplumber pipewire 2>/dev/null || true
  sleep 0.8
  fuser -k /dev/snd/* 2>/dev/null || true
  sleep 0.3
  unmute "$c"

  log ">>> WATCH THE RED LED — it must BLINK like on Windows <<<"
  log "Playing 3s sine on plughw:$c,0 @ 48000 S16_LE stereo…"
  # Show stream file in background
  (
    sleep 0.3
    for n in 1 2 3 4 5 6; do
      if [[ -f /proc/asound/card${c}/stream0 ]]; then
        echo "--- stream0 ---"
        head -n 20 "/proc/asound/card${c}/stream0" 2>/dev/null || true
        break
      fi
      sleep 0.2
    done
  ) &

  timeout 5 speaker-test -D "plughw:$c,0" -c 2 -r 48000 -t sine -f 880 -l 1 2>&1 | tail -n 20
  local rc=${PIPESTATUS[0]:-$?}
  log "speaker-test exit=$rc"

  log "Restarting PipeWire…"
  as_user systemctl --user start pipewire wireplumber pipewire-pulse 2>/dev/null || true
  sleep 1.5
  return "$rc"
}

set_pw_default() {
  local id
  id="$(as_user wpctl status 2>/dev/null | awk '
    /Sinks:/ {in_s=1; next}
    /Sources:/ {in_s=0}
    in_s && /USB|Analog|Device/ && $0 !~ /HDMI|Vc4|vc4/ {
      if (match($0, /[0-9]+/)) { print substr($0, RSTART, RLENGTH); exit }
    }
  ')"
  if [[ -n "$id" ]]; then
    as_user wpctl set-default "$id" && log "wpctl default → $id"
    as_user wpctl set-mute "$id" 0 || true
    as_user wpctl set-volume "$id" 1.0 || true
  else
    log "WARN: no USB sink in wpctl yet"
  fi
  as_user wpctl status 2>/dev/null | sed -n '/Sinks:/,/Sources:/p' | head -n 20
}

# --- main ---
if [[ "$(id -u)" -ne 0 ]]; then
  log "need root: sudo digivice-audio-fix"
  exit 1
fi

if [[ "${1:-}" != "--beep-only" ]]; then
  write_wireplumber_hdmi_off
  hard_reset_cmedia
  sleep 1
fi

if ! find_usb_card; then
  log "ERROR: USB audio card not found. Plug the stick into a powered USB port and retry."
  aplay -l 2>&1 || true
  exit 1
fi

if [[ "${1:-}" != "--beep-only" ]]; then
  write_alsa "$USB_CARD"
  # Also run the shared usb helper if present (boost / reset service)
  if [[ -x /usr/local/bin/digivice-audio-usb ]]; then
    /usr/local/bin/digivice-audio-usb 2>/dev/null || true
    find_usb_card || true
  fi
fi

unmute "$USB_CARD"
beep_exclusive "$USB_CARD"
set_pw_default

log ""
log "If LED blinked and you heard it → fixed. Digivice/desktop will use USB."
log "If LED stayed SOLID → unplug stick 5s, plug back, then:"
log "  sudo digivice-audio-fix --beep-only"
log "If LED blinked but still silent → green jack / headphones / amp hardware."
exit 0
