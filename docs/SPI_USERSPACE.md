# SPI path: Instructables-style userspace mirror

When DRM dual-head (`mipi-dbi-spi` + HDMI) leaves the 2″ black, use the model from  
[How to Mirror the Desktop of RPI OS on Any ST7789 SPI Display](https://www.instructables.com/How-to-Mirror-the-Desktop-of-RPI-OS-on-Any-St7789-/):

**Drive ST7789 over SPI from userspace; mirror the Digivice UI** (not a 1080p crop).

| Layer | Role |
|-------|------|
| HDMI | Digivice fullscreen (works) |
| SPI0 + GPIO DC/RST/BL | ST7789 userspace (`st7789_spi.py`) pushes RGB565 frames |
| Digivice | Grabs its window every ~50 ms → SPI |

This is the same *idea* as **fbcp** (copy framebuffer → ST7789), but we mirror the **phone app**, not the whole desktop.

## One-time switch (recommended)

```bash
cd ~/esp-phone && git pull
sudo bash pi_handset/display/install-spi-userspace.sh
sudo reboot
```

That:

1. **Removes** `dtoverlay=mipi-dbi-spi` (DRM no longer owns SPI; no `Unknown19-1` ghost)  
2. Keeps `dtparam=spi=on` → `/dev/spidev0.0`  
3. Installs `python3-spidev` + GPIO Python  
4. Sets `ESP_HANDSET_SPI_BACKEND=userspace`

After reboot:

```bash
ls -l /dev/spidev0.0          # must exist
export DISPLAY=:0
handset-phone
```

You should see a **red flash** on the 2″, then Digivice. HDMI still shows Digivice.

## Wiring (unchanged)

VCC 3V3 · GND · DIN 10 · CLK 11 · CS 8 · **DC 25 · RST 27 · BL 18**

## Back to DRM panel (not recommended until dual-head works)

```bash
sudo bash pi_handset/display/install-display.sh   # rewrites mipi-dbi block
sudo rm -f /etc/esp-handset/spi-userspace
sudo reboot
```

## Why DRM dual failed for us

`Unknown19-1 connected 0mm x 0mm` without an active mode means **no CRTC** for SPI while HDMI was happy. Renaming SPI→Unknown is KMS, not a different cable. Userspace SPI avoids that path entirely.
