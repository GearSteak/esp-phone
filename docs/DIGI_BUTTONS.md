# Digivice hard buttons (D-pad + Confirm / Back / Home)

Seven tactile buttons instead of CardKB or a T9 pad. Each switch: one side on the listed GPIO, other to **GND**. Internal pull-ups — no VCC needed.

## What each button does

| Button | Digivice action | Key sent |
|--------|-----------------|----------|
| **Up** | Move focus / home row up | ↑ |
| **Down** | Move focus / home row down | ↓ |
| **Left** | Move focus left | ← |
| **Right** | Move focus right | → |
| **Confirm** | Open / activate / select | Enter |
| **Back** | Leave app / cancel | Esc |
| **Home** | Jump home (Digivice home) | Home |

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

Service: **`digi-buttons-inputd`** — must be **enabled on boot** (multi-user).  
Created by `install-handset` / `digivice-update` / `digivice-ensure-buttons`.  
`handset-session phone` also forces a start if the unit is down.

```bash
# One-shot fix on the Pi (now / after pull)
sudo digivice-ensure-buttons
# or:
sudo systemctl enable --now digi-buttons-inputd

sudo systemctl status digi-buttons-inputd
journalctl -u digi-buttons-inputd -f
```

Optional pin override (systemd `Environment=`):

```
DIGI_BTN_UP=5
DIGI_BTN_DOWN=6
DIGI_BTN_LEFT=12
DIGI_BTN_RIGHT=13
DIGI_BTN_CONFIRM=16
DIGI_BTN_BACK=19
DIGI_BTN_HOME=20
```
