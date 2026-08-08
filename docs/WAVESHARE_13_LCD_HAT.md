# Waveshare 1.3inch LCD HAT (legacy)

**Superseded** by the [2inch LCD Module 240×320](WAVESHARE_2INCH_LCD.md) + [CardKB on Pi](CARDKB_PI.md).

Kept only if you still have the 1.3" stick HAT (`docs` + `pi_handset/display/waveshare13hat.*`, optional `hat-inputd`).

Wiki: https://www.waveshare.com/wiki/1.3inch_LCD_HAT

To re-enable the stick HAT instead of the 2":

1. Point `install-display.sh` back at `waveshare13hat` / 240×240 GPIO set  
2. `sudo systemctl enable --now hat-inputd`  
3. Set UI geometry `ESP_HANDSET_W=240 ESP_HANDSET_H=240` if needed  

Default Digivice path is the **2"** panel.
