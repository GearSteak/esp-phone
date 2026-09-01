#!/usr/bin/env bash
# Ensure Heltec soft-UART — pigpio + ESP_BRIDGE env. Safe every update.
#
#   sudo digivice-ensure-heltec
#   sudo digivice-ensure-heltec --doctor
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
DOCTOR=0
for a in "$@"; do
  [[ "$a" == "--doctor" || "$a" == "doctor" ]] && DOCTOR=1
done

if [[ "$(id -u)" -ne 0 ]]; then
  if sudo -n true 2>/dev/null; then
    exec sudo -n env ESP_HANDSET_PREFIX="$PREFIX" bash "$0" "$@"
  fi
  echo "[ensure-heltec] need root (or passwordless sudo)" >&2
  exit 1
fi

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
  for script in \
    "$PREFIX/session/digivice-heltec-doctor.sh" \
    "$(dirname "$0")/digivice-heltec-doctor.sh" \
    /usr/local/bin/digivice-heltec-doctor
  do
    if [[ -f "$script" ]]; then
      bash "$script"
      return $?
    fi
  done
  echo "[ensure-heltec] digivice-heltec-doctor.sh missing" >&2
  return 1
}

echo "[ensure-heltec] soft-UART (pigpio + env)…"
run_softuart
rc=$?

if [[ "$DOCTOR" -eq 1 ]]; then
  run_doctor
fi

exit "$rc"
