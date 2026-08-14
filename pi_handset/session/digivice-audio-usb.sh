#!/usr/bin/env bash
# Force Digivice / desktop audio to the USB sound card (not HDMI).
# Fixes common C-Media 0d8c:0012 issues on Pi:
#   • asound default uses plug (not raw hw)
#   • softvol boost (passive speakers are quiet on green jack)
#   • USB reset after boot (known "solid LED / silent until replug")
#   • PipeWire default sink → USB + volume up
#
#   digivice-audio-usb
#   digivice-audio-usb --reset-only
#
set +e
set -u

log() { echo "[audio-usb] $*"; }

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

# --- reset C-Media USB (Windows blinks when streaming; Linux often needs replug) ---
reset_cmedia() {
  local d sys
  for d in /sys/bus/usb/devices/*; do
    [[ -f "$d/idVendor" && -f "$d/idProduct" ]] || continue
    if [[ "$(cat "$d/idVendor" 2>/dev/null)" == "0d8c" ]]; then
      sys="$(basename "$d")"
      log "USB reset C-Media at $sys"
      echo "$sys" >/sys/bus/usb/drivers/usb/unbind 2>/dev/null || true
      sleep 0.4
      echo "$sys" >/sys/bus/usb/drivers/usb/bind 2>/dev/null || true
      sleep 1.2
    fi
  done
  if command -v usbreset >/dev/null 2>&1; then
    usbreset 0d8c:0012 2>/dev/null || true
  fi
}

find_usb_card() {
  USB_CARD=""
  USB_NAME=""
  while IFS= read -r line; do
    if [[ "$line" =~ ^card\ ([0-9]+):\ ([^ ]+) ]]; then
      idx="${BASH_REMATCH[1]}"
      name="${BASH_REMATCH[2]}"
      low="$(echo "$line" | tr '[:upper:]' '[:lower:]')"
      if echo "$low" | grep -qE 'hdmi|vc4|headphones bcm|bcm2835'; then
        continue
      fi
      if echo "$low" | grep -qE 'usb|device|c-media|audio'; then
        USB_CARD="$idx"
        USB_NAME="$name"
        return 0
      fi
    fi
  done < <(aplay -l 2>/dev/null)
  USB_CARD="$(aplay -l 2>/dev/null | sed -n 's/^card \([0-9]*\):.*/\1/p' | tail -n1)"
  USB_NAME="$(aplay -l 2>/dev/null | sed -n "s/^card ${USB_CARD}: \([^ ]*\).*/\1/p" | head -n1)"
  [[ -n "$USB_CARD" ]]
}

unmute_card() {
  local c="$1"
  for ctl in Master PCM Speaker Headphone Playback; do
    amixer -c "$c" -q sset "$ctl" 100% unmute 2>/dev/null || true
  done
  amixer -c "$c" -q sset 'Auto-Mute Mode' Disabled 2>/dev/null || true
  amixer -c "$c" -q sset 'Digivice Boost' 90% 2>/dev/null || true
}

if [[ "${1:-}" == "--reset-only" ]]; then
  reset_cmedia
  sleep 1
  if find_usb_card; then
    unmute_card "$USB_CARD"
  fi
  exit 0
fi

reset_cmedia

# Prefer USB as ALSA card 0 next boot
mkdir -p /etc/modprobe.d
cat >/etc/modprobe.d/digivice-usb-audio.conf <<'EOF'
# Digivice: put USB audio first
options snd-usb-audio index=0
EOF
log "wrote /etc/modprobe.d/digivice-usb-audio.conf"

if ! find_usb_card; then
  log "ERROR: no ALSA playback cards — plug USB audio and retry"
  exit 1
fi
log "ALSA card $USB_CARD ($USB_NAME)"

mkdir -p /etc/esp-handset
echo "$USB_CARD" >/etc/esp-handset/alsa-card

SLAVE="plughw:${USB_CARD},0"
if [[ -n "$USB_NAME" ]]; then
  SLAVE="plughw:CARD=${USB_NAME},DEV=0"
fi

# plug + softvol (raw "type hw" breaks rates / stays silent for many apps)
cat >/etc/asound.conf <<EOF
# Digivice — USB out with software boost (green jack is line/headphone level)
defaults.pcm.card $USB_CARD
defaults.ctl.card $USB_CARD

pcm.digiraw {
  type plug
  slave.pcm "$SLAVE"
}

pcm.digiboost {
  type softvol
  slave.pcm "digiraw"
  control {
    name "Digivice Boost"
    card $USB_CARD
  }
  min_dB -5.0
  max_dB 18.0
}

pcm.!default {
  type plug
  slave.pcm "digiboost"
}

ctl.!default {
  type hw
  card $USB_CARD
}
EOF
log "wrote /etc/asound.conf → $SLAVE + Digivice Boost"

if [[ -n "$USER_HOME" ]]; then
  cp -f /etc/asound.conf "$USER_HOME/.asoundrc"
  chown "$USER_NAME:$USER_NAME" "$USER_HOME/.asoundrc" 2>/dev/null || true
fi

unmute_card "$USB_CARD"
# Instantiate softvol control
timeout 1 aplay -D default /dev/zero 2>/dev/null || true
unmute_card "$USB_CARD"

ID="$(as_user wpctl status 2>/dev/null | awk '
  /Sinks:/ {in_s=1; next}
  /Sources:/ {in_s=0}
  in_s && /USB|Analog/ && $0 !~ /HDMI|Vc4|vc4/ {
    if (match($0, /[0-9]+/)) { print substr($0, RSTART, RLENGTH); exit }
  }
  in_s && /^[ \t]*\*?[ \t]*[0-9]+\./ && $0 !~ /HDMI|Vc4|vc4/ {
    if (match($0, /[0-9]+/)) { print substr($0, RSTART, RLENGTH); exit }
  }
')"
if [[ -n "$ID" ]]; then
  as_user wpctl set-default "$ID" 2>/dev/null && log "wpctl default → $ID"
  as_user wpctl set-mute "$ID" 0 2>/dev/null || true
  as_user wpctl set-volume "$ID" 1.5 2>/dev/null \
    || as_user wpctl set-volume "$ID" 1.0 2>/dev/null || true
fi

cat >/etc/systemd/system/digivice-audio-usb-reset.service <<'EOF'
[Unit]
Description=Reset C-Media USB audio after boot (solid-LED / silent until replug)
After=multi-user.target sound.target
Wants=sound.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/digivice-audio-usb --reset-only
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload 2>/dev/null || true
systemctl enable digivice-audio-usb-reset.service 2>/dev/null || true

log "Watch the RED LED — it should BLINK during this beep (like Windows):"
log "  speaker-test -D plughw:$USB_CARD,0 -c 2 -t sine -f 880 -l 2"
log "If LED stays solid: unplug/replug the USB stick, then rerun digivice-audio-usb."
log "Quiet speakers: green jack is weak into passive speakers — louder drivers help a"
log "  little; a small amp or MAX98357 helps a lot. Boost: alsamixer -c $USB_CARD"
exit 0
