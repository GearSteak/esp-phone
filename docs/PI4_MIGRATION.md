# Digivice migration — Pi 4B 2GB + UPS Module 3S

Plan for moving off Pi Zero 2 W onto **Pi 4 Model B 2GB**, **Waveshare UPS Module 3S**, onboard headphone audio, and UPS pack telemetry in the status bar.

Hardware decisions locked in this plan:

| Item | Choice |
|------|--------|
| Pi | **4B 2GB** (not Pi 5 1GB / not Pi 3) |
| UPS | **Waveshare UPS Module 3S** (5 V 5 A) — same module as Pi 5 plan |
| Heltec power | UPS header **5 V + GND** |
| Heltec data | **Soft-UART** GPIO **16 / 18** (pigpio works on Pi 4) |
| Pi USB | **Free** (no USB audio dongle) |
| Audio out | Pi **3.5 mm** jack |
| Modem | **UART** pins **8 / 10** |
| CardKB | **I2C** pins **3 / 5** |
| Storage | **microSD** (larger A2 card); no Pi 5 NVMe HAT on Pi 4 |

See also: [`DIGIVICE_WIRING.md`](DIGIVICE_WIRING.md) (update after bench), [`HELTEC_UART_NOTIFY.md`](HELTEC_UART_NOTIFY.md).

---

## UPS I2C battery % — conflicts?

**No address conflict** with CardKB.

| Device | Bus | Address | Pi pins |
|--------|-----|---------|---------|
| **CardKB** | I2C1 | **0x5F** | Grove **5V/GND/SDA/SCL** → pins 2/6/3/5 — **not** the six ISP pads ([`CARDKB_PI.md`](CARDKB_PI.md)) |
| **MCP23017** | I2C1 | **0x20–0x27** | Same SDA/SCL |
| **UPS INA219** | I2C1 | **0x41** (sometimes **0x40**) | UPS SDA/SCL + **GND** → Pi 3/5/6 |

