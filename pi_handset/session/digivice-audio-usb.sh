#!/usr/bin/env bash
# Force Digivice / desktop audio to the USB sound card (not HDMI).
#   digivice-audio-usb
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

# Find first non-HDMI / non-vc4 playback card index
USB_CARD=""
while IFS= read -r line; do
  # card 1: Device [Device], device 0: USB Audio [USB Audio]
  if [[ "$line" =~ ^card\ ([0-9]+): ]]; then
    idx="${BASH_REMATCH[1]}"
    low="$(echo "$line" | tr '[:upper:]' '[:lower:]')"
    if echo "$low" | grep -qE 'hdmi|vc4|headphones bcm|bcm2835'; then
      continue
    fi
    USB_CARD="$idx"
    log "ALSA card $USB_CARD ← $line"
    break
  fi
done < <(aplay -l 2>/dev/null)

if [[ -z "$USB_CARD" ]]; then
  # Fallback: highest card index often USB on Pi
  USB_CARD="$(aplay -l 2>/dev/null | sed -n 's/^card \([0-9]*\):.*/\1/p' | tail -n1)"
  log "fallback ALSA card=$USB_CARD"
fi

if [[ -z "$USB_CARD" ]]; then
  log "ERROR: no ALSA playback cards (aplay -l empty)"
  exit 1
fi

mkdir -p /etc/esp-handset
echo "$USB_CARD" >/etc/esp-handset/alsa-card
cat >/etc/asound.conf <<EOF
# Digivice — prefer USB sound card (written by digivice-audio-usb)
defaults.pcm.card $USB_CARD
defaults.ctl.card $USB_CARD
pcm.!default {
  type hw
  card $USB_CARD
}
ctl.!default {
  type hw
  card $USB_CARD
}
EOF
log "wrote /etc/asound.conf → card $USB_CARD"

if [[ -n "$USER_HOME" ]]; then
  cat >"$USER_HOME/.asoundrc" <<EOF
defaults.pcm.card $USB_CARD
defaults.ctl.card $USB_CARD
EOF
  chown "$USER_NAME:$USER_NAME" "$USER_HOME/.asoundrc" 2>/dev/null || true
fi

# Unmute
for ctl in Master PCM Speaker Headphone Playback; do
  amixer -c "$USB_CARD" -q sset "$ctl" 100% unmute 2>/dev/null || true
done
amixer -c "$USB_CARD" -q sset 'Auto-Mute Mode' Disabled 2>/dev/null || true

# PipeWire / Pulse default sink matching USB / alsa_card
as_user() {
  sudo -u "$USER_NAME" -H env XDG_RUNTIME_DIR="$RUNTIME" DBUS_SESSION_BUS_ADDRESS="unix:path=$RUNTIME/bus" "$@"
}

SINK=""
if as_user pactl list short sinks >/dev/null 2>&1; then
  SINK="$(as_user pactl list short sinks 2>/dev/null | awk '{print $2}' | grep -iE 'usb|alsa_output' | grep -viE 'hdmi|vc4' | head -n1)"
  if [[ -z "$SINK" ]]; then
    SINK="$(as_user pactl list short sinks 2>/dev/null | awk '{print $2}' | grep -viE 'hdmi|vc4' | head -n1)"
  fi
  if [[ -n "$SINK" ]]; then
    as_user pactl set-default-sink "$SINK" 2>/dev/null && log "pactl default sink → $SINK"
    as_user pactl set-sink-mute "$SINK" 0 2>/dev/null || true
    as_user pactl set-sink-volume "$SINK" 100% 2>/dev/null || true
  else
    log "WARN: no non-HDMI Pulse sink found"
  fi
fi

if as_user wpctl status >/dev/null 2>&1; then
  # Pick first Sink id that looks like USB / not HDMI
  ID="$(as_user wpctl status 2>/dev/null | awk '
    /Sinks:/ {in_s=1; next}
    /Sources:/ {in_s=0}
    in_s && /^[[:space:]]*\*?[[:space:]]*[0-9]+\./ {
      line=$0
      if (line ~ /HDMI|Vc4|vc4/) next
      if (match(line, /[0-9]+/)) { print substr(line, RSTART, RLENGTH); exit }
    }')"
  if [[ -n "$ID" ]]; then
    as_user wpctl set-default "$ID" 2>/dev/null && log "wpctl default → $ID"
    as_user wpctl set-mute "$ID" 0 2>/dev/null || true
    as_user wpctl set-volume "$ID" 1.0 2>/dev/null || true
  fi
fi

log "Test:  speaker-test -D hw:$USB_CARD,0 -t sine -f 880 -l 1 -c 1"
log "Or:    speaker-test -c 1 -t sine -f 880 -l 1"
log "If ALSA plays with no error but silence → jack detect / need amp (see digivice-audio-doctor)"
exit 0
