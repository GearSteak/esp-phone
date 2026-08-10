#!/usr/bin/env bash
# One-shot desktop SPI unfuck — run ON THE PI when small screen is blank in Linux desktop.
#
#   curl -sL ... | bash
#   or:  bash fix-desktop-spi-now.sh
#
set +e
set -u

echo "=== Digivice: force desktop → SPI mirror NOW ==="

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"

# Leave Digivice
pkill -f handset_app.py 2>/dev/null
sleep 0.5

# Mode
mkdir -p "$HOME/.esp-handset" /etc/esp-handset 2>/dev/null
echo desktop >"$HOME/.esp-handset/session_mode"
echo desktop | sudo -n tee /etc/esp-handset/ui_mode >/dev/null 2>&1 \
  || echo desktop >/etc/esp-handset/ui_mode 2>/dev/null \
  || true

# Userspace SPI flags if spidev is there
if [[ -e /dev/spidev0.0 ]]; then
  echo userspace | sudo -n tee /etc/esp-handset/spi-userspace >/dev/null 2>&1 \
    || sudo tee /etc/esp-handset/spi-userspace >/dev/null <<<"userspace" 2>/dev/null \
    || true
  echo userspace | sudo -n tee /etc/esp-handset/spi-backend >/dev/null 2>&1 || true
  sudo -n bash -c 'cat >/etc/esp-handset/env <<EOF
ESP_HANDSET_SPI_BACKEND=userspace
ESP_HANDSET_SKIP_LAYOUT=1
EOF' 2>/dev/null || true
  echo "spidev0.0: OK"
else
  echo "WARNING: /dev/spidev0.0 missing"
  echo "  sudo digivice-install-spi-userspace && sudo reboot"
fi

# Prefer installed tools; fall back to repo path
ROOT=""
for c in \
  /opt/esp-handset \
  "$HOME/esp-phone/pi_handset" \
  /home/*/esp-phone/pi_handset
do
  # shellcheck disable=SC2086
  for d in $c; do
    if [[ -f "$d/esp_handset/desktop_spi_mirror.py" ]]; then
      ROOT="$d"
      break 2
    fi
    if [[ -f "$d/desktop_spi_mirror.py" ]]; then
      ROOT="$(cd "$d/.." && pwd)"
      break 2
    fi
  done
done

if [[ -z "$ROOT" ]]; then
  echo "ERROR: desktop_spi_mirror.py not found. git clone esp-phone first."
  exit 1
fi

export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export ESP_HANDSET_SPI_BACKEND=userspace

if [[ -x /usr/local/bin/digivice-desktop-mirror ]]; then
  /usr/local/bin/digivice-desktop-mirror stop
  /usr/local/bin/digivice-desktop-mirror doctor
else
  pkill -f desktop_spi_mirror.py 2>/dev/null
  sleep 0.3
  nohup python3 "$ROOT/esp_handset/desktop_spi_mirror.py" \
    >>"$HOME/.esp-handset/handset.log" 2>&1 &
  echo $! >"$HOME/.esp-handset/desktop-spi-mirror.pid"
  sleep 1.5
  if kill -0 $! 2>/dev/null; then
    echo "started python mirror pid=$!"
  else
    echo "mirror died — log:"
    tail -n 30 "$HOME/.esp-handset/handset.log"
    exit 1
  fi
fi

echo ""
echo "If 2\" is still wrong:  tail -40 ~/.esp-handset/handset.log"
echo "Return to Digivice:     handset-phone"
