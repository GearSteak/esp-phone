#!/usr/bin/env bash
# Install Digivice in-app browser deps.
# Qt WebEngine is often missing on Raspberry Pi OS ARM; Qt WebKit usually works.
#
#   sudo digivice-ensure-browser
#   sudo digivice-ensure-browser --doctor
#
set +e
set -u
DOCTOR=0
for a in "$@"; do
  [[ "$a" == "--doctor" || "$a" == "doctor" ]] && DOCTOR=1
done

if [[ "$(id -u)" -ne 0 ]]; then
  if sudo -n true 2>/dev/null; then
    exec sudo -n bash "$0" "$@"
  fi
  echo "[ensure-browser] need root" >&2
  exit 1
fi

log() { echo "[ensure-browser] $*"; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null 2>&1 || true

# Prefer WebKit on Pi (actually packaged); try WebEngine too when present.
log "apt: python3-pyqt5.qtwebkit…"
apt-get install -y python3-pyqt5.qtwebkit 2>&1 | tail -n 8
log "apt: python3-pyqt5.qtwebengine (may be unavailable on Pi OS)…"
apt-get install -y python3-pyqt5.qtwebengine 2>&1 | tail -n 8 || true

# Extra libs some WebEngine builds need
apt-get install -y libqt5webenginecore5 libqt5webenginewidgets5 2>/dev/null | tail -n 3 || true

check_py() {
  python3 - <<'PY'
import sys
ok = False
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    print("OK QtWebEngine")
    ok = True
except Exception as e:
    print("NO QtWebEngine:", e)
try:
    from PyQt5.QtWebKitWidgets import QWebView
    print("OK QtWebKit")
    ok = True
except Exception as e:
    print("NO QtWebKit:", e)
sys.exit(0 if ok else 1)
PY
}

if check_py; then
  log "browser backend ready"
  [[ "$DOCTOR" -eq 1 ]] && check_py
  exit 0
fi

log "FAIL: neither WebEngine nor WebKit imported"
[[ "$DOCTOR" -eq 1 ]] && check_py
exit 1
