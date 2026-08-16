# M5Stack CardKB on Digivice (Pi)

Full QWERTY on I2C. Nav buttons stay on the hard pad ([`DIGI_BUTTONS.md`](DIGI_BUTTONS.md)).
Bluetooth / USB keyboards also type into Digivice text fields.

## Wiring (Pi 40-pin)

| CardKB | Pi pin | Notes |
|--------|--------|--------|
| **5V** (red) | **2** | 5V — **not 3.3V** |
| **GND** (black) | **6** | GND |
| **SDA** (yellow) | **3** | BCM **2** / SDA1 |
| **SCL** (white) | **5** | BCM **3** / SCL1 |

Same Grove colors as the old Heltec path. Do **not** share these pins with anything else.
CardKB wants a solid **5V** rail (brownout → LED blinks, no keys).

## Enable / fix on the Pi

```bash
cd ~/esp-phone && git pull && sudo digivice-full-update

# Or just the CardKB stack:
sudo digivice-ensure-cardkb
sudo digivice-ensure-cardkb --doctor
```

Doctor checks: `i2cdetect` for **`5f`**, service journal, baudrate, packages.

```bash
sudo raspi-config nonint do_i2c 0
sudo i2cdetect -y 1          # must show 5f
sudo systemctl status cardkb-inputd
journalctl -u cardkb-inputd -f
# live key log:
sudo python3 /opt/esp-handset/cardkb_inputd.py -v
```

`full-update` seeds `dtparam=i2c_arm_baudrate=50000` (Pi Zero clock-stretch). **Reboot once** after that line is first added.

## How keys reach Digivice

`cardkb-inputd` injects via **xdotool** into the Digivice X session (same path as hard buttons).
Confirm on a text field (or start typing) so focus lands in the field.

## “LED blinks once, then dead”

Usually I2C wedged or under-voltage — not Digivice UI.

1. `sudo i2cdetect -y 1` — is `5f` still there after a key?
2. If it vanished: power/wiring or baudrate → reboot with `i2c_arm_baudrate=50000`
3. Keep CardKB on **5V**, not 3.3V
4. `sudo digivice-ensure-cardkb --doctor`
