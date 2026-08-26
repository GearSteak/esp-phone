#!/usr/bin/env bash
# Pi 4 headphone jack + USB dongle — mirror playback to BOTH (ALSA tee).
# Capture stays on USB when present (jack is playback-only).
set -euo pipefail

USER_NAME="${SUDO_USER:-${DIGIVICE_USER:-$USER}}"
USER_HOME="$(getent passwd "$USER_NAME" 2>/dev/null | cut -d: -f6 || echo "/home/$USER_NAME")"
ROUTE_FILE="$USER_HOME/.esp-handset/audio_route"

log() { echo "[digivice-dual-audio] $*"; }

card_short() {
  sed -n 's/^card [0-9]*: \([^ ]*\) .*/\1/p' <<<"$1"
}

find_hp() {
  HP_CARD="" HP_NAME=""
  while IFS= read -r line; do
    [[ "$line" =~ ^card\ ([0-9]+): ]] || continue
    idx="${BASH_REMATCH[1]}"
    low="$(tr '[:upper:]' '[:lower:]' <<<"$line")"
    echo "$low" | grep -qE 'hdmi|vc4' && continue
    echo "$low" | grep -qE 'headphone|bcm2835' || continue
    HP_CARD="$idx"
    HP_NAME="$(card_short "$line")"
    log "headphone card $HP_CARD ($HP_NAME)"
    return 0
  done < <(aplay -l 2>/dev/null || true)
  return 1
}

find_usb() {
  USB_CARD="" USB_NAME=""
  while IFS= read -r line; do
    [[ "$line" =~ ^card\ ([0-9]+): ]] || continue
    idx="${BASH_REMATCH[1]}"
    low="$(tr '[:upper:]' '[:lower:]' <<<"$line")"
    echo "$low" | grep -qE 'hdmi|vc4|headphone|bcm2835' && continue
    if echo "$low" | grep -qE 'usb|device|c-media|cm10|headset|audio|pn[p]?'; then
      USB_CARD="$idx"
      USB_NAME="$(card_short "$line")"
      log "USB card $USB_CARD ($USB_NAME)"
      return 0
    fi
  done < <(aplay -l 2>/dev/null || true)
  while IFS= read -r line; do
    [[ "$line" =~ ^card\ ([0-9]+): ]] || continue
    idx="${BASH_REMATCH[1]}"
    low="$(tr '[:upper:]' '[:lower:]' <<<"$line")"
    echo "$low" | grep -qE 'hdmi|vc4|headphone|bcm2835' && continue
    USB_CARD="$idx"
    USB_NAME="$(card_short "$line")"
    log "USB fallback card $USB_CARD ($USB_NAME)"
    return 0
  done < <(aplay -l 2>/dev/null || true)
  return 1
}

unmute_card() {
  local c="$1"
  for ctl in PCM Headphone Master Speaker; do
    amixer -c "$c" sset "$ctl" 90% unmute 2>/dev/null || true
  done
}

write_asound() {
  local body="$1"
  mkdir -p /etc/esp-handset "$USER_HOME/.esp-handset"
  printf '%s\n' "$body" >/etc/asound.conf
  cp -f /etc/asound.conf "$USER_HOME/.asoundrc" 2>/dev/null || true
  chown "$USER_NAME:$USER_NAME" "$USER_HOME/.asoundrc" 2>/dev/null || true
}

if ! command -v aplay >/dev/null 2>&1; then
  log "aplay missing"
  exit 0
fi

find_hp || true
find_usb || true

mkdir -p "$USER_HOME/.esp-handset"
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset" 2>/dev/null || true

if [[ -n "${HP_CARD:-}" && -n "${USB_CARD:-}" ]]; then
  log "mode=dual — playback → jack + USB"
  write_asound "# Digivice — mirror playback to Pi jack + USB dongle
pcm.digivice_hp {
  type plug
  slave.pcm \"plughw:CARD=${HP_NAME},DEV=0\"
}
pcm.digivice_usb_raw {
  type plug
  slave.pcm \"plughw:CARD=${USB_NAME},DEV=0\"
}
pcm.digivice_usb {
  type softvol
  slave.pcm \"digivice_usb_raw\"
  control {
    name \"Digivice Boost\"
    card ${USB_NAME}
  }
  min_dB -5.0
  max_dB 18.0
}
pcm.digivice_dual {
  type plug
  slave.pcm {
    type tee
    slave.pcm \"digivice_hp\"
    slave {
      pcm \"digivice_usb\"
      format \"same\"
    }
  }
}
pcm.!default {
  type plug
  slave.pcm \"digivice_dual\"
}
ctl.!default {
  type hw
  card ${USB_NAME}
}
defaults.pcm.card ${USB_CARD}
defaults.ctl.card ${USB_CARD}
"
  echo dual >"$ROUTE_FILE"
  unmute_card "$HP_CARD"
  unmute_card "$USB_CARD"
elif [[ -n "${USB_CARD:-}" ]]; then
  log "mode=usb — USB dongle only"
  write_asound "# Digivice — USB audio
defaults.pcm.card ${USB_CARD}
defaults.ctl.card ${USB_CARD}
pcm.!default { type plug; slave.pcm \"plughw:${USB_CARD},0\"; }
ctl.!default { type hw; card ${USB_CARD}; }
"
  echo usb >"$ROUTE_FILE"
  unmute_card "$USB_CARD"
elif [[ -n "${HP_CARD:-}" ]]; then
  log "mode=jack — Pi headphone only"
  write_asound "# Digivice — Pi 3.5 mm jack
defaults.pcm.card ${HP_CARD}
defaults.ctl.card ${HP_CARD}
pcm.!default { type plug; slave.pcm \"plughw:${HP_CARD},0\"; }
ctl.!default { type hw; card ${HP_CARD}; }
"
  echo jack >"$ROUTE_FILE"
  unmute_card "$HP_CARD"
else
  log "no playback cards found"
  echo unknown >"$ROUTE_FILE"
fi

chown "$USER_NAME:$USER_NAME" "$ROUTE_FILE" 2>/dev/null || true
# Prime default PCM (tee)
timeout 1 aplay -D default /dev/zero 2>/dev/null || true
log "done — route=$(cat "$ROUTE_FILE" 2>/dev/null || echo ?)"
