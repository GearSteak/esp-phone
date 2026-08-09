#!/usr/bin/env bash
# Blank the userspace ST7789 (clear frozen Digivice last frame + backlight off).
# Called when leaving Digivice for Linux desktop.
set +e
export ESP_HANDSET_SPI_BACKEND=userspace
# Prefer installed tree
export PYTHONPATH="/opt/esp-handset:${PYTHONPATH:-}"
if [[ -d /opt/esp-handset/esp_handset ]]; then
  :
elif [[ -d "$(dirname "$0")/../esp_handset" ]]; then
  export PYTHONPATH="$(cd "$(dirname "$0")/.." && pwd):${PYTHONPATH}"
fi

/usr/bin/python3 - <<'PY'
import sys
try:
    from esp_handset import st7789_spi as st
except Exception as e:
    print(f"[spi-blank] import: {e}", file=sys.stderr)
    sys.exit(0)
if st.init():
    st.blank(backlight_off=True)
    st.close(blank_panel=False)  # already blanked
    print("[spi-blank] ok", flush=True)
else:
    print("[spi-blank] SPI not available (ok if not using userspace)", flush=True)
PY
