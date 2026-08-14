#!/usr/bin/env bash
# Mini CM108 (tiny USB dongle): first ALSA open often fails with -524.
# PipeWire usually has empty Sinks — do not use pw-play.
#
#   bash digivice-cm108-beep.sh
# No sudo required.
#
set +e
echo "=== mini CM108 beep (no PipeWire) ==="
echo "Headphones in GREEN jack. Watch the USB LED."
aplay -l
echo
echo "Waiting 2s (chip wake)…"
sleep 2
amixer -c 0 -q sset Speaker 100% unmute 2>/dev/null
amixer -c 0 -q sset PCM 100% unmute 2>/dev/null

NAME="$(aplay -l 2>/dev/null | awk '/^card 0:/{gsub(/:/,"",$2); print $2; exit}')"
[[ -n "$NAME" ]] || NAME=Device
WAV="/usr/share/sounds/alsa/Front_Center.wav"

play() {
  echo ">> $*"
  "$@"
  return $?
}

ok=1
play aplay -D "sysdefault:CARD=$NAME" "$WAV"
ok=$?
if [[ $ok -ne 0 ]]; then
  echo "retry after 2s (mini CM108 first-open quirk)…"
  sleep 2
  play aplay -D "sysdefault:CARD=$NAME" "$WAV"
  ok=$?
fi
if [[ $ok -ne 0 ]]; then
  sleep 2
  play aplay -D plughw:0,0 "$WAV"
  ok=$?
fi
if [[ $ok -ne 0 ]]; then
  sleep 2
  play speaker-test -D plughw:0,0 -c 2 -r 48000 -t sine -f 880 -l 1
  ok=$?
fi
if [[ $ok -ne 0 ]]; then
  sleep 2
  play speaker-test -D plughw:0,0 -c 1 -r 48000 -t sine -f 880 -l 1
  ok=$?
fi
echo "exit=$ok  (LED blink = USB is streaming)"
exit "$ok"
