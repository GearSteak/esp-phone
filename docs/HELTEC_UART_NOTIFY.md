# Heltec Wireless Tracker — UART notify panel (battery powered)

Use the Tracker **ST7735** as a side notification display while the Pi runs Digivice. Power the Heltec from its **own LiPo / battery** so it does not drain the Pi UPS.

Firmware: `heltec-wireless-tracker-gateway` (same `NOTIF` / `CLEAR` / `PING` protocol as USB).

## Wiring (Pi GPIO UART ↔ Heltec UART0)

| Pi (40-pin) | BCM | Heltec pad | Notes |
|-------------|-----|------------|--------|
| Pin **8** | **14** TX | **RX** (GPIO **44**) | Pi TX → Heltec RX |
| Pin **10** | **15** RX | **TX** (GPIO **43**) | Pi RX ← Heltec TX |
| Pin **6** | GND | **GND** | Common ground only |
| — | — | **5V / VUSB / LiPo** | **Heltec power from battery** — do not feed from Pi 5V for 24/7 notify |

Cross the data lines: **Pi TX → Heltec RX**, **Pi RX ← Heltec TX**.

### UART conflict with SIM7600

If the modem uses **GPIO UART** (`/dev/serial0`), you cannot share that port with the Heltec. Options:

1. **SIM7600 on USB** (recommended) — free GPIO UART for Heltec  
2. **Heltec on USB-C** — keep existing `/dev/esp-bridge` USB symlink  
3. **USB–serial adapter** on spare USB for Heltec (second `/dev/ttyUSB*`, set `ESP_BRIDGE_PORT`)

## Heltec power

- Run from **Heltec LiPo** or a small **5V battery pack** into the board’s USB / battery input.  
- **Do not** power the Tracker from the Pi’s 5V pin for always-on notify — it will pull from the Pi UPS.  
- Only **GND** must be shared with the Pi for UART reference.

## Pi setup

```bash
cd ~/esp-phone && git pull

# Enable Pi UART, disable serial console on the GPIO port
sudo bash pi_handset/session/digivice-heltec-uart.sh

# Reboot, then flash Heltec (USB once for programming)
pio run -e heltec-wireless-tracker-gateway -t upload
```

After reboot, the session uses:

```bash
export ESP_BRIDGE_PORT=/dev/esp-bridge-uart
export ESP_BRIDGE_UART=1
```

Test from the Pi:

```bash
echo 'NOTIF info|Hello|UART works' > /dev/esp-bridge-uart
# or
python3 - <<'PY'
from esp_handset.bridge import EspBridge
b = EspBridge(port="/dev/esp-bridge-uart")
b.open()
b.notif("Test", "Heltec UART", "info")
b.close()
PY
```

Digivice forwards **SMS, calls, alarms, timers, LoRa, email**, etc. to the panel via `store.push_notif()` → `bridge.notif()`.

## Protocol (115200 8N1)

Pi → Heltec (one line per command):

| Line | Action |
|------|--------|
| `NOTIF kind\|title\|body` | Show on ST7735 |
| `CLEAR` | Clear panel |
| `PING` | Heltec replies `PONG` |
| `STATUS` | Battery / LoRa summary |

Heltec → Pi (optional): `KEY …`, `STEPS n`, LoRa lines — same as USB gateway.

## Antenna

Fit the **LoRa IPEX** antenna before transmitting. GNSS is optional (UART 33/34).

See also: [`HELTEC_TRACKER_PINOUT.md`](HELTEC_TRACKER_PINOUT.md), [`DIGIVICE_WIRING.md`](DIGIVICE_WIRING.md).
