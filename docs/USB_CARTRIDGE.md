# Digivice USB cartridges

Game Boy–sized shells around USB mass-storage sticks. The Pi sees a normal USB disk; **`cartridge.json`** at the root tells Digivice what is on the cart and which menus to take over.

## Hardware

- 3D-printed GB shell → USB thumb drive → **4-pin** (VBUS, D+, D−, GND) → case receptacle → Pi USB (passthrough)
- Keep **USB audio on a different Pi port** than the cart slot
- Author carts on a PC; copy files to the stick; safely eject

## File layout (copy this tree)

```text
/                          ← USB root (FAT32 or exFAT)
  cartridge.json           ← required manifest
  menu/                    ← shared menu assets (optional)
    bg.png
    theme.ogg
    select.wav
  roms/                    ← when kinds includes "games"
    gb/
      My Game.gb
    nes/
    gba/
    snes/
    genesis/
    ps1/
  movies/                  ← when kinds includes "movies"
    My Movie/
      feature.mkv
      menu/
        bg.png
        theme.ogg
      extras/
        trailer.mkv
        commentary.mkv
  tv/                      ← when kinds includes "tv"
    My Show/
      menu/
        bg.png
        theme.ogg
      s01/
        e01.mkv
        e02.mkv
      s02/
        e01.mkv
  music/                   ← when kinds includes "music"
    Album Name/
      01-track.flac
      02-track.flac
      menu/
        cover.png
        theme.ogg
  audiobooks/              ← optional
  extras/                  ← special features not tied to one title
```

## `cartridge.json` (required)

Minimal **games-only** cart:

```json
{
  "version": 1,
  "title": "Summer Games",
  "kinds": ["games"],
  "games": [
    {
      "title": "Pokemon Red",
      "system": "gb",
      "path": "roms/gb/pokemon_red.gb"
    }
  ]
}
```

**Media + games** cart with DVD-style movie menu:

```json
{
  "version": 1,
  "title": "Movie Night",
  "kinds": ["movies", "games"],
  "logo": "menu/logo.png",
  "menu": {
    "background": "menu/bg.png",
    "logo": "menu/logo.png",
    "music": "menu/theme.ogg",
    "select_sound": "menu/select.wav"
  },
  "movies": [
    {
      "title": "Example Film",
      "path": "movies/example/feature.mkv",
      "menu": {
        "background": "movies/example/menu/bg.png",
        "logo": "movies/example/menu/logo.png",
        "music": "movies/example/menu/theme.ogg"
      },
      "extras": [
        { "title": "Trailer", "path": "movies/example/extras/trailer.mkv" }
      ]
    }
  ],
  "tv": [
    {
      "title": "Example Show",
      "autoplay": true,
      "menu": {
        "background": "tv/example/menu/bg.png",
        "music": "tv/example/menu/theme.ogg"
      },
      "seasons": [
        {
          "title": "Season 1",
          "episodes": [
            { "title": "Pilot", "path": "tv/example/s01/e01.mkv" },
            { "title": "Episode 2", "path": "tv/example/s01/e02.mkv" }
          ]
        }
      ]
    }
  ],
  "music": [
    {
      "title": "Example Album",
      "path": "music/example/",
      "menu": {
        "background": "music/example/menu/cover.png",
        "music": "music/example/menu/theme.ogg"
      }
    }
  ],
  "games": [
    {
      "title": "Super Mario Bros",
      "system": "nes",
      "path": "roms/nes/smb.nes"
    }
  ]
}
```

## `kinds` and menu takeover

| `kinds` value | Takes over |
|---------------|------------|
| `games` | **Games** — cart titles only; Confirm boots ROM |
| `music` | **Media → Music** |
| `movies` | **Home Media** → cart title → logo + name + **Play** / **Extras** |
| `tv` | **Home Media** → cart title → logo + name + **Play** / season list |

