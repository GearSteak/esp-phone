#!/usr/bin/env bash
# Flash SPI red WITHOUT rearranging HDMI (safe diagnostic).
#
#   digivice-spi-test           # red on SPI if already active; no xrandr --mode juggling
#   digivice-spi-test --enable  # lightly enable SPI then always re-assert HDMI
#
set +e
set -u
export DISPLAY="${DISPLAY:-:0}"
LOG="${HOME}/.esp-handset/handset.log"
mkdir -p "${HOME}/.esp-handset"
log() { echo "[spi-test] $*" | tee -a "$LOG" >&2; }

ENABLE=0
[[ "${1:-}" == "--enable" ]] && ENABLE=1

if ! command -v xrandr >/dev/null 2>&1 || ! xrandr --query >/dev/null 2>&1; then
  log "xrandr not available DISPLAY=$DISPLAY — abort (HDMI untouched)"
  exit 1
fi

find_spi() {
  local o area
  # preferred: /tmp file
  if [[ -f /tmp/digivice-panel-output ]]; then
    o=$(tr -d '[:space:]' </tmp/digivice-panel-output)
    if xrandr --query 2>/dev/null | grep -qE "^${o} connected"; then
      echo "$o"; return
    fi
  fi
  while read -r o; do
    case "$o" in
      *SPI*|*DPI*|*DSI*|*PANEL*|[Uu]nknown*) echo "$o"; return ;;
    esac
  done < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
  # smallest non-HDMI active head
  local best=999999999 pick=""
  while read -r o; do
    case "$o" in HDMI*|hdmi*|DP-*) continue ;; esac
    area=$(xrandr --query 2>/dev/null | awk -v n="$o" '
      $0 ~ ("^" n " connected") {
        if (match($0, /([0-9]+)x([0-9]+)/, a)) { print (a[1]+0)*(a[2]+0); exit }
      }')
    area="${area:-0}"
    if [[ "$area" -gt 1000 && "$area" -lt 500000 && "$area" -lt "$best" ]]; then
      best=$area; pick=$o
    fi
  done < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
  [[ -n "$pick" ]] && echo "$pick"
}

reassert_hdmi() {
  # CRITICAL: never leave HDMI dark after any SPI experiment
  local o
  while read -r o; do
    case "$o" in
      HDMI*|hdmi*)
        xrandr --output "$o" --auto --on 2>/dev/null
        xrandr --output "$o" --primary 2>/dev/null
        log "HDMI re-asserted: $o (you should still see this monitor)"
        return 0
        ;;
    esac
  done < <(xrandr --query 2>/dev/null | awk '/ connected/{print $1}')
  log "WARN: no HDMI name; ran xrandr --auto only"
  xrandr --auto 2>/dev/null
}

active_geo() {
  local n="$1"
  xrandr --query 2>/dev/null | awk -v n="$n" '
    $0 ~ ("^" n " connected") {
      if (match($0, /[0-9]+x[0-9]+\+[0-9]+\+[0-9]+/))
        print substr($0, RSTART, RLENGTH)
    }'
}

log "=== SPI red test (HDMI-safe) ==="
log "current heads:"
xrandr --query 2>/dev/null | grep -E 'Screen | connected' | tee -a "$LOG" >&2

SPI=$(find_spi || true)
log "detected panel: ${SPI:-NONE}"

if [[ -z "$SPI" ]]; then
  log "No SPI/Unknown in xrandr. Not changing layout."
  log "  Panel may be disconnect at DRM (overlay). HDMI left alone."
  log "  Check: dmesg | grep -iE 'mipi|panel|spi'"
  exit 2
fi

GEO=$(active_geo "$SPI")
if [[ -z "$GEO" && "$ENABLE" -eq 1 ]]; then
  log "--enable: try native phone modes on $SPI (then re-assert HDMI)"
  for try in 240x320 320x240; do
    xrandr --output "$SPI" --mode "$try" --on 2>/dev/null && break
  done
  xrandr --output "$SPI" --auto --on 2>/dev/null
  reassert_hdmi
  GEO=$(active_geo "$SPI")
elif [[ -z "$GEO" ]]; then
  log "$SPI connected but has no active WxH+X+Y"
  log "  Run: digivice-spi-test --enable   (still re-asserts HDMI after)"
  reassert_hdmi
  exit 3
fi

if [[ -z "$GEO" ]]; then
  log "still no active geometry on $SPI after enable"
  reassert_hdmi
  exit 3
fi

W=${GEO%%x*}; rest=${GEO#*x}; H=${rest%%+*}; rest=${rest#*+}; X=${rest%%+*}; Y=${rest#*+}
log "opening red ${W}x${H} at +${X}+${Y} on $SPI (HDMI untouched except re-assert)"
reassert_hdmi

# Unblank backlight only (no layout)
for d in /sys/class/backlight/*; do
  [[ -d "$d" ]] || continue
  echo 0 >"$d/bl_power" 2>/dev/null || true
  [[ -r "$d/max_brightness" ]] && cat "$d/max_brightness" >"$d/brightness" 2>/dev/null || true
done

python3 - <<PY
import sys
from PyQt5.QtWidgets import QApplication, QWidget, QLabel
from PyQt5.QtCore import QTimer, Qt

app = QApplication(sys.argv)
w = QWidget()
w.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
w.setStyleSheet("background-color: #ff0000;")
w.setGeometry(int("$X"), int("$Y"), int("$W"), int("$H"))
lab = QLabel("SPI", w)
lab.setStyleSheet("color: white; font-size: 28px; font-weight: bold;")
lab.setAlignment(Qt.AlignCenter)
lab.setGeometry(0, 0, int("$W"), int("$H"))
w.show()
w.raise_()
print("[spi-test] RED on SPI for 5s — HDMI should stay as it was", flush=True)
QTimer.singleShot(5000, app.quit)
app.exec_()
print("[spi-test] closed red window", flush=True)
PY

reassert_hdmi
log "done. HDMI re-asserted again."
log "  RED on 2\"  → panel CRTC ok; Digivice pin needed (pull latest)"
log "  BLACK on 2\" → panel not scanning (driver/mode), HDMI should still work"
exit 0
