#!/usr/bin/env bash
# Digivice I2C / MCP23017 / CardKB diagnostics.
#   digivice-i2c-doctor
# Writes: ~/.esp-handset/i2c-doctor.txt (+ /tmp/digivice-i2c-doctor.txt)

set +e
set -u

USER_HOME="${HOME:-/tmp}"
USER_NAME="$(id -un 2>/dev/null || echo '?')"
if [[ "$(id -u 2>/dev/null)" -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  CANDIDATE_HOME="$(getent passwd "$SUDO_USER" 2>/dev/null | cut -d: -f6)"
  if [[ -n "$CANDIDATE_HOME" ]]; then
    USER_HOME="$CANDIDATE_HOME"
    USER_NAME="$SUDO_USER"
  fi
fi

OUT_DIR="$USER_HOME/.esp-handset"
mkdir -p "$OUT_DIR" /tmp 2>/dev/null || true
OUT="$OUT_DIR/i2c-doctor.txt"
OUT2="/tmp/digivice-i2c-doctor.txt"
PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
BUS="${DIGIVICE_MCP_I2C_BUS:-1}"
ADDR="${DIGIVICE_MCP_ADDR:-0x20}"

{
  echo "=== digivice-i2c-doctor $(date -Iseconds) ==="
  echo "host=$(hostname 2>/dev/null || echo '?') user=$USER_NAME"
  echo "prefix=$PREFIX"
  echo "configured_bus=$BUS configured_mcp_address=$ADDR"
  echo

  echo "--- I2C device nodes ---"
  if compgen -G "/dev/i2c-*" >/dev/null 2>&1; then
    ls -l /dev/i2c-* 2>&1
  else
    echo "NO /dev/i2c-* devices"
  fi
  echo

  echo "--- I2C adapters ---"
  if command -v i2cdetect >/dev/null 2>&1; then
    i2cdetect -l 2>&1
  else
    echo "i2cdetect missing (install i2c-tools)"
  fi
  echo

  echo "--- configured bus scan ---"
  if command -v i2cdetect >/dev/null 2>&1; then
    i2cdetect -y "$BUS" 2>&1
  else
    echo "cannot scan: i2cdetect missing"
  fi
  echo

  echo "--- all available bus scans ---"
  for dev in /dev/i2c-*; do
    [[ -e "$dev" ]] || continue
    bus="${dev##*-}"
    echo "### $dev"
    i2cdetect -y "$bus" 2>&1
    echo
  done

  echo "--- I2C configuration ---"
  for cfg in /boot/firmware/config.txt /boot/config.txt; do
    if [[ -f "$cfg" ]]; then
      echo "### $cfg"
      grep -nE '^[[:space:]]*(dtparam=i2c|dtoverlay=.*i2c)' "$cfg" 2>&1 || \
        echo "(no enabled I2C setting found)"
    fi
  done
  echo

  echo "--- MCP23017 read ---"
  if [[ -f "$PREFIX/esp_handset/mcp23017.py" ]]; then
    PYTHONPATH="$PREFIX${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
import esp_handset.mcp23017 as m

print(f"module_bus={m._BUS} module_address=0x{m._ADDR:02x}")
detected = m.detect_address()
print(
    "detected_address="
    + (f"0x{detected:02x}" if detected is not None else "NONE")
)
state = m.read_state()
if state is None:
    print("read_state=FAILED")
else:
    print(f"raw_a=0x{state.raw_a:02x} raw_b=0x{state.raw_b:02x}")
    pressed = ",".join(k for k, v in state.pressed.items() if v)
    print("pressed=" + pressed if pressed else "pressed=(none)")
PY
  else
    echo "mcp23017.py missing from $PREFIX"
  fi
  echo

  echo "--- button backend ---"
  if [[ -f "$PREFIX/buttons_inputd.py" ]]; then
    sha256sum "$PREFIX/buttons_inputd.py" 2>&1 || true
  else
    echo "buttons_inputd.py missing from $PREFIX"
  fi
  systemctl is-enabled digi-buttons-inputd.service 2>&1 || true
  systemctl is-active digi-buttons-inputd.service 2>&1 || true
  journalctl -u digi-buttons-inputd -n 50 --no-pager 2>&1 || true
  echo

  echo "--- kernel I2C messages ---"
  dmesg --time-format=iso 2>&1 | grep -iE 'i2c|mcp23017|cardkb' | tail -n 80 || \
    echo "(no matching kernel messages)"
  echo
  echo "=== end doctor ==="
} | tee "$OUT" | tee "$OUT2"

if [[ "$(id -u 2>/dev/null)" -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  chown "$SUDO_USER:$SUDO_USER" "$OUT" "$OUT2" 2>/dev/null || true
fi

echo
echo "Report: $OUT"
echo "Also:   $OUT2"
echo "Transfer: Prep I2C report → http://<pi>:8765/diag/i2c.txt"
exit 0
