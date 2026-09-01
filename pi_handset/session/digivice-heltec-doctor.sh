#!/usr/bin/env bash
# Digivice Heltec soft-UART doctor — env, pigpiod, GPIO probe, live PING.
#   digivice-heltec-doctor              # auto-install pigpio if missing, then report
#   digivice-heltec-doctor --fix        # ensure + restart Digivice
# Writes: ~/.esp-handset/heltec-doctor.txt (+ /tmp/digivice-heltec-doctor.txt)
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
ROOT="$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd || true)"
ENV_FILE="/etc/esp-handset/env"
OUT_DIR="${HOME:-/tmp}/.esp-handset"
mkdir -p "$OUT_DIR" /etc/esp-handset /tmp 2>/dev/null || true
OUT="$OUT_DIR/heltec-doctor.txt"
OUT2="/tmp/digivice-heltec-doctor.txt"
FIX=0
REPORT_ONLY=0
for a in "$@"; do
  [[ "$a" == "--fix" ]] && FIX=1
  [[ "$a" == "--report-only" || "$a" == "report-only" ]] && REPORT_ONLY=1
done
[[ "${DIGIVICE_HELTEC_REPORT_ONLY:-0}" == "1" ]] && REPORT_ONLY=1
[[ "${DIGIVICE_ENSURE_HELTEC_NO_RESTART:-0}" == "1" ]] && REPORT_ONLY=1

