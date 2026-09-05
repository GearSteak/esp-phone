# Digivice paper carts (license / e-Reader style)

Paper cards **unlock local ROMs** and act like a single virtual cartridge insert.
USB carts ([`USB_CARTRIDGE.md`](USB_CARTRIDGE.md)) stay for movies / big media on the case USB port.

## Flow

1. ROM lives under `~/.esp-handset/roms/…` and is listed in the paper-cart **catalog**
2. That ROM is **hidden** in the normal emulator shelf until its card is inserted
3. **Games → Paper Cart** → scan QR (or type the code) → card is **inserted**
4. Status bar shows a **yellow** cart name; **Apps** opens the cart game menu (same as USB games carts)
5. **Eject** before scanning a different card
6. Unplug USB movie carts separately — paper and USB can coexist (USB games cart wins Apps takeover if both want games)

## Demo card (print this)

Printable PNG (trading-card size @ ~300 DPI):

[`docs/assets/digivice_demo_paper_cart.png`](assets/digivice_demo_paper_cart.png)

Regenerate:

```bash
pip install qrcode pillow
python tools/make_license_card.py
```

Demo payload (also printed under the QR):

```text
DIGIVICE-CARD:1:demo-hello:<10-hex-tag>
```

On Digivice without a camera / zbar: open **Paper Cart**, leave the field empty, Confirm **Scan / Insert** — it fills the demo payload automatically the first time, or paste the printed line.

### Play the demo ROM

```bash
# On the Pi — copy any Game Boy ROM to the catalog path:
mkdir -p ~/.esp-handset/roms/gb
cp /path/to/your.gb ~/.esp-handset/roms/gb/demo_hello.gb
```

Until that file exists, insert still works; launch shows **ROM missing**.

## QR decode deps (optional, for camera scan)

```bash
sudo apt install -y libzbar0
sudo pip3 install --break-system-packages pyzbar pillow
# or: python3-opencv (uses cv2.QRCodeDetector)
```

## Catalog

First run creates `~/.esp-handset/license_cards/catalog.json` with the demo card.

Add your own:

```json
{
  "version": 1,
  "cards": [
    {
      "id": "demo-hello",
      "title": "Hello Digivice",
      "secret": "digivice-demo-secret",
      "games": [
        {
          "title": "Demo Hello",
          "system": "gb",
          "path": "roms/gb/demo_hello.gb"
        }
      ]
    },
    {
      "id": "my-gold",
      "title": "Gold Key",
      "secret": "pick-a-long-secret",
      "games": [
        {
          "title": "Pokemon Gold",
          "system": "gb",
          "path": "roms/gb/pokemon_gold.gbc"
        }
      ]
    }
  ]
}
```

Payload format:

```text
DIGIVICE-CARD:1:<card-id>
DIGIVICE-CARD:1:<card-id>:<sha256(secret:id)[:10]>
```

If `secret` is set, the tag is required (stops casual forged QRs). This is **fun gating**, not strong DRM — the ROM file is still on disk.

State files:

| File | Meaning |
|------|---------|
| `license_cards/active.json` | Currently inserted paper cart |
| `license_cards/owned.json` | Cards scanned at least once |
| `license_cards/catalog.json` | What each card unlocks |

## USB vs paper

| | USB cart | Paper cart |
|--|----------|------------|
| Insert | Plug into case USB | Scan QR |
| Eject | Unplug / unmount | **Paper Cart → Eject** |
| Best for | Movies, TV, music, fat ROM packs | Unlock one local title |
| Status bar | Green name | Yellow name |
