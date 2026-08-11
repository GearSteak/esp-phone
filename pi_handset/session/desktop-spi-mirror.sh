#!/usr/bin/env bash
# Start/stop desktop → ST7789 SPI mirror (when Digivice is not running).
#
#   digivice-desktop-mirror start|stop|status|run|doctor
#
set +e
set -u
PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
# Prefer GUI user home even if invoked via sudo
if [[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  GUI_HOME="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
  export HOME="${GUI_HOME:-$HOME}"
  export USER="$SUDO_USER"
fi
LOG="${HOME}/.esp-handset/handset.log"
PIDF="${HOME}/.esp-handset/desktop-spi-mirror.pid"
mkdir -p "${HOME}/.esp-handset"
export DISPLAY="${DISPLAY:-:0}"
export ESP_HANDSET_SPI_BACKEND=userspace
if [[ -z "${XAUTHORITY:-}" ]]; then
  for xa in "${HOME}/.Xauthority" /home/pi/.Xauthority; do
    [[ -f "$xa" ]] && export XAUTHORITY="$xa" && break
  done
fi

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
  # live git checkout under home
  for r in \
    "${HOME}/esp-phone/pi_handset/esp_handset/desktop_spi_mirror.py" \
    /home/*/esp-phone/pi_handset/esp_handset/desktop_spi_mirror.py
  do
    # shellcheck disable=SC2086
    for f in $r; do
      [[ -f "$f" ]] && echo "$f" && return
    done
  done
  echo ""
}

ensure_userspace_flags() {
  # Seed flags so handset-session does not skip the mirror
  mkdir -p /etc/esp-handset 2>/dev/null || true
  if [[ -e /dev/spidev0.0 || -e /dev/spidev0.1 ]]; then
    if [[ ! -f /etc/esp-handset/spi-userspace ]]; then
      if [[ "$(id -u)" -eq 0 ]]; then
        echo userspace >/etc/esp-handset/spi-userspace
        echo userspace >/etc/esp-handset/spi-backend
        if [[ ! -f /etc/esp-handset/env ]]; then
          cat >/etc/esp-handset/env <<'EOF'
ESP_HANDSET_SPI_BACKEND=userspace
ESP_HANDSET_SKIP_LAYOUT=1
EOF
        fi
        log "seeded /etc/esp-handset/spi-userspace (spidev present)"
      else
        echo userspace | sudo -n tee /etc/esp-handset/spi-userspace >/dev/null 2>&1 || true
        echo userspace | sudo -n tee /etc/esp-handset/spi-backend >/dev/null 2>&1 || true
      fi
    fi
  fi
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
  sleep 0.15
}

start_mirror() {
  ensure_userspace_flags
  # Free SPI from Digivice — only when *intentionally* starting desktop mirror
  pkill -f "handset_app.py" 2>/dev/null || true
  sleep 0.4
  stop_mirror
  # Drop exclusive SPI lock files left by crashed paint/update tests
  rm -f /tmp/digivice-st7789.lock /run/digivice-st7789.lock \
    "${HOME}/.esp-handset/st7789.lock" 2>/dev/null || true

  local py root
  py="$(app_py)"
  if [[ -z "$py" || ! -f "$py" ]]; then
    log "ERROR: desktop_spi_mirror.py not found under $PREFIX or git tree"
    return 1
  fi
  if [[ ! -e /dev/spidev0.0 && ! -e /dev/spidev0.1 ]]; then
    log "ERROR: no /dev/spidev0.0 — userspace SPI not active"
    log "  fix: sudo digivice-install-spi-userspace && sudo reboot"
    return 1
  fi

  root="$(cd "$(dirname "$py")/.." && pwd)"
  export PYTHONPATH="$root:${PYTHONPATH:-}"
  export ESP_HANDSET_SPI_BACKEND=userspace
  export DISPLAY="${DISPLAY:-:0}"
  export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
  if [[ -z "${XAUTHORITY:-}" ]]; then
    for xa in "${HOME}/.Xauthority" /home/*/.Xauthority; do
      [[ -f "$xa" ]] && export XAUTHORITY="$xa" && break
    done
  fi

  log "starting $py DISPLAY=$DISPLAY XAUTHORITY=${XAUTHORITY:-none} HOME=$HOME"
  # Run as real GUI user if we are root
  if [[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    local u="$SUDO_USER"
    local h
    h="$(getent passwd "$u" | cut -d: -f6)"
    sudo -u "$u" env \
      HOME="$h" \
      DISPLAY="${DISPLAY:-:0}" \
      XAUTHORITY="${XAUTHORITY:-$h/.Xauthority}" \
      PYTHONPATH="$PYTHONPATH" \
      ESP_HANDSET_SPI_BACKEND=userspace \
      QT_QPA_PLATFORM=xcb \
      ESP_MIRROR_INIT_RETRIES=12 \
      nohup /usr/bin/python3 "$py" >>"$h/.esp-handset/handset.log" 2>&1 &
    echo $! >"$PIDF"
    chown "$u:$u" "$PIDF" 2>/dev/null || true
  else
    nohup /usr/bin/python3 "$py" >>"$LOG" 2>&1 &
    echo $! >"$PIDF"
  fi
  local pid
  pid=$(tr -d '[:space:]' <"$PIDF" 2>/dev/null)
  log "spawned pid=${pid:-?} ($py)"

  # Confirm it stays up (SPI open can fail and exit)
  sleep 1.2
  if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
    log "RUNNING pid=$pid — desktop should paint on 2\" panel"
    return 0
  fi
  log "ERROR: mirror exited immediately — last log lines:"
  tail -n 25 "$LOG" 2>/dev/null | tee -a "$LOG" >&2 || true
  # Try one more time without nohup buffering quirks
  sleep 0.5
  rm -f /tmp/digivice-st7789.lock /run/digivice-st7789.lock 2>/dev/null || true
  if [[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    local u="$SUDO_USER" h
    h="$(getent passwd "$u" | cut -d: -f6)"
    sudo -u "$u" env HOME="$h" DISPLAY=:0 XAUTHORITY="$h/.Xauthority" \
      PYTHONPATH="$PYTHONPATH" ESP_HANDSET_SPI_BACKEND=userspace \
      ESP_MIRROR_INIT_RETRIES=12 \
      /usr/bin/python3 "$py" >>"$h/.esp-handset/handset.log" 2>&1 &
    echo $! >"$PIDF"
  else
    /usr/bin/python3 "$py" >>"$LOG" 2>&1 &
    echo $! >"$PIDF"
  fi
  sleep 1.5
  pid=$(tr -d '[:space:]' <"$PIDF" 2>/dev/null)
  if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
    log "RUNNING after retry pid=$pid"
    return 0
  fi
  log "FAILED — run: digivice-desktop-mirror doctor"
  return 1
}

status_mirror() {
  if [[ -f "$PIDF" ]]; then
    pid=$(tr -d '[:space:]' <"$PIDF")
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "running pid=$pid"
      return 0
    fi
  fi
  if pgrep -af "desktop_spi_mirror.py" >/dev/null 2>&1; then
    echo "running (no pidfile)"
    pgrep -af "desktop_spi_mirror.py" || true
    return 0
  fi
  echo "stopped"
  return 1
}

doctor() {
  echo "=== digivice-desktop-mirror doctor ==="
  echo "USER=$USER HOME=$HOME DISPLAY=${DISPLAY:-} XAUTHORITY=${XAUTHORITY:-}"
  echo "spidev: $(ls -l /dev/spidev* 2>&1)"
  echo "flag spi-userspace: $(cat /etc/esp-handset/spi-userspace 2>/dev/null || echo MISSING)"
  echo "flag env: $(cat /etc/esp-handset/env 2>/dev/null | head -5 || echo MISSING)"
  echo "py: $(app_py)"
  echo "python3: $(command -v python3)"
  python3 -c "import spidev; print('spidev OK')" 2>&1 || echo "spidev IMPORT FAIL"
  python3 -c "from PyQt5.QtWidgets import QApplication; print('PyQt5 OK')" 2>&1 || echo "PyQt5 FAIL"
  echo "handset_app: $(pgrep -af handset_app.py || echo none)"
  echo "mirror: $(pgrep -af desktop_spi_mirror.py || echo none)"
  echo "mode: $(cat "${HOME}/.esp-handset/session_mode" 2>/dev/null || echo '?')"
  echo "--- last log ---"
  tail -n 40 "$LOG" 2>/dev/null || echo "(no log $LOG)"
  echo "=== try start ==="
  start_mirror
  status_mirror
}

cmd="${1:-start}"
case "$cmd" in
  start) start_mirror ;;
  stop) stop_mirror; log "stopped" ;;
  status) status_mirror ;;
  doctor) doctor ;;
  run)
    ensure_userspace_flags
    py="$(app_py)"
    [[ -z "$py" || ! -f "$py" ]] && { log "ERROR: mirror py missing"; exit 1; }
    export PYTHONPATH="$(cd "$(dirname "$py")/.." && pwd):${PYTHONPATH:-}"
    export ESP_HANDSET_SPI_BACKEND=userspace
    exec /usr/bin/python3 "$py"
    ;;
  *)
    echo "Usage: digivice-desktop-mirror start|stop|status|run|doctor"
    exit 1
    ;;
esac
