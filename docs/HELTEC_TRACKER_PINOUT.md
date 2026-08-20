# Heltec Wireless Tracker — handset pinout

Gateway firmware: `pio run -e heltec-wireless-tracker-gateway -t upload`

USB-C to Pi = CDC serial (`/dev/esp-bridge`). Onboard **SX1262** LoRa; **ST7735 = notification panel**. Cellular is SIM7600 on **USB AT** — see `docs/SIM7600_STACK.md`.

## Reserved onboard (do not wire)

| Function | GPIO |
| --- | --- |
| LoRa NSS (CS) | 8 |
| LoRa SCK | 9 |
| LoRa MOSI | 10 |
| LoRa MISO | 11 |
| LoRa RST | 12 |
| LoRa BUSY | 13 |
| LoRa DIO1 | 14 |
| TFT CS | 38 |
| TFT RST / DC / SCLK / MOSI | 39 / 40 / 41 / 42 |
| TFT backlight | 21 |
| Vext (TFT + GNSS power) | 3 — firmware holds **HIGH** |
| GNSS UART RX / TX | 33 / 34 |
| USB D− / D+ | 19 / 20 |
| XTAL 32k | 15 / 16 |
| Boot / user | 0 |

## 5×10 QWERTY matrix

Diode-OR matrix, same layout as Waveshare gateway. Rows driven LOW to scan; columns `INPUT_PULLUP`.

| | C0 | C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 | C9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **GPIO** | **18** | **26** | **35** | **36** | **37** | **43** | **44** | **45** | **47** | **48** |
| R0 **4** | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 0 |
| R1 **5** | Q | W | E | R | T | Y | U | I | O | P |
| R2 **6** | A | S | D | F | G | H | J | K | L | ; |
| R3 **7** | Z | X | C | V | B | N | M | , | . | / |
| R4 **17** | Shift | Space | Bksp | Enter | ← | → | ↑ | ↓ | Call | End |

**Wire:** one diode per key (anode → column, cathode → row) or common diode-per-column scheme matching your PCB.

### Volume (side)

| Button | GPIO | Notes |
| --- | --- | --- |
| Vol+ | **1** | Also board Vbat sense — button to GND, `INPUT_PULLUP` |
| Vol− | **2** | Also ADC control on Heltec — button to GND |
| Mute | **46** | Input-only on S3 — button to GND |

Gateway firmware samples **GPIO1/2** for LiPo % (`BATTERY pct mv` / `STATUS … bat=N`) about every 30s, then restores pull-ups so Vol+/− still work. Digivice shows **`H78%`** in the status bar when the bridge is connected.

## Header cheat sheet (free for keys)

Use these for the matrix + volume only:

`1, 2, 4, 5, 6, 7, 17, 18, 26, 35, 36, 37, 43, 44, 45, 46, 47, 48`

Avoid LoRa/`TFT`/`USB`/`GNSS`/`15`/`16`/`0`/`3`/`21`.

## SW-520D tilt → steps

Crude pedometer on Heltec (not an IMU). Wire:

| SW-520D | Heltec |
| --- | --- |
| Either leg | **GPIO 7** |
| Other leg | **GND** |

Firmware: `INPUT_PULLUP`, counts settled transitions with debounce + ~280 ms refractory. CDC:

```
STEPS 42
STEPS?          → STEPS n
STEPS RESET     → STEPS 0
```

Digivice: **Tools → Steps**. Session count lives on ESP; Pi keeps a daily total in `~/.esp-handset/steps.json`.

`STEP_TILT_ENABLE=1` by default on `heltec-wireless-tracker-gateway`. Do not enable the QWERTY matrix on GPIO 7 at the same time.

**Note:** GPIO **43/44** are labeled UART0 TX/RX on the Heltec silkscreen. With USB-CDC they are free for the matrix; do not also use a USB–UART dongle on those pads.

## Power / antennas

- Power Tracker from LiPo or USB; Pi has its own UPS.
- Fit LoRa IPEX antenna before TX.
- GNSS optional later (UART 33/34 + Vext already on).

## Flash

```bash
pio run -e heltec-wireless-tracker-gateway -t upload
pio device monitor -e heltec-wireless-tracker-gateway
```

## CardKB (M5Stack Unit) — detachable typing

I2C Grove hotplug into Heltec. Firmware polls `@0x5F` and emits `KEY` lines to the Pi.

| Grove wire | Signal | Heltec GPIO / rail |
| --- | --- | --- |
| Black | GND | GND |
| Red | 5V | **5V** (not 3V3) |
| Yellow | SDA | **GPIO 6** |
| White | SCL | **GPIO 17** |

Use a Grove extension so the plug sticks out of the case. Unplug anytime; Digivice stick + OSK still work.

`CARDKB_ENABLE=1` by default on `heltec-wireless-tracker-gateway` (matrix keyboard off).
