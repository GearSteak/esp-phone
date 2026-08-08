# SPI blank deep-dive (Waveshare 2″ / mipi-dbi)

## Short answers

### Why was it `SPI` before and `Unknown19-1` now?
Same LCD. **Kernel/KMS connector naming changed.**

| Era | Typical name |
|-----|----------------|
| Older tinydrm / fb stacks | `SPI-1` / `SPI-0` |
| Current **panel-mipi-dbi** DRM | `Unknown19-1` (type “Unknown”) |

`0mm x 0mm` is normal (no EDID physical size). It is **not** proof the panel works.

### What actually means “SPI is live”?
```text
Unknown19-1 connected 240x320+0+0 0mm x 0mm
#                      ^^^^^^^^^^^ active mode + position
```
Only `connected 0mm x 0mm` with **no** `240x320+…` = **no CRTC** = black glass. Digivice then only paints HDMI.

### Why pins “fine” but still black (software)?
Most common on this project after install thrash:

1. **Firmware not valid MIPI DBI** (wrong file / bad magic) → probe fail  
2. **Minimal init sequence** (sleep-out + display-on only) → black image  
3. **COLMOD `0x3A 0x55`** instead of **`0x05`** (RGB565) on ST7789 SPI  
4. **Kernel never got `/lib/firmware/waveshare2inch.bin`** (compatible name requires that file)  
5. Qt placed the UI on HDMI only (UI bug, separate from panel power)

Qt layout hacks **cannot** light a panel that never got a DRM mode.

---

## Dual-head: HDMI works, SPI black

Often the Pi only drives **one CRTC well** and HDMI keeps it. Prove it:

```bash
export DISPLAY=:0
echo desktop > ~/.esp-handset/session_mode
pkill -f handset_app 2>/dev/null

# Temporarily: HDMI OFF, red on SPI for 6s, then HDMI back
digivice-spi-prove
```

| Red on 2″? | Meaning |
|------------|---------|
| **Yes** | Dual-head starved SPI. Run Digivice as: **`handset-spi`** (SPI only, HDMI off) |
| **No** | Kernel/firmware — `sudo digivice-spi-doctor --fix && sudo reboot` |

SPI-only Digivice (what often worked when “SPI” was primary name):

```bash
handset-spi
# = ESP_HANDSET_SPI_ONLY=1 handset-phone
# Leave: handset-desktop  (restores HDMI)
```

```bash
cd ~/esp-phone && git pull
sudo bash pi_handset/install-handset.sh
# or only display:
sudo bash pi_handset/display/install-display.sh

# Rebuilds full ST7789 init, writes waveshare2inch.bin + panel.bin,
# rewrites mipi-dbi-spi block (32 MHz, write-only, DC25 RST27 BL18)

sudo reboot
```

After reboot:

```bash
export DISPLAY=:0
echo desktop > ~/.esp-handset/session_mode   # stay off kiosk while testing
digivice-spi-doctor
```

Read the report:

| Line | Meaning |
|------|---------|
| `magic=MIPI DBI` | firmware OK |
| `Bad magic` / `probe failed` in dmesg | reinstall firmware again |
| `modes=[240x320 …]` under drm | panel has a mode |
| `status=connected` + `modes=none` | probe incomplete / DT wrong |

```bash
digivice-spi-doctor --modes    # enable CRTC; always re-assert HDMI
xrandr | grep -E 'connected|240x'
```

When you see `240x320+…` on Unknown/SPI, **then**:

```bash
handset-session set-phone
handset-phone
```

---

## Wiring checklist (match software)

| LCD | BCM |
|-----|-----|
| VCC | 3V3 |
| GND | GND |
| DIN | 10 (MOSI) |
| CLK | 11 (SCLK) |
| CS  | 8 (CE0) |
| DC  | **25** |
| RST | **27** |
| BL  | **18** |

---

## Doctor flags

```bash
digivice-spi-doctor              # report
sudo digivice-spi-doctor --fix    # rewrite firmware + config → reboot
digivice-spi-doctor --modes      # xrandr enable (HDMI-safe)
```

Paste full doctor output if still black after reboot + `--modes`.