**Logo:** put `menu/logo.png` (or `"logo": "…"` in `cartridge.json`). Shown on the **home Media takeover** above the cart name (not on the DVD button screen). DVD screen is background + **Play** / **Extras** / **Scenes** only.

**Scenes:** optional `scenes` on a movie, or embedded chapters in the MKV/MP4 (ffprobe). A **Scenes** button appears when either exists.

```json
"scenes": [
  { "title": "Opening", "time": "0:00" },
  { "title": "Main titles", "time": "0:02:15" },
  { "title": "End credits", "time": "1:28:00" }
]
```

`time` may be `H:MM:SS`, `M:SS`, or seconds.

**Subtitles:** on by default. Digivice loads:
1. Softsubs already inside the MKV/MP4  
2. Sidecar files next to the video (`Beetlejuice.srt`, `Beetlejuice.en.srt`, `.vtt`, `.ass`)  
3. Optional paths in `cartridge.json`:

```json
"subtitles": "movies/Beetlejuice/Beetlejuice.en.srt"
```

or a list of paths. During playback, **s** / **j** cycles tracks; **v** toggles visibility (when a keyboard is available).
| `audiobooks` | **Media → Audiobooks** |

- **No cart** → SD libraries as today
- **Mixed cart** → only sections listed in `kinds` switch; rest stay on SD
- **Eject** → revert immediately

## Desktop “what to do with USB?” popup

Pi OS File Manager (PCManFM) often asks what to do when a stick is inserted. Digivice carts need the drive to **automount**, but not that dialog.

Settings → Update runs `digivice-suppress-usb-prompt`, which sets PCManFM **`autorun=0`** while leaving **`mount_removable=1`**. Manual: `sudo digivice-suppress-usb-prompt`. Replug the cart (or restart the session) if the prompt still appears once after Update.

## `system` values (games)

| `system` | Emulator folder |
|----------|-----------------|
| `gb` | Game Boy / GBC |
| `nes` | NES |
| `smsgg` | SMS / Game Gear |
| `gba` | GBA |
| `snes` | SNES |
| `genesis` | Genesis / Mega Drive |
| `ps1` | PlayStation (digital pad) |

Paths in the manifest are **relative to the USB root**. Use forward slashes.

## Supported media extensions

| Type | Extensions |
|------|--------------|
| Video | `.mkv`, `.mp4`, `.avi`, `.webm`, `.mov` |
| Audio | `.flac`, `.mp3`, `.ogg`, `.opus`, `.wav`, `.m4a` |
| Menu images | `.png`, `.jpg`, `.webp` |
| Menu audio | `.ogg`, `.mp3`, `.wav`, `.flac` |

## Authoring on PC

1. Format stick **FAT32** (or exFAT for large files)
2. Copy the folder tree above
3. Edit `cartridge.json` — all paths must exist on the stick
4. Safely eject; insert into Digivice cart slot
5. Digivice mounts under `/media/<user>/…` and reads `cartridge.json`

Example templates ship in [`pi_handset/cartridge_templates/`](../pi_handset/cartridge_templates/).

## Bench test (no 3D shell yet)

Plug a normal USB stick with `cartridge.json` into a Pi USB port. Run:

```bash
python3 -c "from esp_handset.cartridge import refresh; c=refresh(); print(c)"
```

For player, codec, USB, and cart-log diagnostics:

```bash
digivice-media-doctor /media/<user>/<cart>/movies/<title>/feature.mkv
```

The report is saved as `~/.esp-handset/media-doctor.txt` and also copied to
`/tmp/digivice-media-doctor.txt`. It includes the deployed app version,
player versions, the recent mpv log, USB topology, Pi health, and `ffprobe`
details for the selected video.

## See also

- Pi 4 migration plan (cart slot CAD, 4-pin pinout TBD)
- [`media_ui.py`](../pi_handset/esp_handset/media_ui.py) — local SD libraries
- [`emu_ui.py`](../pi_handset/esp_handset/emu_ui.py) — ROM play
