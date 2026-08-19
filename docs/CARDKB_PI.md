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
cd ~/esp-phone && git pull && sudo bash pi_handset/session/full-update.sh

# Doctor (I2C + uinput + pause file):
sudo digivice-ensure-cardkb --doctor
sudo usermod -aG i2c "$USER"   # needed for Digivice in-process reader
# then reboot once if group was just added, or after the first CardKB unit change
```

Doctor checks: `i2cdetect` for **`5f`**, `type socket OK`, pause file **absent** on the Linux desktop.

```bash
sudo raspi-config nonint do_i2c 0
sudo i2cdetect -y 1          # must show 5f
```

`full-update` seeds `dtparam=i2c_arm_baudrate=50000` (Pi Zero clock-stretch). **Reboot once** after that line is first added.

## How keys reach Digivice vs Linux desktop

`cardkb-inputd` reads I2C. **Digivice** uses the in-process reader (`cardkb_qt.py`) and writes `/run/digivice/cardkb.pause` so the daemon releases I2C.

**Settings → Linux** removes the pause file. The daemon then types by sending keys through **Digivice-Buttons** (`/run/digivice/type.sock`) — the pad keyboard labwc already has from boot. It does **not** create a second virtual keyboard (that used to steal Bluetooth / USB keyboards).

Confirm on a Digivice text field (yellow ring + “Typing · Back exits”), then type. **Back** leaves the field.

After this update: `full-update` then **reboot once** so Digivice-Buttons is created with letter keys. Bluetooth keyboards should keep working.

Doctor should show `type socket OK` and **no** `Digivice-CardKB` fallback device.

## “LED blinks once, then dead”

Usually I2C wedged or under-voltage — not Digivice UI.

1. `sudo i2cdetect -y 1` — is `5f` still there after a key?
2. If it vanished: power/wiring or baudrate → reboot with `i2c_arm_baudrate=50000`
3. Keep CardKB on **5V**, not 3.3V
4. `sudo digivice-ensure-cardkb --doctor`
5. Digivice log should show: `[cardkb] in-process OK` — if you see `cannot open I2C`, add user to group `i2c` and reboot
