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

USER_NAME="${SUDO_USER:-}"
if [[ -z "$USER_NAME" || "$USER_NAME" == "root" ]]; then
  USER_NAME=""
  for u in gearsteak pi isaac; do
    if id "$u" >/dev/null 2>&1; then
      USER_NAME="$u"
      break
    fi
  done
fi
[[ -n "$USER_NAME" ]] || USER_NAME=pi
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
UID_NUM="$(id -u "$USER_NAME")"
RUNTIME="/run/user/$UID_NUM"
as_user() {
  sudo -u "$USER_NAME" -H env XDG_RUNTIME_DIR="$RUNTIME" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=$RUNTIME/bus" "$@"
}
log "gui_user=$USER_NAME uid=$UID_NUM"

wake_cmedia() {
  echo -1 >/sys/module/usbcore/parameters/autosuspend 2>/dev/null || true
  for d in /sys/bus/usb/devices/*; do
    [[ -f "$d/idVendor" ]] || continue
    [[ "$(cat "$d/idVendor" 2>/dev/null)" == "0d8c" ]] || continue
    # Never leave stick unauthorized (that = no ALSA card + solid/dead LED)
    echo 1 >"$d/authorized" 2>/dev/null || true
    echo on >"$d/power/control" 2>/dev/null || true
    echo -1 >"$d/power/autosuspend" 2>/dev/null || true
    echo -1 >"$d/power/autosuspend_delay_ms" 2>/dev/null || true
  done
}

recover_cmedia() {
  # Bring C-Media back after a bad re-auth / autosuspend
  log "recover C-Media USB…"
  wake_cmedia
  for d in /sys/bus/usb/devices/*; do
    [[ -f "$d/idVendor" ]] || continue
    [[ "$(cat "$d/idVendor" 2>/dev/null)" == "0d8c" ]] || continue
    name="$(basename "$d")"
    log "  force auth+rebind $name"
    echo 1 >"$d/authorized" 2>/dev/null || true
    if [[ -e "$d/driver" ]]; then
      echo "$name" >"$d/driver/unbind" 2>/dev/null || true
      sleep 0.4
    fi
    echo "$name" >/sys/bus/usb/drivers/usb/bind 2>/dev/null || true
    sleep 0.8
    echo 1 >"$d/authorized" 2>/dev/null || true
    echo on >"$d/power/control" 2>/dev/null || true
  done
  # HDMI/vc4 already owns card 0. Pinning USB to index=0 makes probe fail:
  # lsusb still shows 0d8c, but /proc/asound/cards stays HDMI-only.
  mkdir -p /etc/modprobe.d
  cat >/etc/modprobe.d/digivice-usb-audio.conf <<'EOF'
options snd-usb-audio ignore_ctl_error=1
EOF
  modprobe -r snd-usb-audio 2>/dev/null || true
  modprobe snd-usb-audio 2>/dev/null || true
  sleep 1.2
  log "lsusb C-Media:"
  lsusb 2>/dev/null | grep -i '0d8c\|c-media\|audio' | while read -r l; do log "  $l"; done
  log "aplay -l:"
  aplay -l 2>&1 | while read -r l; do log "  $l"; done
}

find_usb_card() {
  USB_CARD=""
  # 1) Prefer USB / C-Media style names
  while IFS= read -r line; do
    if [[ "$line" =~ ^card\ ([0-9]+): ]]; then
      idx="${BASH_REMATCH[1]}"
      low="$(echo "$line" | tr '[:upper:]' '[:lower:]')"
      echo "$low" | grep -qE 'hdmi|vc4|bcm2835' && continue
      if echo "$low" | grep -qE 'usb|device|c-media|audio|headset|pn[np]'; then
        USB_CARD="$idx"
        log "card $USB_CARD ← $line"
        return 0
      fi
    fi
  done < <(aplay -l 2>/dev/null)
  # 2) Any non-HDMI playback card (cheap sticks often name oddly)
  while IFS= read -r line; do
    if [[ "$line" =~ ^card\ ([0-9]+): ]]; then
      idx="${BASH_REMATCH[1]}"
      low="$(echo "$line" | tr '[:upper:]' '[:lower:]')"
      echo "$low" | grep -qE 'hdmi|vc4|bcm2835' && continue
      USB_CARD="$idx"
      log "card $USB_CARD (fallback) ← $line"
      return 0
    fi
  done < <(aplay -l 2>/dev/null)
  return 1
}

exclusive_beep() {
  # Keep identical to the full-script exclusive section (what works in the terminal).
  local rc=1
  _pw_restart() {
    as_user systemctl --user start pipewire wireplumber pipewire-pulse 2>/dev/null || true
  }
  trap _pw_restart EXIT
  recover_cmedia
  find_usb_card || true
  if [[ -z "${USB_CARD:-}" ]]; then
    log "ERROR: no USB playback card"
    aplay -l 2>&1 || true
    trap - EXIT
    _pw_restart
    return 1
  fi
  mkdir -p /etc/esp-handset
  echo "$USB_CARD" >/etc/esp-handset/alsa-card
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
  recover_cmedia
  udevadm control --reload-rules 2>/dev/null || true
  log "persist OK (no beep)"
  exit 0
fi

if [[ "${1:-}" == "--recover" ]]; then
  recover_cmedia
  find_usb_card || true
  if [[ -n "${USB_CARD:-}" ]]; then
    log "OK card=$USB_CARD"
    exit 0
  fi
  log "FAIL: stick not in ALSA — unplug/replug USB audio, then retry"
  exit 1
fi

if [[ "${1:-}" == "--beep" ]]; then
  exclusive_beep
  exit $?
fi

if [[ "${1:-}" == "--soft-beep" || "${1:-}" == "--ui-beep" ]]; then
  # Digivice Debug BEEP — must match working CLI exclusive path.
  # Stick: C-Media USB (Amazon green=headphones / pink=mic).
  wake_cmedia
  find_usb_card || true
  if [[ -z "${USB_CARD:-}" ]]; then
    log "no card yet — recover…"
    recover_cmedia
    find_usb_card || true
  fi
  if [[ -z "${USB_CARD:-}" ]]; then
    log "ERROR: no USB card"
    lsusb 2>&1 | while read -r l; do log "  $l"; done
    aplay -l 2>&1 | while read -r l; do log "  $l"; done
    exit 1
  fi
  mkdir -p /etc/esp-handset
  echo "$USB_CARD" >/etc/esp-handset/alsa-card
  log "ui-beep card=$USB_CARD user=$USER_NAME"

  # Crank every playback control (C-Media often resets mute)
  while IFS= read -r line; do
    ctl="${line#Simple mixer control \'}"
    ctl="${ctl%%\',*}"
    [[ -n "$ctl" ]] || continue
    case "$ctl" in
      Mic*|Capture*|Auto*) continue ;;
    esac
    amixer -c "$USB_CARD" -q sset "$ctl" 100% unmute 2>/dev/null || true
  done < <(amixer -c "$USB_CARD" scontrols 2>/dev/null)
  for ctl in Speaker PCM Master Headphone Playback; do
    amixer -c "$USB_CARD" -q sset "$ctl" 100% unmute 2>/dev/null || true
  done
  log "mixer:"
  amixer -c "$USB_CARD" sget Speaker 2>/dev/null | head -n 8 | while read -r l; do log "  $l"; done
  amixer -c "$USB_CARD" sget PCM 2>/dev/null | head -n 8 | while read -r l; do log "  $l"; done

  log "stop PipeWire for $USER_NAME"
  timeout 2 as_user systemctl --user stop pipewire-pulse wireplumber pipewire 2>/dev/null || true
  sleep 0.5
  fuser -k "/dev/snd/pcmC${USB_CARD}D0p" 2>/dev/null || true
  sleep 0.2
  for ctl in Speaker PCM Master Headphone; do
    amixer -c "$USB_CARD" -q sset "$ctl" 100% unmute 2>/dev/null || true
  done

  # Full-scale mono 880Hz 2s — same path CLI uses, clearer than speaker-test
  BEEP_WAV="/tmp/digivice-ui-beep.wav"
  python3 - <<'PY'
import math, struct, wave
path = "/tmp/digivice-ui-beep.wav"
rate, secs, freq = 48000, 2.0, 880.0
n = int(rate * secs)
with wave.open(path, "w") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(rate)
    for i in range(n):
        v = int(32000 * math.sin(2 * math.pi * freq * i / rate))
        w.writeframes(struct.pack("<h", v))
PY
  log ">>> LISTEN NOW (green jack) LED should blink ~2s <<<"
  if [[ -f "$BEEP_WAV" ]]; then
    timeout 4 aplay -D "plughw:$USB_CARD,0" -q "$BEEP_WAV"
    rc=$?
    log "aplay exit=$rc"
  else
    timeout 5 speaker-test -D "plughw:$USB_CARD,0" -c 1 -r 48000 -t sine -f 880 -l 1
    rc=$?
    log "speaker-test exit=$rc"
  fi
  timeout 2 as_user systemctl --user start pipewire wireplumber pipewire-pulse 2>/dev/null || true
  exit "$rc"
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

# Soft recover only — do NOT authorized=0 (that can leave stick dead / no ALSA card)
recover_cmedia

# Also system-wide USB autosuspend off (Pi likes to sleep gadgets)
if [[ -f /sys/module/usbcore/parameters/autosuspend ]]; then
  echo -1 >/sys/module/usbcore/parameters/autosuspend 2>/dev/null || true
  mkdir -p /etc/modprobe.d
  echo "options usbcore autosuspend=-1" >/etc/modprobe.d/digivice-usb-autosuspend.conf
  log "usbcore autosuspend=-1"
fi

sleep 0.5

# 2) Find USB card
find_usb_card || true

if [[ -z "${USB_CARD:-}" ]]; then
  log "ERROR: no USB playback card after reset"
  aplay -l 2>&1 || true
  lsusb 2>&1 || true
  exit 1
fi

mkdir -p /etc/esp-handset
echo "$USB_CARD" >/etc/esp-handset/alsa-card
mkdir -p /etc/modprobe.d
cat >/etc/modprobe.d/digivice-usb-audio.conf <<'EOF'
options snd-usb-audio ignore_ctl_error=1
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
