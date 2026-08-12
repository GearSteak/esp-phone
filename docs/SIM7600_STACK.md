# SIM7600G-H — Digivice (USB AT)

Digivice talks to the modem over **USB** (`/dev/sim7600-at` / `ttyUSB*`).  
Heltec LoRa is a **second** USB device (`/dev/esp-bridge`).

## Layout

```
[ Waveshare 2" SPI LCD ]     Digivice UI
[ Pi Zero 2 W ]
        │
        ├─ GPIO ─► ↑ ↓ ← → Confirm Back Home
        ├─ USB ──► SIM7600G-H  (AT / SMS / GNSS)   ← required cable or pogo
        └─ USB ──► Heltec Tracker (optional LoRa)
```

The HAT can sit **beside** the stack; stacking the 40‑pin header alone is **not** enough
for Digivice — you still need the **USB data link**.

## Jumpers (set these)

| Jumper | Digivice setting | Why |
|--------|------------------|-----|
| **PWR** | **PWR ↔ 3V3** | Auto power-on. **Do not** use **PWR ↔ D6** — BCM GPIO 6 is the Digivice **Down** button. |
| **Flight** | **NC** (no jumper) | Leave open |
| **UART A/B/C** | anything / unused for Digivice | Digivice uses the HAT’s **USB modem** port (SimTech), not Pi GPIO UART |
| **VCCIO** | **3.3V** (default for Pi) | Logic level |

## USB (most common “not connected” cause)

1. Plug a **data** Micro‑USB cable from the HAT’s **USB** jack (modem USB, not only the tiny UART jack) into the Pi.
2. Wait ~15–20s after power for the module to boot (NET LED blink).
3. On the Pi:

```bash
ls -l /dev/sim7600-at /dev/ttyUSB*
dmesg | grep -iE 'ttyUSB|1e0e|simcom|option'
```

You want several `/dev/ttyUSB*` and ideally `/dev/sim7600-at`.  
If those are missing, Digivice will say **SIM7600 not connected**.

## Checklist

1. **PWR–3V3** (not D6)  
2. **USB cable** Pi ↔ SIM7600 USB port  
3. Module powered (NET LED activity after boot)  
4. LTE **MAIN** antenna + **GNSS** antenna (GPS needs the GNSS IPEX)  
5. SIM seated (SMS/LTE; GNSS can work without SIM)  
6. `sudo digivice-full-update` once (udev rules for `1e0e`)  

## Software

- udev → `/dev/sim7600-at` (SimTech `1e0e`, AT interface)
- `sim7600.py` opens that port (or `ttyUSB2`-class)
- Settings → **Network** → Refresh shows port / CSQ / scan hints

RNDIS/NDIS cellular data is optional over the same USB link (ModemManager / Waveshare wiki).
