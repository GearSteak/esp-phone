# Digivice hard buttons (D-pad + Confirm / Back / Home / Select)

Eight tactile buttons (Select is optional). Each switch: one side on the listed GPIO, other to **GND**. Internal pull-ups — no VCC needed.

## What each button does

| Button | Digivice (phone) | Linux desktop | Game Boy (when emu on) |
|--------|------------------|---------------|-------------------------|
| **Up / Down / Left / Right** | Arrow keys | Mouse move | D-pad |
| **Confirm** | Enter | Left click | A |
| **Back** | Esc | Right click | B |
| **Home** | Home | Relaunch Digivice | Start |
| **Select** (8th) | Tab | Middle click | Select |

**Exit Game Boy (in-UI PyBoy or RetroArch):** hold **Confirm + Back + Home** (~0.5s).

Mode is `phone` while Digivice runs and `desktop` after `handset-desktop`.
In-UI PyBoy remaps the phone keys itself (Back→B, Home→Start) so you don’t need `gb` mode.

Typing: **CardKB** (I2C) or on-screen keyboard — see [`CARDKB_PI.md`](CARDKB_PI.md).

## Wiring (BCM → 40-pin)

Avoids LCD SPI (**8, 10, 11, 18, 25, 27**) and CardKB I2C (**2, 3**).

| Button | BCM GPIO | Board pin |
|--------|----------|-----------|
| **Up** | **5** | **29** |
| **Down** | **6** | **31** |
| **Left** | **12** | **32** |
| **Right** | **13** | **33** |
| **Confirm** | **16** | **36** |
| **Back** | **19** | **35** |
| **Home** | **20** | **38** |
| **Select** | **21** | **40** |
| **GND** (common) | GND | **34** or **39** (near that pin group) |

Suggested layout:

```
        [Up]
 [Left] [Confirm] [Right]
       [Down]
  [Back]  [Select]  [Home]
```

## Software

Service: **`digi-buttons-inputd`** — **enabled on boot**.

```bash
sudo digivice-ensure-buttons --doctor
journalctl -u digi-buttons-inputd -f
```

Optional pin override (unit `Environment=`):

```
DIGI_BTN_UP=5
DIGI_BTN_DOWN=6
DIGI_BTN_LEFT=12
DIGI_BTN_RIGHT=13
DIGI_BTN_CONFIRM=16
DIGI_BTN_BACK=19
DIGI_BTN_HOME=20
DIGI_BTN_SELECT=21
# DIGI_BTN_SELECT=off   # if you did not wire the 8th button
```
