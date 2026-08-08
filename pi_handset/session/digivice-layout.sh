#!/usr/bin/env bash
# Digivice layout: SPI is the only desktop geometry for Digivice.
#
# Crop bug cause: big HDMI primary + small SPI viewport into same desktop.
# Fix: while Digivice runs, X "world size" = phone resolution on SPI only.
# Optional: after that, HDMI is reattached as scaled CLONE of SPI (same picture).
#
#   digivice-layout              # SPI-only canvas + try HDMI mirror
#   ESP_HANDSET_MIRROR=0 digivice-layout   # SPI only, HDMI off
#
set +e
set -u

log() { echo "[digivice-layout] $*" | tee -a "${HOME}/.esp-handset/handset.log" >&2; }

mkdir -p "${HOME}/.esp-handset" 2>/dev/null

MIRROR="${ESP_HANDSET_MIRROR:-1}"
ROT="0"
[[ -f /etc/esp-handset/panel-rotation ]] && \
  ROT="$(tr -d '[:space:]' </etc/esp-handset/panel-rotation 2>/dev/null || echo 0)"
W=240; H=320
case "$ROT" in 90|270) W=320; H=240 ;; esac
MODE="${W}x${H}"

export DISPLAY="${DISPLAY:-:0}"

if ! command -v xrandr >/dev/null 2>&1; then
  log "xrandr missing — install x11-xserver-utils; use X11 not pure Wayland"
  exit 0
fi
if ! xrandr --query >/dev/null 2>&1; then
  log "cannot query X (DISPLAY=$DISPLAY). Start from desktop session."
  exit 0
fi

mapfile -t OUTS < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
log "connected: ${OUTS[*]:-none}"

SPI=""
HDMI=""
for o in "${OUTS[@]:-}"; do
  case "$o" in
    *SPI*|*DPI*|*DSI*|*PANEL*) SPI="$o" ;;
    HDMI*|hdmi*) HDMI="$o" ;;
  esac
done

if [[ -z "$SPI" ]]; then
  best=999999999
  for o in "${OUTS[@]:-}"; do
    case "$o" in HDMI*|hdmi*) continue ;; esac
    # current mode area from line with *
    area=$(xrandr --query 2>/dev/null | awk -v n="$o" '
      $0 ~ ("^" n " connected") { p=1; next }
      p && $1 ~ /^[0-9]+x[0-9]+/ {
        split($1,a,"x"); print (a[1]+0)*(a[2]+0); exit
      }
      p && NF==0 { p=0 }
    ')
    area="${area:-0}"
    if [[ "$area" -gt 1000 && "$area" -lt 500000 && "$area" -lt "$best" ]]; then
      best=$area; SPI=$o
    fi
  done
fi

if [[ -z "$SPI" ]]; then
  log "ERROR: no SPI/small panel in xrandr — Digivice will crop if only HDMI exists"
  log "Full xrandr:"; xrandr --query 2>&1 | tee -a "${HOME}/.esp-handset/handset.log" >&2
  exit 0
fi

log "SPI=$SPI HDMI=${HDMI:-none} MODE=$MODE MIRROR=$MIRROR"

# --- Phase 1: tear down extended desktop (crop root cause) ---
if [[ -n "$HDMI" ]]; then
  xrandr --output "$HDMI" --off 2>/dev/null
  log "HDMI off temporarily"
  sleep 0.25
fi

# --- Phase 2: entire X framebuffer = phone size on SPI ---
ok=0
for try in "$MODE" 240x320 320x240; do
  if xrandr --output "$SPI" --mode "$try" --primary --pos 0x0 2>/dev/null; then
    MODE=$try
    W="${MODE%x*}"; H="${MODE#*x}"
    ok=1
    log "SPI mode $MODE primary"
    break
  fi
done
if [[ "$ok" -eq 0 ]]; then
  xrandr --output "$SPI" --auto --primary --pos 0x0 2>/dev/null
  log "SPI --auto (mode strings failed — check preferred mode below)"
  xrandr --query 2>/dev/null | awk -v n="$SPI" '
    $0 ~ ("^" n " ") {print; p=1; next}
    p && /^[^ ]/ {exit}
    p {print}
  ' | head -20 | tee -a "${HOME}/.esp-handset/handset.log" >&2
fi

# Force virtual screen size to phone (kills leftover 1920x1080 workspace)
if xrandr --fb "${MODE}" 2>/dev/null; then
  log "xrandr --fb $MODE OK"
else
  log "xrandr --fb $MODE failed (non-fatal)"
fi

# SPI only again after --fb
xrandr --output "$SPI" --primary --pos 0x0 2>/dev/null

# --- Phase 3: HDMI as CLONE of SPI (optional) ---
if [[ -n "$HDMI" && "$MIRROR" != "0" ]]; then
  sleep 0.2
  if xrandr --output "$HDMI" --auto --scale-from "$MODE" --same-as "$SPI" 2>/dev/null; then
    log "HDMI = scale-from $MODE same-as SPI (big mirror)"
  elif xrandr --output "$HDMI" --same-as "$SPI" 2>/dev/null; then
    log "HDMI = same-as SPI"
  else
    # Leave HDMI off — SPI has full uncropped Digivice world
    log "HDMI clone failed — left OFF so SPI stays full canvas (no crop)"
    log "Desk tip: VNC into Pi or use SPI; clone needs X11 + working scale-from"
  fi
fi

# Show final layout
xrandr --query 2>/dev/null | grep -E 'connected|Screen ' | tee -a "${HOME}/.esp-handset/handset.log" >&2

echo "$SPI" >/tmp/digivice-panel-output 2>/dev/null
export ESP_HANDSET_PANEL_OUTPUT="$SPI"
export ESP_HANDSET_W="$W"
export ESP_HANDSET_H="$H"
export ESP_HANDSET_TARGET=panel
log "canvas=${W}x${H} panel=$SPI  (Digivice must fill this; no 1080p primary)"
exit 0
