#!/usr/bin/env bash
# Software wake for mini CM108 sealed in the Digivice (no unplug).
# First ALSA open often returns -524; we prime the chip so later play works.
#
#   sudo digivice-cm108-wake
#
set +e
log() { echo "[cm108-wake] $*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  exec sudo -n "$0" "$@"
fi

echo -1 >/sys/module/usbcore/parameters/autosuspend 2>/dev/null || true

for d in /sys/bus/usb/devices/*; do
  [[ -f "$d/idVendor" ]] || continue
  [[ "$(cat "$d/idVendor" 2>/dev/null)" == "0d8c" ]] || continue
  echo 1 >"$d/authorized" 2>/dev/null || true
  echo on >"$d/power/control" 2>/dev/null || true
  echo -1 >"$d/power/autosuspend" 2>/dev/null || true
  echo -1 >"$d/power/autosuspend_delay_ms" 2>/dev/null || true
done

# Wait for ALSA (boot: USB enumerates after this service)
for i in 1 2 3 4 5 6 7 8; do
  if aplay -l 2>/dev/null | grep -qiE 'usb|device|c-media'; then
    break
  fi
  sleep 1
done

# Still missing: rebind the USB audio driver (not authorized=0 — that can kill the stick)
if ! aplay -l 2>/dev/null | grep -qiE 'usb|device|c-media'; then
  log "no ALSA card — rebind snd-usb-audio"
  names=()
  for iface in /sys/bus/usb/drivers/snd-usb-audio/*; do
    [[ -e "$iface" ]] || continue
    name="$(basename "$iface")"
    case "$name" in module|uevent|bind|unbind) continue ;; esac
    names+=("$name")
  done
  for name in "${names[@]}"; do
    echo "$name" >/sys/bus/usb/drivers/snd-usb-audio/unbind 2>/dev/null || true
  done
  sleep 1
  for name in "${names[@]}"; do
    echo "$name" >/sys/bus/usb/drivers/snd-usb-audio/bind 2>/dev/null || true
  done
  sleep 2
fi

aplay -l >/dev/null 2>&1
sleep 2

CARD=""
while IFS= read -r line; do
  if [[ "$line" =~ ^card\ ([0-9]+): ]]; then
    idx="${BASH_REMATCH[1]}"
    low="$(echo "$line" | tr '[:upper:]' '[:lower:]')"
    echo "$low" | grep -qE 'hdmi|vc4|bcm2835' && continue
    CARD="$idx"
    echo "$low" | grep -qE 'usb|device|c-media' && break
  fi
done < <(aplay -l 2>/dev/null)
[[ -n "$CARD" ]] || CARD=0

mkdir -p /etc/esp-handset
echo "$CARD" >/etc/esp-handset/alsa-card

for ctl in Speaker PCM Master Headphone; do
  amixer -c "$CARD" -q sset "$ctl" 100% unmute 2>/dev/null || true
done

# Prime with silence so boot does not speak "Front Center". First open may -524.
NAME="$(aplay -l 2>/dev/null | awk -v c="$CARD" '
  $1=="card" && $2==c":" { gsub(/:/,"",$3); print $3; exit }')"
[[ -n "$NAME" ]] || NAME=Device
dd if=/dev/zero bs=1920 count=1 2>/dev/null | \
  timeout 2 aplay -D "sysdefault:CARD=$NAME" -f S16_LE -r 48000 -c 2 >/dev/null 2>&1 || true
sleep 1
dd if=/dev/zero bs=1920 count=1 2>/dev/null | \
  timeout 2 aplay -D "plughw:${CARD},0" -f S16_LE -r 48000 -c 2 >/dev/null 2>&1 || true

alsactl store "$CARD" 2>/dev/null || true
log "ready card=$CARD name=$NAME"
exit 0
