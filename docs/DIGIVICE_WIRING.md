# Digivice wiring sheet (Pi Zero 2 W)

Stack: **Pi → (optional tall header) → Waveshare 2″ on its SPI pins → passthrough** for buttons + CardKB.

**Buses (important):**

| Bus | Owner |
|-----|--------|
| **USB** | USB audio (headphones + mic). Optional **hub** also carries Heltec CDC. |
| **GPIO UART** `/dev/serial0` (pins **8 / 10**) | **SIM7600** AT only — `sudo digivice-modem-uart` |
| **Heltec notify** | USB-C `/dev/esp-bridge` (battery powered) — [`HELTEC_UART_NOTIFY.md`](HELTEC_UART_NOTIFY.md) |

Do **not** put the modem on USB if the audio stick needs that port. Do **not** put Heltec on GPIO UART while the modem owns `serial0`.

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

## 4. Steps tilt + passive piezo (Pi GPIO)

Heltec SW-520D path is gone. Wire a **tilt / vibration switch** (SW-520D or similar) and a **passive piezo** on free pins:

| Device | Pi pin | BCM | Wiring |
|--------|--------|-----|--------|
| **Steps** (SW-520D) | **11** | **17** | One leg → GPIO, other → **GND** (internal pull-up) |
| **Piezo** (passive) | **15** | **22** | **+** → GPIO (optional 100–220Ω series), **−** → **GND** |

- Steps: walk / shake closes the switch; Digivice counts edges while the UI is running.
- Piezo: software square-wave for alarms, timer, SMS/call chirps until USB speaker is sorted. Test: **Settings → Debug → Sound → PIEZO**.
  Header **pin 15** (BCM **22**). Do **not** use header pin 22 — that is LCD DC.
- Override pins: `DIGI_STEPS_BCM`, `DIGI_BUZZER_BCM` (set to `off` to disable).

Active buzzers (with onboard oscillator) will only click on/off — use a **passive** element for tones.

## 5. USB + UART roles

| Device | Link |
|--------|------|
| **USB audio** | Pi USB (or hub) — headphones + mic |
| **SIM7600G-H** | **GPIO UART** pins **8 / 10** → `/dev/serial0` ([`SIM7600_STACK.md`](SIM7600_STACK.md)) |
| **Heltec Tracker** | USB-C notify + battery % via hub ([`HELTEC_UART_NOTIFY.md`](HELTEC_UART_NOTIFY.md)); **LiPo powered** |

```
Pi USB ── hub ──┬── audio dongle
                └── Heltec USB-C (data)
SIM7600 ── UART ── Pi pins 8 (TX) / 10 (RX) / GND
```

## 6. Optional speaker amp

Green USB jack → headphones. External **PAM8403** or **MAX98357** + **inline switch** on amp power: [`MAX98357_SPEAKER.md`](MAX98357_SPEAKER.md).

## Full 40-pin map (passthrough view)

```
         3V3 ★LCD VCC     [1]  [2]  5V  · CardKB 5V
         SDA · CardKB     [3]  [4]  5V
         SCL · CardKB     [5]  [6]  GND · CardKB
         (free)           [7]  [8]  UART TX · SIM7600 RX  (BCM14)
         GND ★LCD         [9]  [10] UART RX · SIM7600 TX  (BCM15)
         STEPS BCM17     [11]  [12] ★LCD BL  (BCM18)
         ★LCD RST BCM27  [13]  [14] GND
         PIEZO BCM22     [15]  [16] (free)
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

★ = Waveshare LCD · · = CardKB / buttons on passthrough · STEPS / PIEZO = new Digivice extras

## Pin ownership

| Pins / bus | Owner |
|------------|--------|
| 1, 9, 12, 13, 19, 22, 23, 24 (+ BCM 8/10/11/18/25/27) | Waveshare 2″ |
| 2, 3, 5, 6 | CardKB |
| 11 (BCM17) | Steps tilt |
| 15 (BCM22) | Passive piezo |
| 8 / 10 (BCM 14 / 15) | SIM7600 UART |
| 29–36, 38, 40 (+ GND 34/39) | Buttons |
| USB | Audio dongle (+ Heltec on hub) |
| 27–28 ID EEPROM | Leave alone |
