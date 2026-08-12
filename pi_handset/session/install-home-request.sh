#!/usr/bin/env bash
# Disable the old Home-button systemd path unit (it double-launched Digivice
# and helped crash Pi Zero). Home now just runs:  sudo -u USER handset-phone &
set +e
set -u

if [[ "$(id -u)" -ne 0 ]]; then
  exec sudo bash "$0" "$@"
fi

systemctl stop digivice-home-request.path 2>/dev/null || true
systemctl disable digivice-home-request.path 2>/dev/null || true
systemctl stop digivice-home-request.service 2>/dev/null || true
systemctl disable digivice-home-request.service 2>/dev/null || true
rm -f /run/digivice-home-request 2>/dev/null || true
systemctl daemon-reload 2>/dev/null || true

echo "[install-home-request] disabled (Home uses plain handset-phone now)"
