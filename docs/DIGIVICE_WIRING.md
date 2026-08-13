# Digivice wiring sheet (Pi Zero 2 W)

Stack: **Pi → (optional tall header) → Waveshare 2″ on its SPI pins → passthrough** for buttons + CardKB.  
**SIM7600** and **Heltec** stay USB only.

LCD electrical map is the [Waveshare 2inch](https://www.waveshare.com/wiki/2inch_LCD_Module) Pi table — same whether you use jumpers or a GPIO/passthrough adapter.

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

Wire to the **top of the passthrough** (same pin numbers). Details: [`DIGI_BUTTONS.md`](DIGI_BUTTONS.md).

## 3. CardKB → passthrough (I2C)

| CardKB | Pi pin | BCM |
|--------|--------|-----|
| 5V | **2** | 5V |
| GND | **6** | GND |
| SDA | **3** | **2** |
| SCL | **5** | **3** |

Enable: `sudo systemctl enable --now cardkb-inputd` — [`CARDKB_PI.md`](CARDKB_PI.md).

## 4. USB only

| Device | Link |
|--------|------|
| SIM7600G-H | USB → Pi (modem USB) |
| Heltec Tracker | USB-C → Pi |

## Full 40-pin map (passthrough view)

```
         3V3 ★LCD VCC     [1]  [2]  5V  · CardKB 5V
         SDA · CardKB     [3]  [4]  5V
         SCL · CardKB     [5]  [6]  GND · CardKB
         (free)           [7]  [8]  (free)
         GND ★LCD         [9]  [10] (free)
         (free)          [11]  [12] ★LCD BL  (BCM18)
         ★LCD RST BCM27  [13]  [14] GND
         (free)          [15]  [16] (free)
         3V3             [17]  [18] (free)
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

★ = Waveshare LCD · · = CardKB / buttons on passthrough · (free) = unused

## Pin ownership

| Pins / bus | Owner |
|------------|--------|
| 1, 9, 12, 13, 19, 22, 23, 24 (+ BCM 8/10/11/18/25/27) | Waveshare 2″ |
| 2, 3, 5, 6 | CardKB |
| 29–36, 38, 40 (+ GND 34/39) | Buttons |
| USB | SIM7600 + Heltec |
| 27–28 ID EEPROM | Leave alone |
