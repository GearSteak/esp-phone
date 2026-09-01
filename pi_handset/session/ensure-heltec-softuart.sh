#!/usr/bin/env bash
# Ensure Heltec soft-UART — pigpio + ESP_BRIDGE env. Safe every update.
#
#   sudo digivice-ensure-heltec
#   sudo digivice-ensure-heltec --doctor
#   sudo digivice-ensure-heltec --restart   # also restart Digivice (Settings update path)
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
DOCTOR=0
RESTART=0
for a in "$@"; do
  [[ "$a" == "--doctor" || "$a" == "doctor" ]] && DOCTOR=1
  [[ "$a" == "--restart" || "$a" == "restart" ]] && RESTART=1
done

if [[ "$(id -u)" -ne 0 ]]; then
  if sudo -n true 2>/dev/null; then
    exec sudo -n env ESP_HANDSET_PREFIX="$PREFIX" bash "$0" "$@"
  fi
  echo "[ensure-heltec] need root (or passwordless sudo)" >&2
  exit 1
fi

GUI_USER="${SUDO_USER:-}"
if [[ -z "$GUI_USER" || "$GUI_USER" == "root" ]]; then
  GUI_USER="$(logname 2>/dev/null || true)"
fi
if [[ -z "$GUI_USER" || "$GUI_USER" == "root" ]]; then
  for u in gearsteak pi isaac; do
    if id "$u" >/dev/null 2>&1; then GUI_USER="$u"; break; fi
  done
fi
GUI_HOME="$(getent passwd "${GUI_USER:-pi}" 2>/dev/null | cut -d: -f6 || echo "/home/pi")"

run_softuart() {
  for script in \
    "$PREFIX/session/digivice-heltec-softuart.sh" \
    "$(dirname "$0")/digivice-heltec-softuart.sh" \
    /usr/local/bin/digivice-heltec-softuart
  do
    if [[ -f "$script" ]]; then
      bash "$script"
      return $?
    fi
  done
  echo "[ensure-heltec] digivice-heltec-softuart.sh missing" >&2
  return 1
}

run_doctor() {
  local -a env_args=()
  if [[ "$RESTART" -ne 1 ]]; then
    env_args=(env DIGIVICE_ENSURE_HELTEC_NO_RESTART=1)
  fi
  for script in \
    "$PREFIX/session/digivice-heltec-doctor.sh" \
    "$(dirname "$0")/digivice-heltec-doctor.sh" \
    /usr/local/bin/digivice-heltec-doctor
  do
    if [[ -f "$script" ]]; then
      "${env_args[@]}" bash "$script"
      return $?
    fi
  done
  echo "[ensure-heltec] digivice-heltec-doctor.sh missing" >&2
  return 1
}

restart_digivice() {
  if [[ "${DIGIVICE_ENSURE_HELTEC_NO_RESTART:-0}" == "1" ]]; then
    return 0
  fi
  if ! python3 -c "import pigpio; pi=pigpio.pi(); ok=pi.connected; pi.stop(); import sys; sys.exit(0 if ok else 1)" 2>/dev/null; then
    echo "[ensure-heltec] skip restart — pigpiod not connected"
    return 1
  fi
  echo "[ensure-heltec] restarting Digivice (Heltec bridge)…"
  for start in /usr/local/bin/digivice-start "$PREFIX/session/digivice-start.sh"; do
    if [[ -x "$start" ]]; then
      sudo -u "${GUI_USER:-pi}" -H env \
        HOME="$GUI_HOME" \
        DISPLAY="${DISPLAY:-:0}" \
        XAUTHORITY="${XAUTHORITY:-$GUI_HOME/.Xauthority}" \
        "$start" 2>&1 | tail -n 12
      return 0
    fi
  done
  echo "[ensure-heltec] digivice-start not found"
  return 1
}

echo "[ensure-heltec] soft-UART (pigpio + env)…"
run_softuart
rc=$?

if [[ "$DOCTOR" -eq 1 ]]; then
  run_doctor
fi

if [[ "$RESTART" -eq 1 ]]; then
  restart_digivice || true
fi

exit "$rc"
