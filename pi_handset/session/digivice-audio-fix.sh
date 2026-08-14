#!/usr/bin/env bash
# Keep C-Media USB audio awake and force a real stream.
# HDMI is irrelevant — this targets solid-LED / silent sticks that work on Windows.
#
#   sudo digivice-audio-fix
#
set +e
set -u

log() { echo "[audio-fix] $*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  echo "sudo digivice-audio-fix" >&2
  exit 1
fi

USER_NAME="${SUDO_USER:-gearsteak}"
[[ "$USER_NAME" == "root" ]] && USER_NAME=gearsteak
for u in gearsteak pi isaac; do
  id "$u" >/dev/null 2>&1 && USER_NAME="$u" && break
done
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
UID_NUM="$(id -u "$USER_NAME")"
RUNTIME="/run/user/$UID_NUM"
as_user() {
  sudo -u "$USER_NAME" -H env XDG_RUNTIME_DIR="$RUNTIME" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=$RUNTIME/bus" "$@"
}

wake_cmedia() {
  echo -1 >/sys/module/usbcore/parameters/autosuspend 2>/dev/null || true
  for d in /sys/bus/usb/devices/*; do
    [[ -f "$d/idVendor" ]] || continue
    [[ "$(cat "$d/idVendor" 2>/dev/null)" == "0d8c" ]] || continue
    echo on >"$d/power/control" 2>/dev/null || true
    echo -1 >"$d/power/autosuspend" 2>/dev/null || true
    echo -1 >"$d/power/autosuspend_delay_ms" 2>/dev/null || true
  done
}

find_usb_card() {
  USB_CARD=""
  while IFS= read -r line; do
    if [[ "$line" =~ ^card\ ([0-9]+): ]]; then
      idx="${BASH_REMATCH[1]}"
      low="$(echo "$line" | tr '[:upper:]' '[:lower:]')"
      echo "$low" | grep -qE 'hdmi|vc4' && continue
      echo "$low" | grep -qE 'usb|device|c-media|audio' || continue
      USB_CARD="$idx"
      break
    fi
  done < <(aplay -l 2>/dev/null)
}

exclusive_beep() {
  # Digivice UI path: stop PipeWire, ALSA exclusive sine, restart PW.
  local rc=1
  _pw_restart() {
    as_user systemctl --user start pipewire wireplumber pipewire-pulse 2>/dev/null || true
  }
  trap _pw_restart EXIT
  wake_cmedia
  sleep 0.3
  find_usb_card
  if [[ -z "$USB_CARD" ]]; then
    log "ERROR: no USB playback card"
    aplay -l 2>&1 || true
    trap - EXIT
    _pw_restart
    return 1
  fi
  mkdir -p /etc/esp-handset
  echo "$USB_CARD" >/etc/esp-handset/alsa-card
  for ctl in Speaker PCM Master Headphone; do
    amixer -c "$USB_CARD" -q sset "$ctl" 100% unmute 2>/dev/null || true
  done
  log "card $USB_CARD · stop PipeWire · exclusive beep"
  as_user systemctl --user stop pipewire-pulse wireplumber pipewire 2>/dev/null || true
  sleep 0.6
  fuser -k "/dev/snd/pcmC${USB_CARD}D0p" 2>/dev/null || true
  sleep 0.15
  log ">>> WATCH RED LED — must BLINK <<<"
  timeout 5 speaker-test -D "plughw:$USB_CARD,0" -c 2 -r 48000 -t sine -f 880 -l 1
  rc=$?
  log "speaker-test exit=$rc"
  trap - EXIT
  _pw_restart
  return "$rc"
}

if [[ "${1:-}" == "--persist-only" ]]; then
  # Install rules + wake devices; no beep
  mkdir -p /etc/udev/rules.d /etc/modprobe.d
  if [[ -f /opt/esp-handset/session/99-digivice-cmedia-nosuspend.rules ]]; then
    install -m 644 /opt/esp-handset/session/99-digivice-cmedia-nosuspend.rules \
      /etc/udev/rules.d/99-digivice-cmedia-nosuspend.rules
  fi
  echo "options usbcore autosuspend=-1" >/etc/modprobe.d/digivice-usb-autosuspend.conf
  wake_cmedia
  udevadm control --reload-rules 2>/dev/null || true
  log "persist OK (no beep)"
  exit 0
fi

if [[ "${1:-}" == "--beep" ]]; then
  exclusive_beep
  exit $?
fi

# 1) Kill USB autosuspend for C-Media (common solid-LED / silent cause on Pi)
log "Disabling USB autosuspend for C-Media…"
mkdir -p /etc/udev/rules.d
cat >/etc/udev/rules.d/99-digivice-cmedia-nosuspend.rules <<'EOF'
# Digivice: C-Media USB audio must not autosuspend (silent + solid LED on Pi)
ACTION=="add|change", SUBSYSTEM=="usb", ATTR{idVendor}=="0d8c", \
  TEST=="power/control", ATTR{power/control}="on"
ACTION=="add|change", SUBSYSTEM=="usb", ATTR{idVendor}=="0d8c", \
  TEST=="power/autosuspend", ATTR{power/autosuspend}="-1"
ACTION=="add|change", SUBSYSTEM=="usb", ATTR{idVendor}=="0d8c", \
  TEST=="power/autosuspend_delay_ms", ATTR{power/autosuspend_delay_ms}="-1"
EOF
udevadm control --reload-rules 2>/dev/null || true

for d in /sys/bus/usb/devices/*; do
  [[ -f "$d/idVendor" ]] || continue
  [[ "$(cat "$d/idVendor" 2>/dev/null)" == "0d8c" ]] || continue
  log "  wake $(basename "$d")"
  echo on >"$d/power/control" 2>/dev/null || true
  echo -1 >"$d/power/autosuspend" 2>/dev/null || true
  echo -1 >"$d/power/autosuspend_delay_ms" 2>/dev/null || true
  # Full device re-auth (same idea as unplug/replug)
  if [[ -f "$d/authorized" ]]; then
    echo 0 >"$d/authorized" 2>/dev/null || true
    sleep 0.6
    echo 1 >"$d/authorized" 2>/dev/null || true
    sleep 1.5
  fi
done

# Also system-wide USB autosuspend off (Pi likes to sleep gadgets)
if [[ -f /sys/module/usbcore/parameters/autosuspend ]]; then
  echo -1 >/sys/module/usbcore/parameters/autosuspend 2>/dev/null || true
  mkdir -p /etc/modprobe.d
  echo "options usbcore autosuspend=-1" >/etc/modprobe.d/digivice-usb-autosuspend.conf
  log "usbcore autosuspend=-1"
fi

sleep 1

# 2) Find USB card
USB_CARD=""
while IFS= read -r line; do
  if [[ "$line" =~ ^card\ ([0-9]+): ]]; then
    idx="${BASH_REMATCH[1]}"
    low="$(echo "$line" | tr '[:upper:]' '[:lower:]')"
    echo "$low" | grep -qE 'hdmi|vc4' && continue
    echo "$low" | grep -qE 'usb|device|c-media|audio' || continue
    USB_CARD="$idx"
    log "card $USB_CARD ← $line"
    break
  fi
done < <(aplay -l 2>/dev/null)

if [[ -z "$USB_CARD" ]]; then
  log "ERROR: no USB playback card after reset"
  aplay -l 2>&1 || true
  exit 1
fi

mkdir -p /etc/esp-handset
echo "$USB_CARD" >/etc/esp-handset/alsa-card
mkdir -p /etc/modprobe.d
cat >/etc/modprobe.d/digivice-usb-audio.conf <<'EOF'
options snd-usb-audio index=0
EOF
cat >/etc/asound.conf <<EOF
defaults.pcm.card $USB_CARD
defaults.ctl.card $USB_CARD
pcm.!default { type plug; slave.pcm "plughw:$USB_CARD,0"; }
ctl.!default { type hw; card $USB_CARD; }
EOF
cp -f /etc/asound.conf "$USER_HOME/.asoundrc" 2>/dev/null || true
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.asoundrc" 2>/dev/null || true

for ctl in Speaker PCM Master Headphone; do
  amixer -c "$USB_CARD" -q sset "$ctl" 100% unmute 2>/dev/null || true
done

# 3) Exclusive beep — PipeWire often holds the device half-asleep
log "Stopping PipeWire for exclusive ALSA…"
as_user systemctl --user stop pipewire-pulse wireplumber pipewire 2>/dev/null || true
sleep 0.8
fuser -k "/dev/snd/pcmC${USB_CARD}D0p" 2>/dev/null || true
sleep 0.2

log ">>> WATCH RED LED — must BLINK (Windows behavior) <<<"
log "beep: plughw:$USB_CARD,0  48000Hz stereo 3s"
timeout 5 speaker-test -D "plughw:$USB_CARD,0" -c 2 -r 48000 -t sine -f 880 -l 1
rc=$?
log "speaker-test exit=$rc"

# Show whether kernel sees an active stream
if [[ -f /proc/asound/card${USB_CARD}/stream0 ]]; then
  log "--- /proc/asound/card${USB_CARD}/stream0 ---"
  cat "/proc/asound/card${USB_CARD}/stream0" 2>/dev/null | head -n 30
fi

log "Starting PipeWire again…"
as_user systemctl --user start pipewire wireplumber pipewire-pulse 2>/dev/null || true
sleep 1

# Point PW at USB if present (not because HDMI was the bug — just restore default)
ID="$(as_user wpctl status 2>/dev/null | awk '
  /Sinks:/ {s=1; next} /Sources:/ {s=0}
  s && /USB|Device|Analog/ && $0 !~ /HDMI|vc4|Vc4/ {
    if (match($0, /[0-9]+/)) { print substr($0, RSTART, RLENGTH); exit }
  }')"
[[ -n "$ID" ]] && as_user wpctl set-default "$ID" 2>/dev/null && log "wpctl default=$ID"

log ""
log "Tell me: did the LED blink during the beep? hear anything?"
exit 0
