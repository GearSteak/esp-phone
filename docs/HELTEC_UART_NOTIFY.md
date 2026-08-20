# Heltec Wireless Tracker — Digivice notify panel

Use the Tracker **ST7735** for alerts and report **LiPo %** to Digivice. Power the Heltec from its **own LiPo** so it does not drain the Pi UPS.

Firmware: `heltec-wireless-tracker-gateway`

## Digivice preferred stack (USB audio + UART modem)

Pi Zero has **one** USB data port. Digivice needs it for the **USB headphones/mic** stick. The modem therefore stays on **GPIO UART**.

| Role | Link | Notes |
|------|------|--------|
| **USB audio** | Pi USB (or hub) | Headphones green · mic pink — [`DIGIVICE_AUDIO.md`](DIGIVICE_AUDIO.md) |
| **SIM7600** | GPIO UART `/dev/serial0` | Pins **8 / 10** (BCM 14/15) — `sudo digivice-modem-uart` |
| **Heltec notify** | **USB-C CDC** `/dev/esp-bridge` | **Not** GPIO UART (that port is the modem) |
| **Heltec power** | LiPo / battery | Common GND with Pi only if you also share UART; USB-C data alone is fine |

### One USB port → use a hub

```
Pi USB OTG ── USB hub ──┬── USB audio (headphones + mic)
                        └── Heltec USB-C (data; board on LiPo)
```

A **small powered hub** is ideal. An unpowered hub often works if the audio stick is low-draw and Heltec is on battery (data only on the USB-C cable).

Flash Heltec once over USB, leave it plugged on the hub for Digivice:

```bash
pio run -e heltec-wireless-tracker-gateway -t upload
# udev already makes /dev/esp-bridge (Espressif VID 303a)
```

Do **not** run `digivice-heltec-uart.sh` on this stack — it would steal `/dev/serial0` from the modem.

Test:

```bash
python3 - <<'PY'
from esp_handset.bridge import EspBridge
b = EspBridge()  # finds /dev/esp-bridge
b.open()
b.notif("Test", "Heltec USB", "info")
b.battery_query()
b.close()
PY
```

Digivice already forwards SMS / calls / alarms / timers / LoRa / email via `bridge.notif()`, and shows **`H78%`** from `BATTERY` lines.

## Battery % on Digivice

Onboard divider: **GPIO1** Vbat_Read, **GPIO2** ADC_CTRL.

```
BATTERY 78 3920
STATUS … bat=78 mv=3920 …
```

Updates ~every 30s. Query: `echo BATTERY > /dev/esp-bridge`

GPIO1/2 are also Vol+/Vol− pads — sampling is brief.

## Alternate: Heltec on GPIO UART (modem must not use serial0)

Only if the modem is **not** on `/dev/serial0` (rare for Digivice with USB audio).

| Pi (40-pin) | BCM | Heltec | Notes |
|-------------|-----|--------|--------|
| Pin **8** | **14** TX | RX (GPIO **44**) | Pi TX → Heltec RX |
| Pin **10** | **15** RX | TX (GPIO **43**) | Pi RX ← Heltec TX |
| Pin **6** | GND | GND | Common ground |
| — | — | LiPo | External power |

```bash
# DANGEROUS if modem-backend=uart — will conflict with SIM7600
sudo bash pi_handset/session/digivice-heltec-uart.sh
```

## Protocol (115200 8N1)

| Line | Action |
|------|--------|
| `NOTIF kind\|title\|body` | Show on ST7735 |
| `CLEAR` | Clear panel |
| `PING` | `PONG` |
| `STATUS` | LoRa / steps / **bat=N mv=N** |
| `BATTERY` | `BATTERY pct mv` |

See also: [`HELTEC_TRACKER_PINOUT.md`](HELTEC_TRACKER_PINOUT.md), [`SIM7600_STACK.md`](SIM7600_STACK.md), [`DIGIVICE_WIRING.md`](DIGIVICE_WIRING.md).
