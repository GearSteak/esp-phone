# Wallpaper & UI assets

## Background right now

Solid color via `include/Config.h` (blank/black by default):

```c
#define UI_BG_COLOR           0x000000
#define UI_STATUS_BAR_COLOR   0x111111
#define UI_STATUS_BAR_HEIGHT  32
#define UI_CONTENT_BG_COLOR   0x000000
#define UI_CONTENT_BG_OPA     255     // 255 = opaque panels
#define UI_USE_WALLPAPER       0       // flash wallpaper; prefer SD instead
#define UI_SD_ASSETS           1       // load /ui art from TF card
```

## UI art on the TF card (preferred)

Put JPEGs on the card (not in firmware flash):

```
/ui/wallpaper.jpg          — 320×480 optional
/ui/icons/icon_*.jpg       — 48×48 app icons
/ui/status/*.jpg           — signal / battery / BT
```

See `assets/icons/README.md`. Media stays on SD too: `/music`, `/photos`, `/videos`, `/books`, `/audiobooks`.

Copy files to the card, reboot — **no rebuild** needed when you change icons/wallpaper.

## Optional flash fallback

Only if you want art without an SD card: convert to LVGL C arrays and set `UI_USE_APP_ICONS` / `UI_USE_WALLPAPER`. Prefer SD for this project.
