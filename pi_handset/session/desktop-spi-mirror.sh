#!/usr/bin/env bash
# Start/stop desktop → ST7789 SPI mirror (when Digivice is not running).
#
#   digivice-desktop-mirror start|stop|status|run
#
set +e
set -u
PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
LOG="${HOME}/.esp-handset/handset.log"
PIDF="${HOME}/.esp-handset/desktop-spi-mirror.pid"
mkdir -p "${HOME}/.esp-handset"
export DISPLAY="${DISPLAY:-:0}"
export ESP_HANDSET_SPI_BACKEND=userspace

log() { echo "[desktop-mirror] $*" | tee -a "$LOG" >&2; }

app_py() {
  if [[ -f "$PREFIX/esp_handset/desktop_spi_mirror.py" ]]; then
    echo "$PREFIX/esp_handset/desktop_spi_mirror.py"
    return
  fi
  if [[ -f "$PREFIX/desktop_spi_mirror.py" ]]; then
    echo "$PREFIX/desktop_spi_mirror.py"
    return
  fi
  local r
  r="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)/esp_handset/desktop_spi_mirror.py"
  [[ -f "$r" ]] && echo "$r" && return
  echo ""
}

stop_mirror() {
  if [[ -f "$PIDF" ]]; then
    pid=$(tr -d '[:space:]' <"$PIDF" 2>/dev/null || true)
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 0.2
      kill -9 "$pid" 2>/dev/null || true
      log "stopped pid=$pid"
    fi
    rm -f "$PIDF"
  fi
  pkill -f "desktop_spi_mirror.py" 2>/dev/null || true
}

start_mirror() {
  stop_mirror
  local py
  py="$(app_py)"
  if [[ -z "$py" || ! -f "$py" ]]; then
    log "ERROR: desktop_spi_mirror.py not found"
    return 1
  fi
  # py is .../esp_handset/desktop_spi_mirror.py → package root is parent
  local root
  root="$(cd "$(dirname "$py")/.." && pwd)"
  export PYTHONPATH="$root:${PYTHONPATH:-}"
  export ESP_HANDSET_SPI_BACKEND=userspace
  nohup /usr/bin/python3 "$py" >>"$LOG" 2>&1 &
  echo $! >"$PIDF"
  log "started pid=$! ($py) — desktop → SPI"
}

status_mirror() {
  if [[ -f "$PIDF" ]]; then
    pid=$(tr -d '[:space:]' <"$PIDF")
    if kill -0 "$pid" 2>/dev/null; then
      echo "running pid=$pid"
      return 0
    fi
  fi
  if pgrep -f "desktop_spi_mirror.py" >/dev/null 2>&1; then
    echo "running (no pidfile)"
    return 0
  fi
  echo "stopped"
  return 1
}

cmd="${1:-start}"
case "$cmd" in
  start) start_mirror ;;
  stop) stop_mirror; log "stopped" ;;
  status) status_mirror ;;
  run)
    py="$(app_py)"
    [[ -z "$py" || ! -f "$py" ]] && { log "ERROR: mirror py missing"; exit 1; }
    export PYTHONPATH="$(cd "$(dirname "$py")/.." && pwd):${PYTHONPATH:-}"
    export ESP_HANDSET_SPI_BACKEND=userspace
    exec /usr/bin/python3 "$py"
    ;;
  *)
    echo "Usage: digivice-desktop-mirror start|stop|status|run"
    exit 1
    ;;
esac
