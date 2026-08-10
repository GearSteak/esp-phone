#!/usr/bin/env bash
# Ensure Digivice hard-button daemon is installed, enabled, and running on boot.
# Idempotent — safe to call from install, update, or handset-session.
#
#   sudo digivice-ensure-buttons
#
set +e
set -u
PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
SCRIPT="$PREFIX/buttons_inputd.py"
UNIT=/etc/systemd/system/digi-buttons-inputd.service

if [[ "$(id -u)" -ne 0 ]]; then
  if sudo -n true 2>/dev/null; then
    exec sudo -n env ESP_HANDSET_PREFIX="$PREFIX" bash "$0" "$@"
  fi
  echo "[ensure-buttons] need root (or passwordless sudo)" >&2
  exit 1
fi

if [[ ! -f "$SCRIPT" ]]; then
  # Dev tree / session script sibling
  alt="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)/esp_handset/buttons_inputd.py"
  if [[ -f "$alt" ]]; then
    mkdir -p "$PREFIX"
    install -m 755 "$alt" "$SCRIPT"
  fi
fi

if [[ ! -f "$SCRIPT" ]]; then
  echo "[ensure-buttons] missing $SCRIPT" >&2
  exit 1
fi

cat >"$UNIT" <<EOF
[Unit]
Description=Digivice hard buttons (D-pad + Confirm/Back/Home)
After=multi-user.target
Wants=multi-user.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 $SCRIPT
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable digi-buttons-inputd.service
systemctl restart digi-buttons-inputd.service
if systemctl is-active --quiet digi-buttons-inputd.service; then
  echo "[ensure-buttons] digi-buttons-inputd active (enabled on boot)"
  exit 0
fi
echo "[ensure-buttons] failed to start — check: journalctl -u digi-buttons-inputd -n 40" >&2
systemctl status digi-buttons-inputd.service --no-pager || true
exit 1
