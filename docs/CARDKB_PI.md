# M5Stack CardKB on Digivice (Pi)

Full QWERTY on I2C. Nav buttons stay on the hard pad ([`DIGI_BUTTONS.md`](DIGI_BUTTONS.md)).
Bluetooth / USB keyboards also type into Digivice text fields (OSK removed).

## Wiring (Pi 40-pin)

| CardKB | Pi pin | Notes |
|--------|--------|--------|
| **5V** (red) | **2** | 5V — not 3.3V |
| **GND** (black) | **6** | GND |
| **SDA** (yellow) | **3** | BCM **2** / SDA1 |
| **SCL** (white) | **5** | BCM **3** / SCL1 |

Same Grove colors as Heltec CardKB. Do **not** share these pins with anything else.
CardKB wants a solid **5V** rail (shared Pi 5V / power bus is fine; brownout → LED blinks, no keys).

## Enable on the Pi

`full-update` / `install-handset` enables `cardkb-inputd` by default and seeds
`dtparam=i2c_arm_baudrate=50000` (avoids Pi Zero I2C hang after the first key).

```bash
# I2C must be on
sudo raspi-config nonint do_i2c 0

# See the keyboard at 0x5F
sudo i2cdetect -y 1

sudo systemctl enable --now cardkb-inputd
journalctl -u cardkb-inputd -f
```

Service runs `cardkb_inputd.py` → uinput (`Digivice-CardKB`).

## Digivice use

- Confirm on a text field (or start typing) to focus it.
- Letters / digits / Enter / Backspace from CardKB or a paired Bluetooth keyboard.
- Arrow codes from CardKB also work for nav if you prefer keys over the pad.

To disable without unplugging: `sudo systemctl disable --now cardkb-inputd`.

## “LED blinks once, then dead”

Usually I2C wedged or under-voltage, not Digivice UI.

```bash
sudo i2cdetect -y 1          # still see 5f?
journalctl -u cardkb-inputd -n 40 --no-pager
sudo systemctl restart cardkb-inputd
# verbose one-shot test (Ctrl+C to stop):
sudo python3 /opt/esp-handset/cardkb_inputd.py -v
```

If `i2cdetect` loses `5f` after a key, power/wiring or baudrate — reboot after full-update so `i2c_arm_baudrate=50000` applies. Keep CardKB on **5V**, not 3.3V.
