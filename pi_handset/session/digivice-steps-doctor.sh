#!/usr/bin/env bash
# SW-520D / BCM17 step sensor doctor — run on the Pi (SSH or keyboard).
#
#   digivice-steps-doctor
#   digivice-steps-doctor --scan     # also sample BCM18/22/27 (common mix-ups)
#
set -euo pipefail

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
SCAN=0
BCM="${DIGI_STEPS_BCM:-17}"
DURATION="${DIGI_STEPS_DOCTOR_S:-5}"

for a in "$@"; do
  [[ "$a" == "--scan" ]] && SCAN=1
done

if [[ -f /etc/esp-handset/env ]]; then
  # shellcheck disable=SC1091
  source /etc/esp-handset/env 2>/dev/null || true
fi
[[ -n "${DIGI_STEPS_BCM:-}" ]] && BCM="$DIGI_STEPS_BCM"

echo "=== digivice steps doctor ==="
echo "BCM target: $BCM (physical pin 11 on 40-pin header)"
echo "Duration: ${DURATION}s — shake / tap the tilt sensor now"
echo

if [[ -f /run/digivice/steps-debug.json ]]; then
  echo "--- /run/digivice/steps-debug.json ---"
  cat /run/digivice/steps-debug.json
  echo
fi

echo "--- buttons daemon ---"
systemctl is-active digi-buttons-inputd 2>&1 || true
journalctl -u digi-buttons-inputd -n 8 --no-pager 2>&1 | grep -i steps || true
echo

export PYTHONPATH="${PREFIX}${PYTHONPATH:+:$PYTHONPATH}"
python3 - "$BCM" "$DURATION" "$SCAN" <<'PY'
import json
import os
import sys
import time

bcm = int(sys.argv[1])
duration = float(sys.argv[2])
scan = int(sys.argv[3])

active_low = (os.environ.get("DIGI_STEPS_ACTIVE_LOW") or "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
)


def pressed(level: int) -> bool:
    return level == 0 if active_low else level != 0


def sample_lgpio(pins: list[int], seconds: float) -> dict[int, dict]:
    import lgpio

    h = lgpio.gpiochip_open(0)
    out: dict[int, dict] = {}
    try:
        for pin in pins:
            try:
                lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_UP)
            except Exception as e:
                out[pin] = {"error": str(e)}
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            for pin in pins:
                if pin not in out or "error" in out[pin]:
                    continue
                st = out[pin]
                try:
                    level = int(lgpio.gpio_read(h, pin))
                except Exception as e:
                    st["error"] = str(e)
                    continue
                st.setdefault("min", level)
                st.setdefault("max", level)
                st.setdefault("toggles", 0)
                st.setdefault("edges", 0)
                st.setdefault("last", level)
                st.setdefault("prev_pressed", pressed(level))
                st["min"] = min(st["min"], level)
                st["max"] = max(st["max"], level)
                if level != st["last"]:
                    st["toggles"] += 1
                    st["last"] = level
                hit = pressed(level)
                if hit and not st["prev_pressed"]:
                    st["edges"] += 1
                st["prev_pressed"] = hit
            time.sleep(0.0005)
    finally:
        lgpio.gpiochip_close(h)
    return out


pins = [bcm]
if scan:
    for p in (18, 22, 27):
        if p not in pins:
            pins.append(p)

print(f"active_low={active_low}  pins={pins}")
try:
    stats = sample_lgpio(pins, duration)
except Exception as e:
    print(f"lgpio sample FAILED: {e}")
    sys.exit(1)

for pin in pins:
    st = stats.get(pin, {})
    if "error" in st:
        print(f"BCM{pin}: ERROR {st['error']}")
        continue
    print(
        f"BCM{pin}: min={st.get('min')} max={st.get('max')} "
        f"toggles={st.get('toggles', 0)} edges={st.get('edges', 0)} "
        f"last={st.get('last')}"
    )

target = stats.get(bcm, {})
if "error" in target:
    print("\nRESULT: BCM pin could not be opened — GPIO busy or wrong OS image?")
elif target.get("toggles", 0) == 0:
    print(
        "\nRESULT: BCM pin never changed."
        "\n  • Confirm sensor on physical pin 11 (BCM17), not pin 17 (BCM18 = LCD BL)."
        "\n  • One sensor leg → pin 11, other leg → GND."
        "\n  • Short pin 11 to GND with a wire — toggles should jump."
    )
else:
    print(f"\nRESULT: BCM{bcm} saw activity — software path should work after update.")
PY

echo "=== end steps doctor ==="
