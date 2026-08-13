# Digivice wiring sheet (Pi Zero 2 W)

Physical GPIO: **2" LCD** + **8 hard buttons** + optional **CardKB**.  
**SIM7600** and **Heltec** are USB only.

## 1. Waveshare 2" LCD (SPI)

| LCD | Pi pin | BCM |
|-----|--------|-----|
| VCC | **1** | 3.3V |
| GND | **9** (or any GND) | GND |
| DIN | **19** | 10 MOSI |
| CLK | **23** | 11 SCLK |
| CS | **24** | 8 CE0 |
| DC | **22** | **25** |
| RST | **13** | **27** |
| BL | **12** | **18** |

LCD **3.3V only**. Notes: [`WAVESHARE_2INCH_LCD.md`](WAVESHARE_2INCH_LCD.md).

## 2. Hard buttons (7 or 8)

Each button: **GPIO ↔ switch ↔ GND**. Full map: [`DIGI_BUTTONS.md`](DIGI_BUTTONS.md).

| Button | Pi pin | BCM | Action |
|--------|--------|-----|--------|
| **Up** | **29** | **5** | Move ↑ |
| **Down** | **31** | **6** | Move ↓ |
| **Left** | **32** | **12** | Move ← |
| **Right** | **33** | **13** | Move → |
| **Confirm** | **36** | **16** | OK / A |
| **Back** | **35** | **19** | Cancel / B |
| **Home** | **38** | **20** | Home / Start |
| **Select** | **40** | **21** | Tab / Select (game) |
| Common GND | **34** or **39** | GND | Share with LCD GND |

## 3. CardKB (optional QWERTY)

| CardKB | Pi pin |
|--------|--------|
| 5V | **2** |
| GND | **6** |
| SDA | **3** (BCM 2) |
| SCL | **5** (BCM 3) |

Enable: `sudo systemctl enable --now cardkb-inputd`  
Details: [`CARDKB_PI.md`](CARDKB_PI.md).

## 4. USB only

| Device | Link | Path |
|--------|------|------|
| SIM7600G-H | USB → Pi | `/dev/sim7600-at` |
| Heltec Tracker | USB-C → Pi | `/dev/esp-bridge` |

SIM7600: jumper **PWR–3V3**, UART path **USB**.

## Pin ownership

| Resource | Owner |
|----------|--------|
| SPI0 + GPIO 25/27/18 | 2" LCD |
| GPIO 5, 6, 12, 13, 16, 19, 20, 21 | D-pad + Confirm/Back/Home/Select |
| GPIO 2, 3 (I2C1) | CardKB |
| USB | SIM7600 + Heltec |
