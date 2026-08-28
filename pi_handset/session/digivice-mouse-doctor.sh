#!/usr/bin/env bash
# Digivice MCP / Linux mouse-input diagnostics.
#   digivice-mouse-doctor
# Writes: ~/.esp-handset/mouse-doctor.txt (+ /tmp/digivice-mouse-doctor.txt)

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
OUT="$OUT_DIR/mouse-doctor.txt"
OUT2="/tmp/digivice-mouse-doctor.txt"
PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"

{
  echo "=== digivice-mouse-doctor $(date -Iseconds) ==="
  echo "host=$(hostname 2>/dev/null || echo '?') user=$USER_NAME"
  echo "prefix=$PREFIX"
  echo

  echo "--- session mode ---"
  for mode_file in \
    "$USER_HOME/.esp-handset/session_mode" \
    /etc/esp-handset/ui_mode
  do
    if [[ -f "$mode_file" ]]; then
      printf "%s=" "$mode_file"
      tr -d '[:space:]' <"$mode_file"
      echo
    else
      echo "$mode_file=(missing)"
    fi
  done
  if pgrep -f "handset_app.py" >/dev/null 2>&1; then
    echo "digivice_process=running (buttons daemon forces phone mode)"
  else
    echo "digivice_process=not-running"
  fi
  echo

  echo "--- button daemon ---"
  systemctl is-enabled digi-buttons-inputd.service 2>&1 || true
  systemctl is-active digi-buttons-inputd.service 2>&1 || true
  if [[ -f "$PREFIX/buttons_inputd.py" ]]; then
    sha256sum "$PREFIX/buttons_inputd.py" 2>&1 || true
  else
    echo "buttons_inputd.py missing from $PREFIX"
  fi
  echo

  echo "--- uinput / input devices ---"
  if [[ -e /dev/uinput ]]; then
    ls -l /dev/uinput 2>&1
  else
    echo "/dev/uinput missing"
  fi
  if [[ -r /proc/bus/input/devices ]]; then
    awk '
      /Name="Digivice-|Name="Digivice"/ {show=1; block=$0 "\n"; next}
      show {block=block $0 "\n"}
      show && /^$/ {printf "%s", block; show=0; block=""}
    ' /proc/bus/input/devices 2>&1
    echo
    input_device_count=0
    for input_node in /sys/class/input/*; do
      [[ -e "$input_node" ]] || continue
      input_device_count=$((input_device_count + 1))
    done
    echo "input_device_count=$input_device_count"
  else
    echo "/proc/bus/input/devices unavailable"
  fi
  echo

  echo "--- display input session ---"
  echo "DISPLAY=${DISPLAY:-"(unset)"}"
  echo "WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-"(unset)"}"
  echo "XAUTHORITY=${XAUTHORITY:-"(unset)"}"
  command -v xdotool 2>&1 || echo "xdotool=missing"
  command -v xinput 2>&1 || echo "xinput=missing"
  command -v libinput 2>&1 || echo "libinput=missing"
  if command -v xdotool >/dev/null 2>&1; then
    xdotool getmouselocation --shell 2>&1 || true
  fi
  if command -v xinput >/dev/null 2>&1; then
    xinput list 2>&1 || true
  fi
  echo

  echo "--- MCP configuration ---"
  for cfg in /etc/esp-handset/buttons-backend /etc/esp-handset/ui_mode; do
    if [[ -f "$cfg" ]]; then
      echo "$cfg=$(tr -d '[:space:]' <"$cfg")"
    fi
  done
  if [[ -f "$PREFIX/esp_handset/mcp23017.py" ]]; then
    PYTHONPATH="$PREFIX${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
import esp_handset.mcp23017 as m

print(f"module_bus={m._BUS} module_address=0x{m._ADDR:02x}")
print("pin_map=" + ",".join(
    f"{name}=P{port}{bit}" for name, (port, bit) in m._PIN_MAP.items()
))
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

  echo "--- recent button daemon log ---"
  journalctl -u digi-buttons-inputd -n 120 --no-pager 2>&1 || true
  echo
  echo "=== end doctor ==="
} | tee "$OUT" | tee "$OUT2"

if [[ "$(id -u 2>/dev/null)" -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  chown "$SUDO_USER:$SUDO_USER" "$OUT" "$OUT2" 2>/dev/null || true
fi

echo
echo "Report: $OUT"
echo "Also:   $OUT2"
echo "Transfer: Prep mouse report → http://<pi>:8765/diag/mouse.txt"
exit 0
