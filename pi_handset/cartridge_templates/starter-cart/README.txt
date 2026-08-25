DIGIVICE USB CART — copy this whole folder to your USB stick
==============================================================

1. Plug USB into your PC
2. Open the USB drive (e.g. D:)
3. Copy EVERYTHING inside this "starter-cart" folder onto the USB root
   (cartridge.json must sit at the top level of the stick, not inside a subfolder)
4. Drop your files into the folders below
5. Edit cartridge.json — set title, kinds, and paths to match your files
6. Safely eject the stick

FOLDER GUIDE
------------
roms/gb/       .gb .gbc files
roms/nes/      .nes files
roms/gba/      .gba files
roms/snes/     .sfc .smc files
roms/genesis/  .md .bin files
roms/ps1/      .bin .cue .pbp files

movies/        one folder per movie + feature.mkv + menu/ + extras/
tv/            one folder per show + s01/e01.mkv etc.
music/         one folder per album + tracks
menu/          optional shared menu art/sounds for the whole cart

KINDS in cartridge.json control what Digivice takes over:
  games | music | movies | tv | audiobooks

See docs/USB_CARTRIDGE.md in the esp-phone repo for full examples.
