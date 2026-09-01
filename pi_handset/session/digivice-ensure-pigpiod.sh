#!/usr/bin/env bash
# Start pigpiod for Heltec soft-UART (source-built binary often misses systemd).
set +e
set -u

log() { echo "[ensure-pigpiod] $*"; }

pigpio_connected() {
  python3 -c "import pigpio; pi=pigpio.pi(); ok=pi.connected; pi.stop(); import sys; sys.exit(0 if ok else 1)" 2>/dev/null
}

find_pigpiod() {
  for bin in /usr/local/bin/pigpiod /usr/bin/pigpiod pigpiod; do
    if [[ -x "$bin" ]] || command -v "$bin" >/dev/null 2>&1; then
      command -v "$bin" 2>/dev/null || echo "$bin"
      return 0
    fi
  done
  return 1
}

install_unit() {
  local bin="$1"
  local unit="/etc/systemd/system/pigpiod.service"
  [[ -f "$unit" ]] && grep -q "$bin" "$unit" 2>/dev/null && return 0
  log "installing systemd unit → $bin"
  cat >"$unit" <<EOF
[Unit]
Description=pigpio daemon (Digivice Heltec soft-UART)
After=network.target

[Service]
Type=forking
ExecStart=$bin
ExecStop=/bin/kill -TERM \$MAINPID
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload 2>/dev/null || true
  systemctl enable pigpiod 2>/dev/null || true
}

if pigpio_connected; then
  log "already connected"
  exit 0
fi

systemctl start pigpiod 2>/dev/null || true
sleep 0.4
if pigpio_connected; then
  log "started via systemctl"
  exit 0
fi

bin="$(find_pigpiod || true)"
if [[ -z "$bin" ]]; then
  log "ERROR: pigpiod binary not found"
  exit 1
fi

if [[ "$(id -u)" -eq 0 ]]; then
  install_unit "$bin"
  systemctl start pigpiod 2>/dev/null || true
  sleep 0.4
  if pigpio_connected; then
    log "started via systemd ($bin)"
    exit 0
  fi
fi

pkill -x pigpiod 2>/dev/null || true
sleep 0.2
"$bin" 2>/dev/null &
sleep 0.5
if pigpio_connected; then
  log "started direct ($bin)"
  exit 0
fi

log "ERROR: pigpiod still not connected"
exit 1
