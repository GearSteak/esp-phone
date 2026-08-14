#!/usr/bin/env bash
# Digivice USB / ALSA / PipeWire audio doctor.
#   digivice-audio-doctor
# Writes: ~/.esp-handset/audio-doctor.txt  (+ /tmp/digivice-audio-doctor.txt)
#
set +e
set -u

OUT_DIR="${HOME:-/tmp}/.esp-handset"
mkdir -p "$OUT_DIR" /tmp 2>/dev/null || true
OUT="$OUT_DIR/audio-doctor.txt"
OUT2="/tmp/digivice-audio-doctor.txt"

if [[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  UH="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
  if [[ -n "$UH" ]]; then
    OUT_DIR="$UH/.esp-handset"
    mkdir -p "$OUT_DIR"
    OUT="$OUT_DIR/audio-doctor.txt"
    chown "$SUDO_USER:$SUDO_USER" "$OUT_DIR" 2>/dev/null || true
  fi
fi

run_as_user() {
  if [[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    sudo -u "$SUDO_USER" -H env XDG_RUNTIME_DIR="/run/user/$(id -u "$SUDO_USER")" "$@"
  else
    "$@"
  fi
}

{
  echo "=== digivice-audio-doctor $(date -Iseconds) ==="
  echo "host=$(hostname) user=$(id -un)"
  echo

  echo "--- USB audio devices ---"
  lsusb 2>/dev/null | grep -iE 'audio|sound|c-media|cm10|pcm27|headset|speaker' || echo "(no obvious USB audio in lsusb)"
  echo
  lsusb 2>/dev/null | head -n 40
  echo

  echo "--- ALSA cards (aplay -l) ---"
  aplay -l 2>&1 || echo "aplay missing"
  echo
  echo "--- ALSA capture (arecord -l) ---"
  arecord -l 2>&1 || echo "arecord missing"
  echo

  echo "--- /proc/asound ---"
  cat /proc/asound/cards 2>&1
  echo
  ls -l /dev/snd/ 2>&1
  echo

  echo "--- default PCM ---"
  echo -n "aplay -L default: "
  aplay -L 2>/dev/null | head -n 20
  echo
  cat /etc/asound.conf 2>/dev/null || echo "(no /etc/asound.conf)"
  echo
  cat "${HOME}/.asoundrc" 2>/dev/null || true
  if [[ -n "${SUDO_USER:-}" ]]; then
    cat "$(getent passwd "$SUDO_USER" | cut -d: -f6)/.asoundrc" 2>/dev/null || true
  fi
  echo

  echo "--- PipeWire / Pulse sinks ---"
  run_as_user wpctl status 2>&1 | head -n 80 || true
  run_as_user pactl info 2>&1 | head -n 40 || true
  run_as_user pactl list short sinks 2>&1 || true
  run_as_user pactl list short sources 2>&1 || true
  echo

  echo "--- amixer (each card) ---"
  for c in 0 1 2 3; do
    if aplay -l 2>/dev/null | grep -q "card $c:"; then
      echo "## card $c"
      amixer -c "$c" scontents 2>&1 | head -n 80
      echo
      # Common mute killers on USB dongles
      amixer -c "$c" sget Master 2>&1 | head -n 12 || true
      amixer -c "$c" sget PCM 2>&1 | head -n 12 || true
      amixer -c "$c" sget Speaker 2>&1 | head -n 12 || true
      amixer -c "$c" sget Headphone 2>&1 | head -n 12 || true
      amixer -c "$c" sget 'Auto-Mute Mode' 2>&1 | head -n 12 || true
      echo
    fi
  done

  echo "--- forced unmute + max (best-effort) ---"
  for c in 0 1 2 3; do
    if aplay -l 2>/dev/null | grep -q "card $c:"; then
      for ctl in Master PCM Speaker Headphone Playback; do
        amixer -c "$c" -q sset "$ctl" 100% unmute 2>/dev/null || true
      done
      amixer -c "$c" -q sset 'Auto-Mute Mode' Disabled 2>/dev/null || true
      echo "card $c: unmute attempted"
    fi
  done
  echo

  echo "--- play test to each hw:N,0 (1s sine via speaker-test) ---"
  if command -v speaker-test >/dev/null; then
    for c in 0 1 2 3; do
      if aplay -l 2>/dev/null | grep -q "card $c:"; then
        echo ">> speaker-test -D hw:$c,0 (2s)…"
        timeout 3 speaker-test -D "hw:$c,0" -t sine -f 880 -l 1 -c 2 2>&1 | tail -n 8
        echo "exit=$?"
      fi
    done
  else
    echo "speaker-test missing (apt install alsa-utils)"
  fi
  echo

  echo "--- jack / solder notes ---"
  cat <<'NOTE'
Do NOT assume plug bands = PCB pads.

On many USB-audio 3.5mm jack footprints (what you solder):
  Middle lug / pad = Ground
  Outer pads       = Tip (L) and Ring (R) — order varies by jack

Mono speaker:
  Ground → middle pad
  Signal → one outer pad (or both outers tied together for L+R)

Plug bands (only if using a plug cable) tip→ring→sleeve = L / R / GND —
that is NOT the same as PCB pad order. Trust continuity: meter from
middle pad to plug sleeve should beep if middle is really GND.

If Linux plays OK (no aplay error) but you hear NOTHING:
  1) Output may still be HDMI — default sink wrong (run digivice-audio-usb)
  2) USB card Auto-Mute until jack DETECT closes
     → plug a real 3.5mm plug, or bridge jack-detect pads on the PCB
  3) Bare 8Ω speaker on headphone jack is often inaudible — need a small amp
     (MAX98357 / PAM8403) between USB DAC and speaker
  4) Signal on GND pad / open joint = silence
NOTE
  echo
  echo "=== end ==="
} | tee "$OUT" | tee "$OUT2"

if [[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  chown "$SUDO_USER:$SUDO_USER" "$OUT" 2>/dev/null || true
fi

echo
echo "Report: $OUT"
echo "Also:   $OUT2"
echo "Transfer: Prep audio report → http://<pi>:8765/diag/audio.txt"
exit 0
