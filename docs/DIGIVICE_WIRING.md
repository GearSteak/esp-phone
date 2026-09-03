# Digivice wiring sheet (Pi Zero 2 W)

Stack: **Pi → (optional tall header) → Waveshare 2″ SPI → passthrough** for buttons + CardKB.

## Bus ownership (power-safe Digivice)

Pi USB **polyfuse** trips if the modem or Heltec draw on that port. Keep USB for audio only.

| Bus | Owner | Notes |
|-----|--------|--------|
| **USB** | **USB audio** (headphones + mic) | Nothing else |
| **GPIO UART** pins **8 / 10** (`/dev/serial0`) | **SIM7600** | `sudo digivice-modem-uart` |
| **SPI** (LCD) | **Waveshare 2″** | MOSI/CLK/CS/DC/RST + BL — **not** I2C |
| **I2C** pins **3 / 5** | **Shared** CardKB + MCP + UPS | Addresses `0x5F` / `0x20–0x27` / `0x41` — Heltec stays off this bus |
| **Soft-UART** pins **16 / 18** (BCM 23 / 24) | **Heltec** notify + battery % | Heltec on **LiPo**; common **GND** only — [`HELTEC_UART_NOTIFY.md`](HELTEC_UART_NOTIFY.md) |

```
Pi USB ──────── audio dongle only
SIM7600 ─────── UART 8/10
I2C 3/5 ─────── CardKB Grove + MCP + UPS (shared; not CardKB ISP pads)
SPI ─────────── Waveshare 2″ LCD (separate from I2C)
Heltec LiPo ─── soft-UART 16/18 + GND  (no USB to Pi)
```

LCD electrical map: [Waveshare 2inch](https://www.waveshare.com/wiki/2inch_LCD_Module).

## 1. Waveshare 2″ LCD (claims these pins)

**3.3V only** (do not feed 5V into VCC).

| LCD | Pi pin | BCM | Notes |
|-----|--------|-----|--------|
| VCC | **1** | 3.3V | or pin 17 |
| GND | **9** | GND | any GND OK |
| DIN | **19** | **10** MOSI | |
| CLK | **23** | **11** SCLK | |
| CS | **24** | **8** CE0 | |
| DC | **22** | **25** | |
| RST | **13** | **27** | |
| BL | **12** | **18** | backlight |

Those eight pins are **owned by the LCD**. On a passthrough header, do not also bolt button wires onto 12 / 13 / 19 / 22 / 23 / 24 for other jobs.

## 2. Hard buttons → passthrough (GPIO ↔ switch ↔ GND)

| Button | Pi pin | BCM | Digivice / GB |
|--------|--------|-----|----------------|
| Up | **29** | **5** | ↑ / D-pad |
| Down | **31** | **6** | ↓ |
| Left | **32** | **12** | ← |
| Right | **33** | **13** | → |
| Confirm | **36** | **16** | OK / A |
| Back | **35** | **19** | Esc / B |
| Home | **38** | **20** | Home / Start |
| Select | **40** | **21** | Tab / Select |
| Common GND | **34** or **39** | GND | shared |

Details: [`DIGI_BUTTONS.md`](DIGI_BUTTONS.md).

## 3. CardKB → passthrough (I2C Grove / cable)

Use the **4-wire Grove** (or an equivalent cable). **Not** the six ISP pads on the bottom of the CardKB PCB — those are for ATmega firmware flash only.

| CardKB (Grove) | Pi pin | BCM |
|----------------|--------|-----|
| 5V | **2** | 5V |
| GND | **6** | GND |
| SDA | **3** | **2** |
| SCL | **5** | **3** |

Same I2C1 bus as **MCP23017** and **UPS INA219**. Full detail: [`CARDKB_PI.md`](CARDKB_PI.md).

## 4. Steps tilt + passive piezo (Pi GPIO)

| Device | Pi pin | BCM | Wiring |
|--------|--------|-----|--------|
| **Steps** (SW-520D) | **11** | **17** | One leg → GPIO, other → **GND** |
| **Piezo** (passive) | **15** | **22** | **+** → GPIO (optional 100–220Ω), **−** → **GND** |

Override: `DIGI_STEPS_BCM`, `DIGI_BUZZER_BCM`. Test piezo: **Settings → Debug → Sound → PIEZO**.

## 5. SIM7600 (GPIO UART only)

| Modem | Pi |
|-------|-----|
| RX | Pin **8** BCM14 TX |
| TX | Pin **10** BCM15 RX |
| GND | GND |
| PWR | 3V3 (not BCM6) |

[`SIM7600_STACK.md`](SIM7600_STACK.md) · `echo uart \| sudo tee /etc/esp-handset/modem-backend`

## 6. Heltec notify (soft-UART + LiPo)

| Heltec | Pi |
|--------|-----|
| RX GPIO44 | Pin **16** BCM23 TX |
| TX GPIO43 | Pin **18** BCM24 RX |
| GND | GND |
| Power | **LiPo** — flash over USB once, then unplug |

`sudo bash pi_handset/session/digivice-heltec-softuart.sh` · [`HELTEC_UART_NOTIFY.md`](HELTEC_UART_NOTIFY.md)

## 7. Optional speaker amp

Green USB jack → headphones. **PAM8403** / **MAX98357** + inline switch: [`MAX98357_SPEAKER.md`](MAX98357_SPEAKER.md).

## Full 40-pin map (passthrough view)

```
         3V3 ★LCD VCC     [1]  [2]  5V  · CardKB 5V
         SDA · CardKB     [3]  [4]  5V
         SCL · CardKB     [5]  [6]  GND · CardKB / Heltec
         (free)           [7]  [8]  UART TX · SIM7600 RX  (BCM14)
         GND ★LCD         [9]  [10] UART RX · SIM7600 TX  (BCM15)
         STEPS BCM17     [11]  [12] ★LCD BL  (BCM18)
         ★LCD RST BCM27  [13]  [14] GND
         PIEZO BCM22     [15]  [16] Heltec soft TX BCM23
         3V3             [17]  [18] Heltec soft RX BCM24
         ★LCD DIN MOSI   [19]  [20] GND
         (free)          [21]  [22] ★LCD DC  (BCM25)
         ★LCD CLK        [23]  [24] ★LCD CS  (BCM8)
         GND             [25]  [26] (free)
         ID_SD (leave)   [27]  [28] ID_SC (leave)
         UP BCM5         [29]  [30] GND
         DOWN BCM6       [31]  [32] LEFT BCM12
         RIGHT BCM13     [33]  [34] GND · buttons
         BACK BCM19      [35]  [36] CONFIRM BCM16
         (free)          [37]  [38] HOME BCM20
         GND             [39]  [40] SELECT BCM21
```

## Pin ownership

| Pins / bus | Owner |
|------------|--------|
| 1, 9, 12, 13, 19, 22, 23, 24 (+ BCM 8/10/11/18/25/27) | Waveshare 2″ |
| 2, 3, 5, 6 | I2C1 — CardKB Grove + MCP + UPS (shared) |
| 8 / 10 (BCM 14 / 15) | SIM7600 UART |
| 11 (BCM17) | Steps |
| 15 (BCM22) | Piezo |
| 16 / 18 (BCM 23 / 24) | Heltec soft-UART |
| 29–36, 38, 40 (+ GND 34/39) | Buttons |
| USB | Audio dongle only |
| 27–28 ID EEPROM | Leave alone |
