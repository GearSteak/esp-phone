Digivice USB cartridge templates
================================

Copy one of these folders to the ROOT of a USB stick, then add your files.

  example/       Full demo layout (games + movies + tv + music)
  games-only/    Minimal games cart

Required on every cart:
  cartridge.json

See docs/USB_CARTRIDGE.md for the full spec.

Quick layout:
  cartridge.json
  menu/          (optional shared DVD menu assets)
  roms/gb/       .gb .gbc
  roms/nes/      .nes
  roms/gba/      .gba
  roms/snes/     .sfc .smc
  roms/genesis/  .md .bin
  roms/ps1/      .bin .cue .pbp
  movies/        .mkv .mp4 + menu/ subfolders
  tv/            seasons/episodes + menu/
  music/         tracks or album folders + menu/

Format: FAT32 or exFAT. Safely eject before inserting in Digivice.