Share the bus: **SCL, SDA, GND only** from the UPS header to the Pi. **Do not** connect UPS header **5 V** to Pi GPIO pin 2/4 while the Pi is fed from the UPS Type-C cable (back-feed risk). See [Waveshare UPS Module 3S wiki](https://www.waveshare.com/wiki/UPS_Module_3S).

After wiring, verify:

```bash
sudo i2cdetect -y 1
# Expect: 5f (CardKB) and 41 (INA219) — not both missing
```

**Software coexistence:** CardKB polls I2C continuously; UPS reads are occasional (e.g. every 30 s). No bus ownership clash. Keep `dtparam=i2c_arm_baudrate=50000` for CardKB; INA219 reads still work at that speed.

**Status bar:** Today **`H78%`** = Heltec LiPo via soft-UART ([`shell.py`](../../pi_handset/esp_handset/shell.py)). Add **`78%`** (or **`P78%`**) for **UPS pack** from INA219 bus voltage (~9.0–12.6 V for 3S, calibrate on bench). Both can show at once.

**INA219 gives:** pack voltage, current, power — not a coulomb counter. “Percent” is **estimated** from voltage curve; fine for UI, not exact SOC.

---

## BOM (order list)

### Core (order now)

- Raspberry Pi **4 Model B 2GB**
- Waveshare **UPS Module 3S** (B0BQC2WNR8 class)
- **3× 18650** — match module holder (form factor / button vs flat-top per Waveshare manual)
- **12.6 V 2 A** charger (DC5521) for UPS — not a 5 V phone charger
- **microSD** — **128 GB+ A2** (GBA ROMs are small; 256 GB if you hoard everything)
- **Extra-tall GPIO stacking header** (measure after cooler if any)
- **Pi 4 CSI camera cable** (you have this)
- Optional: small heatsink or fan on Pi 4 (not Pi 5 Active Cooler)

### Reuse (already owned)

- Waveshare **2″ SPI LCD** + passthrough
- **CardKB**, **8 buttons**, steps, piezo
- **SIM7600** (UART)
- **Heltec Wireless Tracker**
- Camera module
- Dupont / Grove wiring

### Do not buy for Pi 4

- Freenove **Pi 5 NVMe** adapter (B0F2HS4TTG) — **Pi 5 only**
- Pi **5** Active Cooler
- USB **audio dongle** for daily use (headphone jack instead)

---

## Power wiring (target)

```
12.6V charger ──► UPS Module 3S ◄── 3× 18650 (3S)
                        │
          ┌─────────────┼─────────────┐
          │ Type-C 5V   │ header 5V   │ I2C: SCL, SDA, GND
          ▼             ▼             ▼
       Pi 4 USB-C    Heltec 5V     Pi pins 3, 5, 6
          │             GND           (NOT UPS 5V → Pi pin 2)
          │             │
          └──── GND ────┴── common ground
```

**Heltec data:** Pi pin **16** → Heltec **44**, Pi pin **18** ← Heltec **43**, GND.

---

## Migration phases

### Phase 0 — Before parts arrive

- [ ] Sketch **case envelope** (Pi 4 + UPS + cells ≈ 93 mm length on UPS axis + stack height for LCD)
- [ ] Plan **SD slot access** on Pi 4 underside (or removable shell bottom)
- [ ] Flash **Raspberry Pi OS (64-bit)** to microSD on PC (Imager); user **gear**, Trixie if that’s your track
- [ ] Clone / `git pull` `esp-phone` on dev machine; **do not** run full handset update on new Pi until bench order below

### Phase 1 — Bare Pi 4 (bench PSU or UPS, no case)

Use **temporary 5 V 3 A USB-C PSU** or UPS Type-C only.

1. Boot Pi 4 from microSD; SSH or keyboard/monitor once
2. `sudo raspi-config` → enable **I2C**, **SPI**, **UART** (serial login off if offered)
3. `git clone` / copy repo; **do not** enable full Digivice UI yet
4. Confirm: `uname -a`, `ls /dev/i2c-1`, `ls /dev/spidev0.0`

### Phase 2 — GPIO stack (no UPS I2C yet)

Order matches [`DIGIVICE_WIRING.md`](DIGIVICE_WIRING.md):

1. **SPI LCD** — panel lights, `handset-phone` or SPI doctor if needed
2. **Buttons** — `buttons_inputd` / Settings debug
3. **CardKB** — `i2cdetect` shows **5f**; typing in UI
4. **SIM7600 UART** — `sudo digivice-modem-uart`, `modem-backend=uart`, AT on `/dev/serial0`
5. **Heltec soft-UART** — runs on **full-update / apply-update** (`digivice-ensure-heltec`); flash gateway firmware; Heltec icon in bar when PING works
6. **Onboard audio** — `dtparam=audio=on`; test `speaker-test -D plughw:0,0` (card index may vary); plan **digivice-analog-audio** script (to add) instead of `digivice-audio-usb`
7. **CSI camera** — Pi 4 cable; photo + preview in Camera app

**Gate:** all buses stable before sealing in case.

### Phase 3 — UPS integration

1. Install **3 cells**; check **reverse-polarity LEDs**; press **BOOT** if no output ([wiki Note 2](https://www.waveshare.com/wiki/UPS_Module_3S))
2. Pi power: **UPS Type-C → Pi USB-C** only
3. Heltec: **UPS 5 V + GND** (header or pigtail)
4. I2C: **UPS SCL → Pi pin 5, SDA → pin 3, GND → pin 6**
5. `sudo i2cdetect -y 1` → **41** + **5f**
6. Download Waveshare demo / run `INA219.py` from [wiki](https://www.waveshare.com/wiki/UPS_Module_3S) — confirm voltage/current
7. Charge test: 12.6 V in → charging; unplug → Pi keeps running
8. Load test: camera + UI + modem idle — watch for brownouts/reboots

### Phase 4 — Case + cooling

- Mount **UPS + cells** (bottom layer typical); **air path** for Pi 4 + case fans
- **GPIO stack height** — measure with tall header + LCD + passthrough
- Antenna exits: SIM7600 LTE/GNSS, Heltec LoRa
- **12.6 V charge port**, UPS **switch**, optional **BOOT** access
- Headphone jack / speaker wire to 3.5 mm
- CardKB **Grove** cable through wall (4-wire I2C — not ISP pads)

### Phase 5 — Software on device

When hardware is stable:

```bash
cd ~/esp-phone && git pull
sudo bash pi_handset/session/digivice-modem-uart.sh      # if not done
sudo bash pi_handset/session/digivice-heltec-softuart.sh
sudo bash pi_handset/session/full-update.sh
# Reboot; then handset-phone
```

Post-migration doc updates:

- [`DIGIVICE_WIRING.md`](DIGIVICE_WIRING.md) — Pi 4, UPS power, headphone jack, UPS I2C
- [`HELTEC_UART_NOTIFY.md`](HELTEC_UART_NOTIFY.md) — UPS 5 V not LiPo
- New: onboard audio setup script + [`DIGIVICE_AUDIO.md`](DIGIVICE_AUDIO.md) Pi 4 section

---

## UPS battery % — software plan (repo work)

Implement after Phase 3 `i2cdetect` shows **0x41**.

### 1. `pi_handset/esp_handset/ups_monitor.py` (new)

- Read INA219 on `i2c-1` @ `0x41` via `smbus2` (already used by CardKB code)
- Return: `bus_voltage_v`, `current_ma`, `power_mw`, `percent` (clamp 9.0–12.6 V or calibrate), `charging` (current &lt; threshold per Waveshare demos)
- Handle missing hardware gracefully (no crash if UPS I2C unplugged)

### 2. Poll from `handset_app.py`

- Timer ~30 s (same as Heltec battery)
- Call `shell.set_pi_battery(percent, charging=...)`

### 3. `shell.py` status bar

- Add label for **pack %** (e.g. `82%` with tooltip “UPS pack”)
- Keep **`Hxx%`** for Heltec when bridge connected
- Layout: `[pack%] [H%?] wifi cell`

### 4. Session helper (optional)

- `digivice-ups-i2c.sh` — ensure `dtparam=i2c_arm=on`, `i2c-dev` module, document UPS wires (no env vars required if address fixed)

### 5. Bench calibration

- Log voltage at “full” after charge and “empty” before cutoff; adjust empty/full constants in `ups_monitor.py` if 9.0/12.6 V is off for your cells.

**Dependencies:** `python3-smbus` / `smbus2` — already in handset install path.

---

## Risk checklist (why Zeros died — avoid repeat)

- [ ] **Never** modem or Heltec on Pi **USB** for runtime power
- [ ] **Never** Heltec on **3S BAT** terminals — **5 V only**
- [ ] **Never** UPS header 5 V → Pi GPIO 5 V while Type-C powers Pi
- [ ] **Common GND** everywhere before UART data wires
- [ ] SIM7600 **PWR → 3V3**, not BCM6 (Down button)
- [ ] CardKB **5 V** from Pi pin 2 — acceptable; total 5 A from UPS covers it

---

## Quick reference — bus ownership (Pi 4 target)

| Bus | Owner |
|-----|--------|
| UPS Type-C | Pi 4 power |
| UPS header 5 V | Heltec |
| I2C 3/5 | CardKB **+** UPS INA219 |
| UART 8/10 | SIM7600 |
| GPIO 16/18 | Heltec soft-UART |
| 3.5 mm jack | Audio out |
| USB | Empty (or debug only) |

---

## Emulator expansion (Pi 4B 2GB)

**Scope (locked):** 8/16-bit in-UI emulators + **GBA** (`mgba`). **No PS1, N64, or SNES** — not enough face/shoulder buttons without case bloat.

| System | Pi 4B 2GB | In UI today? |
|--------|-----------|--------------|
| GB / GBC | Excellent | Yes |
| NES | Excellent | Yes |
| SMS / GG | Excellent | Yes |
| **GBA** | Excellent | **Add** — needs **L/R** |
| Genesis | Excellent | Optional later (`genesis_plus_gx` already installed) |
| PS1 / N64 / SNES | — | **Out of scope** |

The **2″ LCD** (240×320) keeps load modest. **2 GB RAM** is fine for one emulator at a time.

### Shoulder buttons — **L + R only** (GBA)

GBA uses **L/R** for many titles; **no L2/R2** needed.

**GPIO budget:** only **2 pins** required — plenty of room on the passthrough.

| Button | BCM | Pin | Notes |
|--------|-----|-----|--------|
| **L** | **4** | **7** | Free today |
| **R** | **26** | **37** | Free today |

Still available if needed later: BCM **7** (pin 26), BCM **9** (pin 21, SPI MISO — use only if necessary).

Wire like other pad buttons: GPIO ↔ switch ↔ **GND**, internal pull-up.

**Software (repo — after case wired):**

- [`buttons_inputd.py`](../../pi_handset/esp_handset/buttons_inputd.py) — `DIGI_BTN_L`, `DIGI_BTN_R` (or fixed BCM 4 / 26)
- [`emu_ui.py`](../../pi_handset/esp_handset/emu_ui.py) / [`libretro_host.py`](../../pi_handset/esp_handset/libretro_host.py) — map L/R to libretro `l` / `r`
- [`DIGI_BUTTONS.md`](DIGI_BUTTONS.md) + [`DIGIVICE_WIRING.md`](DIGIVICE_WIRING.md) — document new pins

Existing pad mapping unchanged: Confirm=A, Back=B, Home=Start, Select=Select.

### Repo today vs target

**In-UI today:** GB, NES, SMS/GG ([`emu_ui.py`](../../pi_handset/esp_handset/emu_ui.py)).

**Cores installed today:** `gambatte`, `fceumm`, `nestopia`, `genesis_plus_gx` ([`ensure-libretro-cores.sh`](../../pi_handset/session/ensure-libretro-cores.sh)).

**Target add:**

| System | Core | ROM folder | Extensions |
|--------|------|------------|------------|
| **GBA** | `mgba` | `roms/gba` | `.gba` |

### Storage (ROMs)

```
~/.esp-handset/roms/
  gb/  nes/  sms/  gba/
```

### Software tasks (repo — after Phase 5 boot)

1. **`ensure-libretro-cores.sh`** — add `mgba` to `NEED_CORES`.
2. **`emu_ui.py`** — `EmuSystem` entry for GBA (240×160 native).
3. **`libretro_host.py`** — `mgba` entries in `_SPEED_VARS` (already partially present).
4. **L/R** in `buttons_inputd` + libretro joypad mapping.

### Phase 6 — Emulators (after handset stable)

- [ ] Wire **L** / **R** on BCM **4** / **26**
- [ ] `sudo digivice-libretro-cores` — confirm `mgba_libretro.so`
- [ ] Test GBA ROM + L/R in a game that uses shoulders
- [ ] Audio via **3.5 mm** jack
- [ ] Exit combo: Confirm+Back+Home ([`emu_ui.py`](../../pi_handset/esp_handset/emu_ui.py))

---

## Deferred / out of scope for first boot

- NVMe / USB SSD boot
- MAX98357 speaker (GPIO conflicts — see [`MAX98357_SPEAKER.md`](MAX98357_SPEAKER.md))
- Ollama / heavy local LLM on 2 GB
- PS1 / N64 / SNES emulation
- Genesis UI entry (core already on disk)
- Doc commit for `.cursor/rules` unless you want it in repo
