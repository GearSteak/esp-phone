# Digivice full update (terminal)

One command. Do this whenever software is out of date or half-broken.

## Command

```bash
sudo digivice-full-update
```

First time (command not installed yet):

```bash
cd ~/esp-phone
git pull
sudo bash pi_handset/session/full-update.sh
```

After that, `digivice-full-update` is on your PATH forever.

## What it updates

| Step | Action |
|------|--------|
| Git | `fetch` + hard-reset to `origin/main` |
| apt | PyQt5, uinput, GPIO, xdotool, … |
| Tree | copy UI/scripts → `/opt/esp-handset` + bins |
| Services | `digi-buttons-inputd` + `esp-keyd` enable/start |
| udev | Digivice keyboard + uinput |
| Cursor | Xorg software cursor conf |
| SPI | **left alone** (userspace ST7789 safe) |
| UI | restarts Digivice when done |

Log: `~/.esp-handset/full-update.log`

## Flags

```bash
sudo digivice-full-update                  # normal full stack
sudo digivice-full-update --no-restart     # install only
sudo digivice-full-update --reboot         # reboot after
sudo digivice-full-update --with-spi-userspace   # also re-apply SPI userspace
sudo digivice-full-update --with-display   # also DRM install-display (can break SPI)
```

## Not the same as

- `digivice-update` — lighter UI/script reinstall only  
- Settings → Update → FULL — same as this terminal command  
