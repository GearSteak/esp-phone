# SIM7600G-H — Digivice (USB AT)

Modem AT/SMS/GNSS/data use **USB** to the Pi (Micro‑USB cable or Zero **pogo**). Heltec is a second USB device (`/dev/esp-bridge`).

## Layout

```
[ Waveshare 2" SPI LCD 240×320 ]   Digivice UI (GPIO wires, not HAT stick)
[ optional height / mounts ]
[ Pi Zero 2 W ]
[ battery / UPS ]
        │
        ├─ GPIO ─► ↑ ↓ ← → Confirm Back Home
        ├─ USB ──► SIM7600G-H (AT / RNDIS)
        └─ USB ──► Heltec Tracker (LoRa; TFT optional)
```

SIM7600 can sit **flat** beside the stack and only USB‑link — same software.

## HAT jumpers (SIM7600)

| Jumper | Setting | Why |
|--------|---------|-----|
| **PWR** | **PWR–3V3** (auto on) | Simple always-on; avoid GPIO that the LCD uses |
| **Flight** | **NC** | Leave unused |
| **UART** | USB path (not B) | Digivice uses SimTech **USB** AT, not Pi GPIO UART |

## Software

- udev → `/dev/sim7600-at` (SimTech `1e0e`, AT interface)
- `sim7600.py` opens that port (or `ttyUSB2`-class)
- Re-run `sudo ./install-handset.sh` to restore USB udev and remove any old UART symlink service

## Checklist

1. 2" LCD + buttons: [`WAVESHARE_2INCH_LCD.md`](WAVESHARE_2INCH_LCD.md), [`DIGI_BUTTONS.md`](DIGI_BUTTONS.md)  
2. USB (or pogo) Pi ↔ SIM7600; **PWR–3V3**  
3. Heltec on its own USB (optional)  
4. Antennas + SIM  
5. `ls -l /dev/sim7600-at` / `dmesg | grep -i ttyUSB`  

RNDIS/NDIS cellular data works over USB (ModemManager / Waveshare wiki).
