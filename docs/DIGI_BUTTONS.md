# Digivice hard buttons (D-pad + Confirm / Back / Home)

Seven tactile buttons instead of CardKB or a T9 pad. Each switch: one side on the listed GPIO, other to **GND**. Internal pull-ups — no VCC needed.

## What each button does

| Button | Digivice (phone) | Linux desktop |
|--------|------------------|---------------|
| **Up / Down / Left / Right** | Arrow keys | Mouse move |
| **Confirm** | Enter | Left click |
| **Back** | Esc | Right click |
| **Home** | Home | Super (start menu) |

Mode is `phone` while Digivice runs and `desktop` after `handset-desktop`.
Buttons read `/etc/esp-handset/ui_mode` and `~/.esp-handset/session_mode`.

Typing is still OSK (on-screen) or future dial pad — these seven only navigate the UI.

## Wiring (BCM → 40-pin)

Avoids LCD SPI (**8, 10, 11, 18, 25, 27**).

| Button | BCM GPIO | Board pin |
|--------|----------|-----------|
| **Up** | **5** | **29** |
| **Down** | **6** | **31** |
| **Left** | **12** | **32** |
| **Right** | **13** | **33** |
| **Confirm** | **16** | **36** |
| **Back** | **19** | **35** |
| **Home** | **20** | **38** |
| **GND** (common) | GND | **34** or **39** (near that pin group) |

Suggested layout on the case (under the screen or side thumb):

```
        [Up]
 [Left] [Confirm] [Right]
       [Down]
  [Back]      [Home]
```

Or classic d-pad with Confirm in center and Back/Home as side keys.

## Software

Service: **`digi-buttons-inputd`** — **enabled on boot**.  
Injects keys via **uinput + xdotool** so Digivice (X11) actually receives them.

```bash
# Full fix + diagnose (run on the Pi)
sudo digivice-ensure-buttons --doctor

# Watch presses (must print PRESS … when you mash a wire to GND)
journalctl -u digi-buttons-inputd -f
```

| Doctor result | Meaning |
|---------------|---------|
| `PRESS UP` in journal | Wiring + daemon OK → GUI path |
| No PRESS, levels stay 1 | Switch not pulling GPIO to GND (wrong pin / wiring) |
| All levels 0 | Shorted / missing pull / wrong polarity |
| Service failed | `python3-uinput` / GPIO package missing |

Optional pin override (unit `Environment=`):

```
DIGI_BTN_UP=5
DIGI_BTN_DOWN=6
DIGI_BTN_LEFT=12
DIGI_BTN_RIGHT=13
DIGI_BTN_CONFIRM=16
DIGI_BTN_BACK=19
DIGI_BTN_HOME=20
```
