# Heltec Wireless Tracker — Digivice notify (no USB power)

## Why not USB / I2C / serial0

| Bus | Digivice owner | Why Heltec is not here |
|-----|----------------|------------------------|
| **USB** | Headphones + mic | Modem **or** Heltec on USB trips the Pi **polyfuse** |
| **I2C** pins 3/5 | **CardKB** | Leave that bus alone |
| **UART** pins 8/10 `/dev/serial0` | **SIM7600** | Modem AT only |
| **Soft-UART** pins **16 / 18** | **Heltec** | Battery powered, common GND only |

## Wiring (soft-UART)

| Pi (40-pin) | BCM | Heltec | Notes |
|-------------|-----|--------|--------|
| Pin **16** | **23** TX | **RX** GPIO **44** | Pi → Heltec |
| Pin **18** | **24** RX | **TX** GPIO **43** | Heltec → Pi |
| Pin **6** or **14** | GND | **GND** | Required |
| — | — | **LiPo** | **No USB cable to the Pi in normal use** |

Cross TX/RX. Flash the Heltec over USB **once**, then **unplug USB** and run from LiPo.

```
Pi USB ──────── USB audio only
SIM7600 ─────── GPIO UART pins 8/10
CardKB ──────── I2C pins 3/5
Heltec LiPo ─── soft-UART pins 16/18 + GND
```

## Pi setup

```bash
cd ~/esp-phone && git pull
sudo bash pi_handset/session/digivice-heltec-softuart.sh
sudo bash pi_handset/session/full-update.sh
# flash Heltec while USB is plugged for programming only:
pio run -e heltec-wireless-tracker-gateway -t upload
# then disconnect Heltec USB from the Pi — leave LiPo connected
```

Env written to `/etc/esp-handset/env`:

```
ESP_BRIDGE_SOFTUART=1
ESP_BRIDGE_SOFT_TX=23
ESP_BRIDGE_SOFT_RX=24
ESP_BRIDGE_SOFT_BAUD=9600
```

Needs `pigpiod` (bit-bang UART). The setup script enables it.

## Protocol (same as before, 9600 8N1 on soft-UART)

| Pi → Heltec | Heltec → Pi |
|-------------|-------------|
| `NOTIF kind\|title\|body` | `BATTERY pct mv` (~30s) |
| `CLEAR` / `PING` / `STATUS` / `BATTERY` | `STATUS … bat=N mv=N` · `PONG` · `READY` |

Digivice shows a Heltec radio icon in the status bar when the bridge answers
status probes, and pushes alerts to the ST7735.

## Doctor / fix on Pi

```bash
sudo digivice-heltec-doctor          # report → ~/.esp-handset/heltec-doctor.txt
sudo digivice-heltec-doctor --fix    # re-apply soft-UART env + restart Digivice
```

**Updates:** `digivice-full-update` and Settings → Update run `digivice-ensure-heltec` automatically (installs pigpio, writes `ESP_BRIDGE_SOFTUART=1`). Display installs preserve existing `ESP_BRIDGE_*` lines when rewriting env.

Or **Tools → Transfer → Prep Heltec report**, then download `/diag/heltec.txt`.

## Do not run

- `digivice-heltec-uart.sh` — steals modem `serial0`
- Heltec or modem on Pi USB for day-to-day use

See [`DIGIVICE_WIRING.md`](DIGIVICE_WIRING.md), [`SIM7600_STACK.md`](SIM7600_STACK.md).
