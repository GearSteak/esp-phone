#!/usr/bin/env bash
# Prove SPI panel by forcing SPI-only (HDMI off) for a few seconds of red, then restore HDMI.
#
#   digivice-spi-prove
#
# If red shows on 2"  → dual-head CRTC was starving SPI; use SPI-only Digivice mode.
# If still black      → firmware/kernel (run digivice-spi-doctor --fix + reboot).
#
set +e
set -u
export DISPLAY="${DISPLAY:-:0}"
LOG="${HOME}/.esp-handset/handset.log"
mkdir -p "${HOME}/.esp-handset"
log() { echo "[spi-prove] $*" | tee -a "$LOG" >&2; }

log "=== SPI prove (HDMI temporarily off, red on panel, HDMI restored) ==="

# 1) SPI-only layout
if [[ -x /usr/local/bin/digivice-layout ]]; then
  ESP_HANDSET_SPI_ONLY=1 bash /usr/local/bin/digivice-layout
else
  ESP_HANDSET_SPI_ONLY=1 bash "$(dirname "$0")/digivice-layout.sh"
fi

SPI=$(cat /tmp/digivice-panel-output 2>/dev/null || true)
geo=$(xrandr --query 2>/dev/null | awk -v n="$SPI" '
  $0 ~ ("^" n " connected") {
    if (match($0, /[0-9]+x[0-9]+\+[0-9]+\+[0-9]+/))
      print substr($0, RSTART, RLENGTH)
  }')
log "SPI=$SPI geo=${geo:-(none)}"

if [[ -z "$SPI" || -z "$geo" ]]; then
  log "FAIL: no active SPI mode even with HDMI off → firmware/DT, not dual-head."
  log "  sudo digivice-spi-doctor --fix && sudo reboot"
  # still try restore HDMI
  digivice-layout --hdmi-restore 2>/dev/null || true
  bash /usr/local/bin/digivice-layout --hdmi-restore 2>/dev/null || true
  exit 1
fi

W=${geo%%x*}; rest=${geo#*x}; H=${rest%%+*}; rest=${rest#*+}; X=${rest%%+*}; Y=${rest#*+}

log "RED fullscreen on SPI for 6 seconds — LOOK AT THE 2\" PANEL"
log "(HDMI is intentionally OFF during this — normal)"

python3 - <<PY
import sys
from PyQt5.QtWidgets import QApplication, QWidget, QLabel
from PyQt5.QtCore import QTimer, Qt

app = QApplication(sys.argv)
w = QWidget()
w.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
w.setStyleSheet("background:#ff0000;")
w.setGeometry(int("$X"), int("$Y"), int("$W"), int("$H"))
lab = QLabel("SPI OK", w)
lab.setAlignment(Qt.AlignCenter)
lab.setStyleSheet("color:#fff;font-size:22px;font-weight:bold;")
lab.setGeometry(0, 0, int("$W"), int("$H"))
w.showFullScreen()
w.show()
QTimer.singleShot(6000, app.quit)
app.exec_()
print("[spi-prove] red done", flush=True)
PY

log "Restoring HDMI..."
if [[ -x /usr/local/bin/digivice-layout ]]; then
  bash /usr/local/bin/digivice-layout --hdmi-restore
else
  bash "$(dirname "$0")/digivice-layout.sh" --hdmi-restore
fi
# belt + suspenders
for o in $(xrandr --query 2>/dev/null | awk '/ connected/{print $1}'); do
  case "$o" in HDMI*|hdmi*)
    xrandr --output "$o" --auto --primary --on 2>/dev/null
    log "HDMI restored: $o"
    ;;
  esac
done

log "Done."
log "  RED on 2\"  → run Digivice SPI-only:  ESP_HANDSET_SPI_ONLY=1 handset-phone"
log "  BLACK 2\"   → sudo digivice-spi-doctor --fix && sudo reboot"
exit 0
