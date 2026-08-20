# SIM7600G-H — Digivice (GPIO UART preferred)

Digivice talks AT to the modem on:

- **GPIO UART** (Digivice default) — HAT on the 40‑pin header → `/dev/serial0` (GPIO 14/15, pins **8 / 10**)
- **USB** — optional only if you are **not** using the Pi USB port for headphones/mic

Pi Zero has one USB data port. Digivice uses it for **USB audio**. Put the modem on UART.

Heltec notify panel uses **soft-UART on pins 16/18** (battery powered) — see [`HELTEC_UART_NOTIFY.md`](HELTEC_UART_NOTIFY.md). Do not put Heltec on GPIO UART (`serial0`) or on Pi USB.

## GPIO UART (recommended)

```bash
sudo digivice-modem-uart
# reboot if it just enabled UART
# ensure mode:
echo uart | sudo tee /etc/esp-handset/modem-backend
handset-phone
# Digivice → Settings → Network → Reconnect  (or Use GPIO UART)
```

| Item | Setting |
|------|---------|
| **PWR** | **PWR ↔ 3V3** (not D6 — Digivice Down uses BCM 6) |
| **UART** | Pi TX pin **8** → modem RX · Pi RX pin **10** ← modem TX · GND |
| Speed | 115200 |
| Mode file | `/etc/esp-handset/modem-backend` = **`uart`** |

```bash
ls -l /dev/serial0 /dev/sim7600-at
sudo timeout 1 cat /dev/serial0 &
echo -ne 'AT\r' | sudo tee /dev/serial0 >/dev/null
```

## USB modem (only if USB is free)

Skip this when the audio dongle needs the Pi USB port.

1. Data Micro‑USB from HAT **USB** (modem) → Pi  
2. Wait ~15–20s (NET LED)  
3. `ls -l /dev/sim7600-at /dev/ttyUSB*`  
4. `echo usb | sudo tee /etc/esp-handset/modem-backend`

## Mode

| File / env | Values |
|------------|--------|
| `/etc/esp-handset/modem-backend` | **`uart`** (Digivice) · `usb` · `auto` |
| `SIM7600_PORT` | force e.g. `/dev/serial0` |
| `SIM7600_BACKEND` | same as modem-backend |

`auto` still tries USB first — set **`uart`** explicitly when audio owns USB.

## Antennas

- LTE **MAIN** + **GNSS** IPEX for GPS  
- GNSS can work without a SIM; SMS/LTE need a SIM  

## Software

- `sim7600.py` opens USB and/or `serial0`  
- Settings → **Network** → Scan / Reconnect / Use GPIO UART  
