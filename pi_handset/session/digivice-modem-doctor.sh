#!/usr/bin/env bash
# Digivice SIM7600 doctor — GPIO UART / USB AT diagnostics.
#   digivice-modem-doctor
# Writes: ~/.esp-handset/modem-doctor.txt  (+ /tmp/digivice-modem-doctor.txt)
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
OUT_DIR="${HOME:-/tmp}/.esp-handset"
mkdir -p "$OUT_DIR" /etc/esp-handset /tmp 2>/dev/null || true
OUT="$OUT_DIR/modem-doctor.txt"
OUT2="/tmp/digivice-modem-doctor.txt"

# Prefer GUI user home when run as root
if [[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  UH="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
  if [[ -n "$UH" ]]; then
    OUT_DIR="$UH/.esp-handset"
    mkdir -p "$OUT_DIR"
    OUT="$OUT_DIR/modem-doctor.txt"
    chown "$SUDO_USER:$SUDO_USER" "$OUT_DIR" 2>/dev/null || true
  fi
fi

{
  echo "=== digivice-modem-doctor $(date -Iseconds) ==="
  echo "host=$(hostname) user=$(id -un) HOME=${HOME:-}"
  echo

  echo "--- modem-backend ---"
  echo -n "file: "; cat /etc/esp-handset/modem-backend 2>/dev/null || echo "(missing)"
  echo -n "flag modem-uart: "; [[ -f /etc/esp-handset/modem-uart ]] && echo yes || echo no
  echo "SIM7600_BACKEND=${SIM7600_BACKEND:-}"
  echo "SIM7600_PORT=${SIM7600_PORT:-}"
  echo

  echo "--- serial devices ---"
  ls -l /dev/serial0 /dev/ttyAMA0 /dev/ttyS0 /dev/sim7600-at 2>&1
  echo
  ls -l /dev/ttyUSB* 2>&1 | head -n 20
  echo

  echo "--- boot UART config ---"
  for c in /boot/firmware/config.txt /boot/config.txt; do
    if [[ -f "$c" ]]; then
      echo "file: $c"
      grep -E '^(enable_uart|dtoverlay=.*uart|dtparam=uart)' "$c" 2>/dev/null || echo "(no uart lines)"
    fi
  done
  for c in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
    if [[ -f "$c" ]]; then
      echo "cmdline: $c"
      cat "$c"
      if grep -qE 'console=serial0|console=ttyAMA0|console=ttyS0' "$c" 2>/dev/null; then
        echo "WARN: serial console still on cmdline — steals AT port"
        echo "  fix: raspi-config → Serial → login shell No, hardware Yes"
      fi
    fi
  done
  echo

  echo "--- groups (dialout) ---"
  id
  groups 2>/dev/null || true
  echo

  echo "--- dmesg (serial/simcom/usb) ---"
  dmesg 2>/dev/null | grep -iE 'ttyAMA|ttyS0|serial0|simcom|1e0e|option|cdc_acm|usb.*tty' | tail -n 40
  echo

  echo "--- AT probe (115200) ---"
  probe() {
    local port="$1"
    [[ -e "$port" ]] || { echo "$port: missing"; return; }
    if ! command -v python3 >/dev/null; then
      echo "$port: no python3"
      return
    fi
    python3 - "$port" <<'PY'
import sys, time
port = sys.argv[1]
try:
    import serial
except ImportError:
    print(port + ": pyserial missing")
    raise SystemExit(0)
try:
    s = serial.Serial(port, 115200, timeout=0.5)
except Exception as e:
    print(f"{port}: open FAIL {e}")
    raise SystemExit(0)
try:
    s.reset_input_buffer()
    s.write(b"AT\r")
    deadline = time.time() + 1.5
    buf = ""
    while time.time() < deadline:
        chunk = s.read(64)
        if chunk:
            buf += chunk.decode("utf-8", "replace")
            if "OK" in buf:
                print(f"{port}: AT → OK  ({buf.strip()[:60]!r})")
                raise SystemExit(0)
            if "ERROR" in buf:
                print(f"{port}: AT → ERROR  ({buf.strip()[:60]!r})")
                raise SystemExit(0)
        else:
            time.sleep(0.05)
    print(f"{port}: AT → NO RESPONSE  ({buf.strip()[:80]!r})")
finally:
    try:
        s.close()
    except Exception:
        pass
PY
  }
  for p in /dev/sim7600-at /dev/serial0 /dev/ttyAMA0 /dev/ttyS0 \
           /dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2 /dev/ttyUSB3; do
    probe "$p"
  done
  echo

  echo "--- Python Sim7600.diagnose ---"
  export PYTHONPATH="${PREFIX}:${PYTHONPATH:-}"
  python3 - <<'PY' 2>&1
import sys
sys.path.insert(0, "/opt/esp-handset")
try:
    from esp_handset.sim7600 import Sim7600, modem_backend
    print("backend:", modem_backend())
    print(Sim7600.diagnose())
    live = Sim7600.find_live_at_port()
    print("live_at:", live or "NONE")
except Exception as e:
    print("diagnose FAIL:", e)
PY
  echo

  echo "--- HAT checklist (visual) ---"
  echo "UART jumpers: both on B (Pi controls modem)"
  echo "PWR jumper: 3V3 (not D6)"
  echo "Flight: NC"
  echo "VCCIO: 3.3V"
  echo "PWR LED on? NET solid vs blink? (user reported separately)"
  echo
  echo "=== end ==="
} | tee "$OUT" | tee "$OUT2"

if [[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  chown "$SUDO_USER:$SUDO_USER" "$OUT" 2>/dev/null || true
fi

echo
echo "Report saved:"
echo "  $OUT"
echo "  $OUT2"
echo "Paste that file into Cursor chat."
