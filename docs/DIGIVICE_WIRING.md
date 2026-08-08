# Digivice wiring sheet (Pi Zero 2 W)

Physical GPIO: **2" LCD** + **7 hard buttons**.  
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

## 2. Seven hard buttons

Each button: **GPIO ↔ switch ↔ GND**. Full map: [`DIGI_BUTTONS.md`](DIGI_BUTTONS.md).

| Button | Pi pin | BCM | Action |
|--------|--------|-----|--------|
| **Up** | **29** | **5** | Move ↑ |
| **Down** | **31** | **6** | Move ↓ |
| **Left** | **32** | **12** | Move ← |
| **Right** | **33** | **13** | Move → |
| **Confirm** | **36** | **16** | Select / OK |
| **Back** | **35** | **19** | Cancel / back |
| **Home** | **38** | **20** | Home screen |
| Common GND | **34** or **39** | GND | Share with LCD GND |

## 3. USB only

| Device | Link | Path |
|--------|------|------|
| SIM7600G-H | USB → Pi | `/dev/sim7600-at` |
| Heltec Tracker | USB-C → Pi | `/dev/esp-bridge` |

SIM7600: jumper **PWR–3V3**, UART path **USB**.

## 4. Heltec optional

| Extra | Wire |
|-------|------|
| SW-520D steps | Heltec **GPIO 7** + GND |

## Pin ownership

| Resource | Owner |
|----------|--------|
| SPI0 + GPIO 25/27/18 | 2" LCD |
| GPIO 5, 6, 12, 13, 16, 19, 20 | D-pad + Confirm/Back/Home |
| USB | SIM7600 + Heltec |
