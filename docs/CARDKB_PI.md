# M5Stack CardKB on Digivice (Pi)

Full QWERTY over **I2C**. Nav buttons stay on the hard pad / MCP ([`DIGI_BUTTONS.md`](DIGI_BUTTONS.md)).
Bluetooth / USB keyboards also type into Digivice text fields.

The Waveshare LCD is **SPI** — different bus. Do not confuse CardKB pads with LCD wiring.

## Two connectors on the CardKB board (do not mix them up)

| What | Where | Purpose | Wire to Pi? |
|------|--------|---------|-------------|
| **Grove / HY2.0-4P** (or the same four nets on a cable) | Side / cable | **Day-to-day Digivice typing** | **Yes** |
| **Six solder pads** along the bottom edge | PCB edge | **ISP only** — flash the onboard ATmega | **No** (not for Digivice) |

### Grove / cable — use this for Digivice

| Grove wire | Signal | Pi pin | BCM |
|------------|--------|--------|-----|
| **Red** | **5V** | **2** | 5V — **not 3.3V** |
| **Black** | **GND** | **6** | GND |
| **Yellow** | **SDA** | **3** | **2** (SDA1) |
| **White** | **SCL** | **5** | **3** (SCL1) |

I2C address **`0x5F`**. CardKB wants a solid **5V** rail (brownout → LED blinks, no keys).

Cables are fine (extension Grove, soldered pigtail to a protoboard header, etc.). You are still carrying these **four** signals — not one wire per key.

### Six bottom pads — ISP programming only

Left → right (keyboard oriented with pads along the bottom):

| 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|
| **VCC (5V)** | **RST** | **SCK** | **MISO** | **MOSI** | **GND** |

That row is the **ATmega ISP** header (firmware update with an external programmer). It is **SPI to the keyboard MCU**, not Digivice’s key bus.

**Do not** solder those six pads to the Pi SPI / LCD pins (MOSI/CLK/CS/etc.). That fights the Waveshare panel and does not make keys work.

Official pin map: [M5Stack CardKB v1.1](https://docs.m5stack.com/en/unit/cardkb_1.1).

## I2C1 is a shared bus

Pins **3 / 5** are **one** I2C bus with **many devices** (different addresses). Digivice already expects this:

| Device | Address (typical) |
|--------|-------------------|
| **CardKB** | **0x5F** |
| **MCP23017** (pad / vibe) | **0x20–0x27** |
| **UPS INA219** | **0x41** (sometimes **0x40**) |

Sharing SDA/SCL is normal. Keep `dtparam=i2c_arm_baudrate=50000` for CardKB clock-stretch; other chips on the same bus are fine at that speed.

What **not** to put on I2C1: Heltec notify (that uses soft-UART), or anything that is not an I2C device on those pins.

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
sudo i2cdetect -y 1          # expect 5f (+ 20/27 MCP, + 41 UPS when fitted)
```

`full-update` seeds `dtparam=i2c_arm_baudrate=50000` (Pi Zero / CardKB clock-stretch). **Reboot once** after that line is first added.

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
4. Confirm you used the **Grove four wires**, not the six ISP pads, for the Pi link
5. `sudo digivice-ensure-cardkb --doctor`
6. Digivice log should show: `[cardkb] in-process OK` — if you see `cannot open I2C`, add user to group `i2c` and reboot

See also: [`DIGIVICE_WIRING.md`](DIGIVICE_WIRING.md) (full pin map), [`PI4_MIGRATION.md`](PI4_MIGRATION.md) (UPS on same I2C).
