# SIM7600G-H — Digivice (USB **or** GPIO UART)

Digivice talks AT to the modem on:

- **USB** — `/dev/sim7600-at` / `ttyUSB*` (SimTech `1e0e`), or  
- **GPIO UART** — HAT on the 40‑pin header → `/dev/serial0` (GPIO 14/15)

Heltec LoRa is a separate USB device (`/dev/esp-bridge`).

## GPIO UART (HAT on the header)

```bash
sudo digivice-modem-uart
# reboot if it just enabled UART
handset-phone
# Digivice → Settings → Network → Reconnect  (or Use GPIO UART)
```

| Item | Setting |
|------|---------|
| **PWR** | **PWR ↔ 3V3** (not D6 — Digivice Down uses BCM 6) |
| **UART** | Pi `/dev/serial0` @ 115200 |
| Mode file | `/etc/esp-handset/modem-backend` = `uart` |

```bash
ls -l /dev/serial0 /dev/sim7600-at
# quick AT probe (may need dialout group)
sudo timeout 1 cat /dev/serial0 &
echo -ne 'AT\r' | sudo tee /dev/serial0 >/dev/null
```

## USB (optional cable)

1. Data Micro‑USB from HAT **USB** (modem) → Pi  
2. Wait ~15–20s (NET LED)  
3. `ls -l /dev/sim7600-at /dev/ttyUSB*`

## Mode

| File / env | Values |
|------------|--------|
| `/etc/esp-handset/modem-backend` | `usb` · `uart` · `auto` (default) |
| `SIM7600_PORT` | force e.g. `/dev/serial0` |
| `SIM7600_BACKEND` | same as modem-backend |

`auto` tries USB first, then GPIO UART.

## Antennas

- LTE **MAIN** + **GNSS** IPEX for GPS  
- GNSS can work without a SIM; SMS/LTE need a SIM  

## Software

- `sim7600.py` opens USB and/or `serial0`  
- Settings → **Network** → Scan / Reconnect / Use GPIO UART  
