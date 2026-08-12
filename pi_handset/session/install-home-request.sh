#!/usr/bin/env bash
# Install systemd path/unit so Home button never spawns Digivice from the
# GPIO daemon process tree (that crashed Pi Zero 2 W).
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
SCRIPT=/usr/local/bin/digivice-home-relaunch

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Re-run as root: sudo $0"
  exec sudo env ESP_HANDSET_PREFIX="$PREFIX" bash "$0" "$@"
fi

if [[ -f "$PREFIX/session/home-relaunch.sh" ]]; then
  install -m 755 "$PREFIX/session/home-relaunch.sh" "$SCRIPT"
elif [[ -f "$(dirname "$0")/home-relaunch.sh" ]]; then
  install -m 755 "$(dirname "$0")/home-relaunch.sh" "$SCRIPT"
fi

cat >/etc/systemd/system/digivice-home-request.service <<EOF
[Unit]
Description=Digivice Home button → launch phone UI (isolated)
After=display-manager.service multi-user.target

[Service]
Type=oneshot
ExecStart=$SCRIPT
TimeoutStartSec=180
Nice=5

[Install]
WantedBy=multi-user.target
EOF

# PathExists: each Home press creates/writes the file; service deletes it.
cat >/etc/systemd/system/digivice-home-request.path <<'EOF'
[Unit]
Description=Watch Digivice Home button request file

[Path]
PathExists=/run/digivice-home-request
Unit=digivice-home-request.service

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable digivice-home-request.path
systemctl restart digivice-home-request.path
# Do not leave a stale request sitting around
rm -f /run/digivice-home-request 2>/dev/null || true

echo "[install-home-request] path unit active=$(systemctl is-active digivice-home-request.path 2>/dev/null)"
echo "  Home button writes /run/digivice-home-request → isolated Digivice launch"
