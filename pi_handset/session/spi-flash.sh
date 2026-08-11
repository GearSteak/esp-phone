#!/usr/bin/env bash
# Pure ST7789 hardware prove — NO X, NO Digivice UI.
# If this does not flash red/green/blue on the 2" panel, the problem is
# spidev/wiring/config — not HDMI apps.
#
#   digivice-spi-flash
#   sudo digivice-spi-flash
#
set +e
set -u

export ESP_HANDSET_SPI_BACKEND=userspace
PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
for p in \
  "$PREFIX" \
  "$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)" \
  "$HOME/esp-phone/pi_handset" \
  /home/*/esp-phone/pi_handset
do
  # shellcheck disable=SC2086
  for d in $p; do
    if [[ -d "$d/esp_handset" ]]; then
      export PYTHONPATH="$d:${PYTHONPATH:-}"
      break 2
    fi
  done
done

echo "=== digivice-spi-flash (userspace ST7789) ==="
echo "PYTHONPATH=$PYTHONPATH"
ls -l /dev/spidev* 2>&1 || echo "NO SPIDEV"
echo "flags: $(cat /etc/esp-handset/spi-userspace 2>/dev/null || echo none)"

# Free bus
pkill -f handset_app.py 2>/dev/null
pkill -f desktop_spi_mirror.py 2>/dev/null
sleep 0.4

/usr/bin/python3 - <<'PY'
import sys, time, os
print("[flash] python", sys.version.split()[0], flush=True)

try:
    import spidev  # noqa: F401
    print("[flash] spidev import OK", flush=True)
except Exception as e:
    print("[flash] FAIL spidev:", e, flush=True)
    print("  sudo apt install -y python3-spidev", flush=True)
    sys.exit(2)

try:
    import RPi.GPIO as GPIO  # noqa: F401
    print("[flash] RPi.GPIO OK", flush=True)
except Exception as e:
    print("[flash] RPi.GPIO fail:", e, "— trying anyway", flush=True)

try:
    from esp_handset import st7789_spi as st
except Exception as e:
    print("[flash] FAIL import st7789_spi:", e, flush=True)
    print("  PYTHONPATH must include /opt/esp-handset", flush=True)
    sys.exit(3)

# Force cold open
try:
    if st.ready():
        st.close(blank_panel=False)
except Exception:
    pass

if not st.init():
    print("[flash] FAIL st.init() — no /dev/spidev0.0 or GPIO?", flush=True)
    print("  ls -l /dev/spidev0.0", flush=True)
    print("  sudo digivice-install-spi-userspace && sudo reboot", flush=True)
    sys.exit(4)

st.wake_display()
w, h = st.size()
print(f"[flash] panel {w}x{h} — flashing R/G/B (2s each)", flush=True)

colors = [
    (255, 0, 0, "RED"),
    (0, 255, 0, "GREEN"),
    (0, 0, 255, "BLUE"),
    (255, 255, 255, "WHITE"),
    (0, 0, 0, "BLACK"),
]
for r, g, b, name in colors:
    print(f"[flash] {name}", flush=True)
    st.fill(r, g, b)
    st.wake_display()
    time.sleep(1.5)

# Leave a bright green "alive" screen (backlight on)
st.fill(0, 200, 0)
st.wake_display()
st.close(blank_panel=False)
print("[flash] DONE — if you saw colors, HARDWARE works.", flush=True)
print("[flash] Next: handset-phone   (or digivice-fix-screens)", flush=True)
sys.exit(0)
PY
rc=$?
echo "exit=$rc"
exit $rc
