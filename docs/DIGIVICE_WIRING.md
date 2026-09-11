# Digivice wiring sheet — Pi 4B single board

Target stack: **Pi 4B 2GB → (tall header) → Waveshare 2″ SPI → passthrough / single protoboard**  
Power: **Waveshare UPS Module 3S** → Pi USB-C. Plan: [`PI4_MIGRATION.md`](PI4_MIGRATION.md).

LCD electrical map: [Waveshare 2inch](https://www.waveshare.com/wiki/2inch_LCD_Module).  
Firmware defaults: [`st7789_spi.py`](../pi_handset/esp_handset/st7789_spi.py) — MOSI=10 SCLK=11 CE0=8 DC=25 RST=27 BL=18.

---

## Focus: Waveshare 2″ LCD (SPI) — do this first

**3.3 V only** on LCD **VCC** (never 5 V).

| LCD pad | Pi physical pin | BCM | Net |
|---------|-----------------|-----|-----|
| **VCC** | **1** | 3V3 | Power (pin **17** also OK) |
| **GND** | **9** | GND | Any GND OK |
| **DIN** | **19** | **10** | SPI0 MOSI |
| **CLK** | **23** | **11** | SPI0 SCLK |
| **CS** | **24** | **8** | SPI0 CE0 |
| **DC** | **22** | **25** | Data / command |
| **RST** | **13** | **27** | Reset |
| **BL** | **12** | **18** | Backlight |

Those **eight pins are owned by the LCD**. On the single board / passthrough, do **not** also assign buttons or other jobs to pins **12, 13, 19, 22, 23, 24**.

```
Waveshare 2″          Pi 4 40-pin
───────────          ────────────
VCC  ─────────────── 1  (3V3)
GND  ─────────────── 9  (GND)
DIN  ─────────────── 19 (BCM10 MOSI)
CLK  ─────────────── 23 (BCM11 SCLK)
CS   ─────────────── 24 (BCM8  CE0)
DC   ─────────────── 22 (BCM25)
RST  ─────────────── 13 (BCM27)
BL   ─────────────── 12 (BCM18)
```

**Bench check:** `ls /dev/spidev0.0` → panel lights → Digivice UI on SPI.

**Note:** BCM **18** (BL) is also Pi hardware I2S BCLK. Keep BL here for now; moving BL is only required if you add MAX98357 later ([`MAX98357_SPEAKER.md`](MAX98357_SPEAKER.md)).

---

## Bus ownership (Pi 4 target)

| Bus | Owner | Notes |
|-----|--------|--------|
| **UPS Type-C** | Pi 4 power | 5 V into Pi USB-C only |
| **UPS header 5 V** | **Heltec** | Not into Pi pin 2/4 while Type-C powers Pi |
| **USB** | Free / carts / debug | **No** USB audio dongle (use **3.5 mm**) |
| **SPI** | **Waveshare 2″** | Table above |
| **I2C** pins **3 / 5** | **Shared** CardKB + MCP + UPS INA219 | `0x5F` / `0x20–0x27` / `0x41` |
| **UART** pins **8 / 10** | **SIM7600** | `/dev/serial0` |
| **Soft-UART** pins **16 / 18** | **Heltec** | BCM **23 / 24** |
| **3.5 mm jack** | Audio out | `dtparam=audio=on` |

```
UPS Type-C ──────── Pi 4 USB-C
UPS header 5V ───── Heltec Vsys (+ GND)
SPI ─────────────── Waveshare 2″ LCD
I2C 3/5 ─────────── CardKB Grove + MCP + UPS INA219 (shared)
UART 8/10 ───────── SIM7600
GPIO 16/18 ──────── Heltec soft-UART (+ common GND)
3.5 mm ──────────── headphones / amp line-in
USB ─────────────── empty or cartridge (not modem / not Heltec power)
```

---

## 2. Hard buttons (GPIO ↔ switch ↔ GND)

| Button | Pi pin | BCM | Digivice / GB |
|--------|--------|-----|----------------|
| Up | **29** | **5** | ↑ |
| Down | **31** | **6** | ↓ |
| Left | **32** | **12** | ← |
| Right | **33** | **13** | → |
| Confirm | **36** | **16** | OK / A |
| Back | **35** | **19** | Esc / B |
| Home | **38** | **20** | Home / Start |
| Select | **40** | **21** | Tab / Select |
| **L** (GBA) | **7** | **4** | Shoulder L — Pi 4 add |
| **R** (GBA) | **37** | **26** | Shoulder R — Pi 4 add |
| Common GND | **34** or **39** | GND | shared |

Details: [`DIGI_BUTTONS.md`](DIGI_BUTTONS.md). L/R software: [`PI4_MIGRATION.md`](PI4_MIGRATION.md).

---

## 3. CardKB (Grove I2C — not ISP pads)

| CardKB Grove | Pi pin | BCM |
|--------------|--------|-----|
| 5V | **2** | 5V |
| GND | **6** | GND |
| SDA | **3** | **2** |
| SCL | **5** | **3** |

[`CARDKB_PI.md`](CARDKB_PI.md).

---

## 4. UPS Module 3S (I2C telemetry only on GPIO)

| UPS header | Pi |
|------------|-----|
| SCL | Pin **5** (BCM3) |
| SDA | Pin **3** (BCM2) |
| GND | Pin **6** |
| **5 V** | **Heltec only** — do **not** feed Pi pin 2/4 |

Expect `i2cdetect -y 1` → **41** (INA219) + **5f** (CardKB).

---

## 5. Steps + piezo

| Device | Pi pin | BCM |
|--------|--------|-----|
| Steps (SW-520D) | **11** | **17** |
| Piezo (passive) | **15** | **22** |

Overrides: `DIGI_STEPS_BCM`, `DIGI_BUZZER_BCM`.

---

## 6. SIM7600 (GPIO UART)

| Modem | Pi |
|-------|-----|
| RX | Pin **8** BCM14 TX |
| TX | Pin **10** BCM15 RX |
| GND | GND |
| PWR | **3V3** (not BCM6) |

---

## 7. Heltec soft-UART

| Heltec | Pi |
|--------|-----|
| RX (GPIO44) | Pin **16** BCM23 TX |
| TX (GPIO43) | Pin **18** BCM24 RX |
| GND | GND |
| Power | **UPS header 5 V** (Pi 4 target) — flash USB once, then unplug USB |

[`HELTEC_UART_NOTIFY.md`](HELTEC_UART_NOTIFY.md).

---

## Full 40-pin map (Pi 4 / single board)

`★` = LCD. Do not double-assign those.

```
         3V3 ★LCD VCC      [1]  [2]  5V · CardKB 5V
         SDA · I2C1        [3]  [4]  5V
         SCL · I2C1        [5]  [6]  GND · CardKB / UPS I2C / Heltec
         L BCM4            [7]  [8]  UART TX · SIM7600 RX  (BCM14)
         GND ★LCD          [9]  [10] UART RX · SIM7600 TX  (BCM15)
         STEPS BCM17      [11]  [12] ★LCD BL  (BCM18)
         ★LCD RST BCM27   [13]  [14] GND
         PIEZO BCM22      [15]  [16] Heltec soft TX BCM23
         3V3              [17]  [18] Heltec soft RX BCM24
         ★LCD DIN MOSI    [19]  [20] GND
         (free)           [21]  [22] ★LCD DC  (BCM25)
         ★LCD CLK         [23]  [24] ★LCD CS  (BCM8)
         GND              [25]  [26] (free)
         ID_SD (leave)    [27]  [28] ID_SC (leave)
         UP BCM5          [29]  [30] GND
         DOWN BCM6        [31]  [32] LEFT BCM12
         RIGHT BCM13      [33]  [34] GND · buttons
         BACK BCM19       [35]  [36] CONFIRM BCM16
         R BCM26          [37]  [38] HOME BCM20
         GND              [39]  [40] SELECT BCM21
```

I2C1 on **3 / 5**: CardKB Grove **+** MCP23017 **+** UPS INA219.

---

## Pin ownership summary

| Pins / bus | Owner |
|------------|--------|
| **1, 9, 12, 13, 19, 22, 23, 24** (BCM **8 / 10 / 11 / 18 / 25 / 27**) | **Waveshare 2″ LCD** |
| 2, 3, 5, 6 | I2C1 — CardKB + MCP + UPS |
| 7 / 37 (BCM 4 / 26) | L / R shoulders |
| 8 / 10 (BCM 14 / 15) | SIM7600 UART |
| 11 (BCM17) | Steps |
| 15 (BCM22) | Piezo |
| 16 / 18 (BCM 23 / 24) | Heltec soft-UART |
| 29–36, 38, 40 (+ GND 34/39) | D-pad + face buttons |
| 21, 26 | Free |
| 27–28 ID EEPROM | Leave alone |
| USB | Free / cartridge (not modem power) |
| 3.5 mm | Audio |

---

## Changed vs old Pi Zero sheet

| Item | Zero (old) | Pi 4 single board |
|------|------------|-------------------|
| LCD SPI pins | Same ★ set | **Same** (no remap) |
| Audio | USB dongle | **3.5 mm** |
| Heltec power | LiPo | **UPS 5 V header** |
| UPS I2C | Optional | **On 3/5/6** |
| L / R | — | **Pins 7 / 37** |
