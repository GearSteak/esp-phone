#!/usr/bin/env bash
# Pi 4 onboard 3.5 mm headphone jack — unmute PCM for VoIP + UI beeps.
set -euo pipefail

log() { echo "[digivice-analog-audio] $*"; }

if ! command -v aplay >/dev/null 2>&1; then
  log "aplay missing"
  exit 0
fi

# Find Headphones / bcm2835 cards (skip HDMI)
while IFS= read -r line; do
  card="$(sed -n 's/^card \([0-9]*\):.*/\1/p' <<<"$line")"
  [[ -z "$card" ]] && continue
  low="$(tr '[:upper:]' '[:lower:]' <<<"$line")"
  echo "$low" | grep -qE 'hdmi|vc4' && continue
  echo "$low" | grep -qE 'headphone|bcm2835' || continue
  log "card $card: $line"
  amixer -c "$card" sset PCM 90% unmute 2>/dev/null || true
  amixer -c "$card" sset Headphone 90% unmute 2>/dev/null || true
  amixer -c "$card" sset Master 90% unmute 2>/dev/null || true
done < <(aplay -l 2>/dev/null || true)

log "done — plug headphones into Pi 3.5 mm jack"
