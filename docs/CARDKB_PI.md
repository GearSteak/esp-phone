# M5Stack CardKB on Digivice (Pi)

Optional full QWERTY on I2C. Nav buttons stay on the hard pad ([`DIGI_BUTTONS.md`](DIGI_BUTTONS.md)).

## Wiring (Pi 40-pin)

| CardKB | Pi pin | Notes |
|--------|--------|--------|
| **5V** (red) | **2** | 5V |
| **GND** (black) | **6** | GND |
| **SDA** (yellow) | **3** | BCM **2** / SDA1 |
| **SCL** (white) | **5** | BCM **3** / SCL1 |

Same Grove colors as Heltec CardKB. Do **not** share these pins with anything else.

## Enable on the Pi

```bash
# I2C must be on
sudo raspi-config nonint do_i2c 0
# or: enable I2C in raspi-config → Interface Options

# See the keyboard at 0x5F
sudo i2cdetect -y 1

sudo systemctl enable --now cardkb-inputd
journalctl -u cardkb-inputd -f
```

Service runs `cardkb_inputd.py` → uinput (`Digivice-CardKB`).

## Digivice use

- Letters / digits / Enter / Backspace for SMS, notes, search, etc.
- Arrow codes from CardKB also work for nav if you prefer keys over the pad.

Leave `cardkb-inputd` **disabled** if CardKB is not plugged in (avoids I2C retry spam).
