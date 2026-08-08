# Pi Digivice handset

## Architecture

```
Pi Zero 2 W
  ├─ SPI ──► Waveshare 2" LCD 240×320 (ST7789) — main Digivice UI
  ├─ GPIO ─► 7 hard buttons (↑ ↓ ← → Confirm Back Home)
  ├─ USB ──► SIM7600G-H — LTE / SMS / GNSS
  └─ USB ──► Heltec Tracker — LoRa (+ optional steps / notify)
```

## Quick start

1. **Wire 2" panel** — [`docs/WAVESHARE_2INCH_LCD.md`](../docs/WAVESHARE_2INCH_LCD.md)  
2. **Wire buttons** — [`docs/DIGI_BUTTONS.md`](../docs/DIGI_BUTTONS.md)  
3. Flash Heltec (optional): `pio run -e heltec-wireless-tracker-gateway -t upload`  
4. On the Pi:
   ```bash
   cd pi_handset
   sudo ./install-handset.sh
   sudo reboot
   ```

### Dev without hardware

```bash
cd pi_handset
python3 esp_handset/handset_app.py
```

| Control | Action |
|---------|--------|
| Arrows | Move focus |
| Enter | Confirm |
| Esc | Back |
| Home | Digivice home |

## Roles

| Path | Purpose |
|------|---------|
| GPIO 5/6/12/13/16/19/20 | Hard buttons → `digi-buttons-inputd` |
| SPI DRM panel | Digivice fullscreen UI |
| `/dev/sim7600-at` | SIM7600 USB AT |
| `/dev/esp-bridge` | Heltec LoRa |
| Tools → AI | Ollama + small DeepSeek (optional) — [`docs/OLLAMA.md`](../docs/OLLAMA.md) |
