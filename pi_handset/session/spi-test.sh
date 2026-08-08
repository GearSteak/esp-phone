#!/usr/bin/env bash
# Flash the SPI panel solid red for 3s (proves CRTC + backlight + SPI scanout).
#   digivice-spi-test
set +e
export DISPLAY="${DISPLAY:-:0}"
LOG="${HOME}/.esp-handset/handset.log"
mkdir -p "${HOME}/.esp-handset"
log() { echo "[spi-test] $*" | tee -a "$LOG" >&2; }

if ! command -v xrandr >/dev/null 2>&1; then
  log "need xrandr / X11"
  exit 1
fi

bash /usr/local/bin/digivice-layout 2>/dev/null \
  || bash "$(dirname "$0")/digivice-layout.sh" 2>/dev/null

SPI=$(cat /tmp/digivice-panel-output 2>/dev/null || true)
if [[ -z "$SPI" ]]; then
  SPI=$(xrandr --query | awk '/ connected/ && /Unknown|SPI|DPI|DSI|PANEL/{print $1; exit}')
fi
if [[ -z "$SPI" ]]; then
  log "No SPI/Unknown output. Kernel?"
  xrandr --query | tee -a "$LOG"
  log "Try: dmesg | grep -i mipi"
  exit 1
fi

geo=$(xrandr --query | awk -v n="$SPI" '
  $0 ~ ("^" n " connected") {
    if (match($0, /[0-9]+x[0-9]+\+[0-9]+\+[0-9]+/))
      print substr($0, RSTART, RLENGTH)
  }')
log "panel=$SPI geo=${geo:-(not active)}"
if [[ -z "$geo" ]]; then
  log "panel connected but no active mode"
  exit 1
fi

# WxH+X+Y
W=${geo%%x*}; rest=${geo#*x}; H=${rest%%+*}; rest=${rest#*+}; X=${rest%%+*}; Y=${rest#*+}
log "flashing red on ${W}x${H}+${X}+${Y}"

python3 - <<PY
import sys
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import QTimer, Qt

app = QApplication(sys.argv)
w = QWidget()
w.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
w.setStyleSheet("background-color: #ff0000;")
w.setGeometry(int("$X"), int("$Y"), int("$W"), int("$H"))
w.show()
print("[spi-test] red window up — look at 2-inch panel for 4s", flush=True)
QTimer.singleShot(4000, app.quit)
app.exec_()
print("[spi-test] done")
PY

log "If panel stayed black during red flash: wiring/backlight/driver (not Digivice UI)."
log "If red showed: Digivice must pin to $SPI — pull latest display_geom + handset-phone."
