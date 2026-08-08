#!/usr/bin/env bash
# Turn SPI panel ON for Digivice (do not leave it blank).
# Digivice app paints natively on SPI; HDMI gets a software scaled copy.
# Prefer: keep HDMI on too so Qt sees both screens.
#
set +e
set -u
LOG="${HOME}/.esp-handset/handset.log"
mkdir -p "${HOME}/.esp-handset" 2>/dev/null
log() { echo "[digivice-layout] $*" | tee -a "$LOG" >&2; }

export DISPLAY="${DISPLAY:-:0}"

# backlight
for d in /sys/class/backlight/*; do
  [[ -d "$d" ]] || continue
  echo 0 >"$d/bl_power" 2>/dev/null || true
  [[ -r "$d/max_brightness" ]] && cat "$d/max_brightness" >"$d/brightness" 2>/dev/null || true
  log "backlight $d"
done

if ! command -v xrandr >/dev/null 2>&1 || ! xrandr --query >/dev/null 2>&1; then
  log "no xrandr/X — SPI may only work if already active"
  exit 0
fi

mapfile -t OUTS < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
log "connected: ${OUTS[*]:-none}"

SPI=""; HDMI=""
# mipi-dbi-spi panels often appear as Unknown19-1 (not SPI-1) under KMS
for o in "${OUTS[@]:-}"; do
  case "$o" in
    HDMI*|hdmi*|DP-*|DisplayPort*) HDMI="${HDMI:-$o}" ;;
    *SPI*|*DPI*|*DSI*|*PANEL*|[Uu]nknown*) SPI="$o" ;;
  esac
done

# Prefer exact phone modes if several Unknown* / small outs exist
if [[ -z "$SPI" ]] || [[ "${#OUTS[@]}" -gt 1 ]]; then
  best=999999999
  pick=""
  for o in "${OUTS[@]:-}"; do
    case "$o" in HDMI*|hdmi*|DP-*) continue ;; esac
    area=$(xrandr --query 2>/dev/null | awk -v n="$o" '
      $0 ~ ("^" n " connected") {p=1;next}
      p && $1 ~ /^[0-9]+x[0-9]+/ {split($1,a,"x"); print (a[1]+0)*(a[2]+0); exit}
      p && /^[^ ]/ {exit}')
    area="${area:-0}"
    # favor 240x320 / 320x240 (~76800)
    if [[ "$area" -eq 76800 ]]; then
      pick=$o; best=$area; break
    fi
    if [[ "$area" -gt 1000 && "$area" -lt 500000 && "$area" -lt "$best" ]]; then
      best=$area; pick=$o
    fi
  done
  [[ -n "$pick" ]] && SPI="$pick"
fi

if [[ -z "$SPI" ]]; then
  log "ERROR: no panel output (SPI / Unknown* / small mode) — Qt will only use HDMI"
  xrandr --query 2>&1 | tee -a "$LOG" >&2
  exit 0
fi
log "panel output name=$SPI (UnknownN-1 is normal for mipi-dbi-spi)"

ROT=0
[[ -f /etc/esp-handset/panel-rotation ]] && \
  ROT="$(tr -d '[:space:]' </etc/esp-handset/panel-rotation 2>/dev/null || echo 0)"
MODE=240x320
case "$ROT" in 90|270) MODE=320x240 ;; esac

log "enabling panel=$SPI MODE=$MODE (HDMI stays ${HDMI:-none})"

# Turn panel ON with an explicit mode (blank SPI is often "connected" without CRTC)
ok=0
for try in "$MODE" 240x320 320x240; do
  if xrandr --output "$SPI" --mode "$try" --pos 0x0 --rotate normal 2>/dev/null; then
    MODE=$try; ok=1; log "panel mode $MODE"; break
  fi
done
if [[ "$ok" -eq 0 ]]; then
  xrandr --output "$SPI" --auto --pos 0x0 2>/dev/null && log "panel --auto"
  # Preferred mode from first listed rate line
  pref=$(xrandr --query 2>/dev/null | awk -v n="$SPI" '
    $0 ~ ("^" n " connected") {p=1;next}
    p && $1 ~ /^[0-9]+x[0-9]+/ {print $1; exit}
    p && /^[^ ]/ {exit}')
  if [[ -n "$pref" ]]; then
    xrandr --output "$SPI" --mode "$pref" --pos 0x0 2>/dev/null && MODE=$pref && log "panel preferred $MODE"
  fi
fi

# Explicit CRTC attach (some drivers leave output dark without this)
xrandr --output "$SPI" --primary --on 2>/dev/null

# HDMI extended to the RIGHT so rects are distinct (+0+0 panel, +W+0 HDMI)
if [[ -n "$HDMI" && "$HDMI" != "$SPI" ]]; then
  xrandr --output "$HDMI" --auto 2>/dev/null
  xrandr --output "$HDMI" --right-of "$SPI" 2>/dev/null \
    || xrandr --output "$HDMI" --pos "${MODE%x*}0" 2>/dev/null \
    || xrandr --output "$HDMI" --auto 2>/dev/null
  log "HDMI on extended right-of panel"
fi

# Panel primary again (some configs re-primary HDMI on --auto)
xrandr --output "$SPI" --primary --pos 0x0 --on 2>/dev/null

# Confirm panel has an active mode of form WxH+X+Y (not just "connected")
active=$(xrandr --query 2>/dev/null | awk -v n="$SPI" '
  $0 ~ ("^" n " connected") {
    if (match($0, /[0-9]+x[0-9]+\+[0-9]+\+[0-9]+/)) print substr($0, RSTART, RLENGTH)
  }')
if [[ -z "$active" ]]; then
  log "WARN: panel $SPI has no active WxH+X+Y — compositor may not scan out; SPI stays black"
  log "Full xrandr:"
  xrandr --query 2>&1 | tee -a "$LOG" >&2
else
  log "panel active geometry: $active"
fi

echo "$SPI" >/tmp/digivice-panel-output 2>/dev/null
export ESP_HANDSET_PANEL_OUTPUT="$SPI"
export ESP_HANDSET_TARGET=panel
W="${MODE%x*}"; H="${MODE#*x}"
export ESP_HANDSET_W="$W" ESP_HANDSET_H="$H"

log "final layout:"
xrandr --query 2>/dev/null | grep -E 'Screen | connected' | tee -a "$LOG" >&2
log "hosts paint full Digivice onto both $SPI and ${HDMI:-n/a}"
exit 0
