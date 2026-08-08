# Digivice display — scale to all screens

## Pipeline

```
Digivice paints fixed 240×320
        │
        ├─► SPI fullscreen host  (scale whole UI into 240×320)
        └─► HDMI fullscreen host (scale whole UI into monitor)
```

- **Not** “fullscreen on HDMI then crop SPI.”
- **Not** requiring xrandr clone.
- Full UI on **both** displays.

Default: `ESP_HANDSET_DISPLAY=scale`

## Launch

```bash
export DISPLAY=:0
git pull && sudo bash pi_handset/install-handset.sh   # or copy esp_handset
handset-phone
```

Log:

```text
multi-screen: source 240x320, hosts=2
```