if [[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  UH="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
  if [[ -n "$UH" ]]; then
    OUT_DIR="$UH/.esp-handset"
    mkdir -p "$OUT_DIR"
    OUT="$OUT_DIR/heltec-doctor.txt"
    chown "$SUDO_USER:$SUDO_USER" "$OUT_DIR" 2>/dev/null || true
  fi
fi

need_ensure=0
if ! python3 -c "import pigpio" 2>/dev/null; then
  need_ensure=1
fi
if [[ ! -f "$ENV_FILE" ]] || ! grep -qE '^ESP_BRIDGE_SOFTUART=(1|true|yes|on)' "$ENV_FILE" 2>/dev/null; then
  need_ensure=1
fi

run_ensure() {
  local extra=()
  [[ "$FIX" -eq 1 ]] && extra+=(--restart)
  for script in \
    "$PREFIX/session/ensure-heltec-softuart.sh" \
    "$(dirname "$0")/ensure-heltec-softuart.sh" \
    "${ROOT}/pi_handset/session/ensure-heltec-softuart.sh"
  do
    if [[ -f "$script" ]]; then
      echo "[heltec-doctor] ensuring soft-UART (pigpio + env)…"
      bash "$script" "${extra[@]}" 2>&1 | tee -a "$OUT" || true
      return 0
    fi
  done
  for script in \
    "$PREFIX/session/digivice-heltec-softuart.sh" \
    "$(dirname "$0")/digivice-heltec-softuart.sh" \
    "${ROOT}/pi_handset/session/digivice-heltec-softuart.sh"
  do
    if [[ -f "$script" ]]; then
      bash "$script" 2>&1 | tee -a "$OUT" || true
      return 0
    fi
  done
  echo "[heltec-doctor] ensure script missing" | tee -a "$OUT"
}

if [[ "$(id -u)" -eq 0 ]]; then
  if [[ "$REPORT_ONLY" -ne 1 && ( "$FIX" -eq 1 || "$need_ensure" -eq 1 ) ]]; then
    run_ensure
  fi
elif [[ "$need_ensure" -eq 1 && "$REPORT_ONLY" -ne 1 ]]; then
  echo "[heltec-doctor] pigpio/env missing — re-run via sudo or Prep Heltec report" | tee -a "$OUT"
fi

{
  echo "=== digivice-heltec-doctor $(date -Iseconds) ==="
  echo "host=$(hostname) user=$(id -un) prefix=$PREFIX fix=$FIX report_only=$REPORT_ONLY"
  echo

  echo "--- wiring (Digivice soft-UART) ---"
  echo "Pi pin 16 BCM23 TX  → Heltec GPIO44 RX"
  echo "Pi pin 18 BCM24 RX  ← Heltec GPIO43 TX"
  echo "Pi GND              → Heltec GND"
  echo "Heltec power        = LiPo / 5V (USB only for flashing — unplug for normal use)"
  echo

  echo "--- /etc/esp-handset/env (bridge) ---"
  if [[ -f "$ENV_FILE" ]]; then
    grep -E '^ESP_BRIDGE_' "$ENV_FILE" 2>/dev/null || echo "(no ESP_BRIDGE_* lines — run: sudo digivice-heltec-doctor --fix)"
    echo "--- full env ---"
    cat "$ENV_FILE" 2>/dev/null
  else
    echo "MISSING $ENV_FILE"
  fi
  echo

  soft_ok=0
  if [[ -f "$ENV_FILE" ]] && grep -qE '^ESP_BRIDGE_SOFTUART=(1|true|yes|on)' "$ENV_FILE" 2>/dev/null; then
    soft_ok=1
    echo "soft-UART env: OK"
  else
    echo "soft-UART env: MISSING — Pi will not use GPIO 16/18 for Heltec"
    echo "  fix: sudo digivice-heltec-doctor --fix"
  fi
  if [[ -f "$ENV_FILE" ]] && grep -qE '^ESP_BRIDGE_UART=' "$ENV_FILE" 2>/dev/null; then
    echo "WARN: ESP_BRIDGE_UART set — conflicts with modem serial0"
    echo "  use soft-UART only: sudo digivice-heltec-softuart.sh"
  fi
  echo

  echo "--- pigpiod ---"
  systemctl is-enabled pigpiod 2>&1 || true
  systemctl is-active pigpiod 2>&1 || true
  if command -v pigpiod >/dev/null 2>&1; then
    echo "pigpiod binary: $(command -v pigpiod)"
  elif [[ -x /usr/local/bin/pigpiod ]]; then
    echo "pigpiod binary: /usr/local/bin/pigpiod (source build — OK if client connected)"
  else
    echo "pigpiod binary: MISSING"
  fi
  if python3 -c "import pigpio; pi=pigpio.pi(); print('pigpio client:', 'connected' if pi.connected else 'NOT connected'); pi.stop()" 2>&1; then
    :
  else
    echo "python3-pigpio: import/connect FAILED"
  fi
  echo

  echo "--- GPIO lines (BCM23 TX, BCM24 RX) ---"
  TX="${ESP_BRIDGE_SOFT_TX:-23}"
  RX="${ESP_BRIDGE_SOFT_RX:-24}"
  if [[ -f "$ENV_FILE" ]]; then
    v="$(grep -E '^ESP_BRIDGE_SOFT_TX=' "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d ' \"')"
    [[ -n "$v" ]] && TX="$v"
    v="$(grep -E '^ESP_BRIDGE_SOFT_RX=' "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d ' \"')"
    [[ -n "$v" ]] && RX="$v"
  fi
  echo "configured TX=BCM$TX (Pi→Heltec)  RX=BCM$RX (Heltec→Pi)"
  if [[ -r "/sys/class/gpio/gpio${TX}/value" ]]; then
    echo "TX sysfs value: $(cat "/sys/class/gpio/gpio${TX}/value" 2>/dev/null)"
  fi
  if [[ -r "/sys/class/gpio/gpio${RX}/value" ]]; then
    echo "RX sysfs value: $(cat "/sys/class/gpio/gpio${RX}/value" 2>/dev/null)"
  fi
  python3 - "$TX" "$RX" <<'PY' 2>&1
import sys
tx, rx = int(sys.argv[1]), int(sys.argv[2])
try:
    import pigpio
except ImportError:
    print("pigpio: not installed")
    raise SystemExit(0)
pi = pigpio.pi()
if not pi.connected:
    print("pigpio: daemon not connected")
    raise SystemExit(0)
try:
    print(f"TX BCM{tx} level={pi.read(tx)} (idle should be 1)")
    print(f"RX BCM{rx} level={pi.read(rx)} (pull-up, often 1)")
except Exception as e:
    print(f"GPIO read FAIL: {e}")
finally:
    pi.stop()
PY
  echo

  echo "--- USB serial (should be empty in normal use) ---"
  lsusb 2>/dev/null | grep -iE '303a|espressif|heltec|ch340|cp210' || echo "(no obvious ESP USB — good for Digivice)"
  ls -l /dev/ttyUSB* /dev/ttyACM* 2>&1 | head -n 10
  echo

  echo "--- live soft-UART probe (PING + STATUS) ---"
  if [[ "$REPORT_ONLY" -eq 1 ]]; then
    echo "SKIP — report-only mode (no UART probe)"
  elif pgrep -f handset_app.py >/dev/null 2>&1; then
    echo "SKIP — Digivice bridge already owns soft-UART (Heltec icon = live status)"
    echo "Stop Digivice first if you need an isolated PING test"
  else
  export PYTHONPATH="${PREFIX}:${PYTHONPATH:-}"
  python3 - <<'PY'
import os, sys, time
sys.path.insert(0, "/opt/esp-handset")
os.environ.setdefault("ESP_BRIDGE_SOFTUART", "1")
try:
    from esp_handset.softuart_pigpio import SoftUartLink, softuart_enabled
except Exception as e:
    print("import FAIL:", e)
    raise SystemExit(0)
print("softuart_enabled():", softuart_enabled())
link = SoftUartLink()
try:
    link.open()
except Exception as e:
    print("open FAIL:", e)
    print("  → pigpiod running? env ESP_BRIDGE_SOFTUART=1? wiring + Heltec powered?")
    raise SystemExit(0)
print(f"open OK on {link.port if hasattr(link, 'port') else f'tx{link.tx}/rx{link.rx}@{link.baud}'}")
for cmd in (b"PING\n", b"STATUS\n"):
    print(f">>> {cmd.decode().strip()}")
    link.write(cmd)
    time.sleep(0.9)
    rx = link.read(512)
    text = rx.decode("utf-8", "replace").strip()
    if text:
        for line in text.splitlines():
            print("<<<", line)
        if any(line.startswith(("PONG", "STATUS", "READY", "BATTERY")) for line in text.splitlines()):
            print("RESULT: Heltec responded — status bar should show connected after digivice-start")
    else:
        print("<<< (no response)")
        print("RESULT: NO RESPONSE — check TX/RX swap, GND, Heltec on LiPo (not PC USB), firmware flashed")
link.close()
PY
  fi
  echo

  echo "--- handset log (bridge / heltec / pigpio) ---"
  for log in \
    "${OUT_DIR}/handset.log" \
    "${HOME}/.esp-handset/handset.log" \
    "/home/gearsteak/.esp-handset/handset.log" \
    "/home/pi/.esp-handset/handset.log" \
    "/home/isaac/.esp-handset/handset.log"
  do
    if [[ -f "$log" ]]; then
      echo "### $log"
      grep -iE 'heltec|LoRa ESP|softuart|soft-uart|pigpio|bridge|PONG|STATUS|READY' "$log" 2>/dev/null | tail -n 30
      echo
    fi
  done
  echo

  echo "--- checklist ---"
  echo "[ ] Heltec shows 'ESP notify' + id on its screen (firmware OK)"
  echo "[ ] Heltec NOT on USB to Pi/PC during test (UART pins 16/18 wired)"
  echo "[ ] ESP_BRIDGE_SOFTUART=1 in /etc/esp-handset/env"
  echo "[ ] pigpiod active"
  echo "[ ] PING above returned PONG or STATUS"
  echo "[ ] After fix: sudo digivice-start"
  echo
  echo "=== end doctor ==="
} | tee "$OUT" | tee "$OUT2"

if [[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  chown "$SUDO_USER:$SUDO_USER" "$OUT" "$OUT2" 2>/dev/null || true
fi

if [[ "$FIX" -eq 1 && "$REPORT_ONLY" -ne 1 ]]; then
  echo
  echo "[heltec-doctor] Restarting Digivice (use after update, not from Transfer)…"
  if [[ -n "${DIGIVICE_ENSURE_HELTEC_NO_RESTART:-}" && "${DIGIVICE_ENSURE_HELTEC_NO_RESTART}" != "0" ]]; then
    echo "[heltec-doctor] skip restart — DIGIVICE_ENSURE_HELTEC_NO_RESTART set"
  elif command -v digivice-start >/dev/null 2>&1; then
    digivice-start 2>&1 | tail -n 15
  elif [[ -f /usr/local/bin/digivice-start ]]; then
    /usr/local/bin/digivice-start 2>&1 | tail -n 15
  else
    echo "digivice-start not installed — reboot session manually"
  fi
fi

echo
echo "Report saved:"
echo "  $OUT"
echo "  $OUT2"
echo "Paste into Cursor, or Transfer → Prep Heltec report → /diag/heltec.txt"
