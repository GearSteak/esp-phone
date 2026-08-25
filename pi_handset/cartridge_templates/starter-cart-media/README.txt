DIGIVICE MEDIA CART — quickstart
================================

COPY everything in this folder to your USB stick root.

Then drop your ripped files into the example folders (or rename folders to match your titles).

WHAT'S INCLUDED
---------------
  cartridge.json     — already set for movies + tv + music
  movies/Example Film/
  tv/Example Show/
  music/Example Album/

AFTER COPYING FILES
-------------------
1. Rename "Example Film" / "Example Show" / "Example Album" OR edit paths in cartridge.json
2. Match filenames in cartridge.json to what you actually put on the stick
3. Add menu/bg.png, menu/theme.ogg in each title's menu/ folder (optional but nice)
4. Safely eject

KINDS in cartridge.json:
  "movies"  → takes over Media → Videos (DVD-style menus when menu/ assets exist)
  "tv"      → takes over Media → Videos (autoplay next episode when "autoplay": true)
  "music"   → takes over Media → Music

Remove a kind from the list if you don't use that section.

SUPPORTED FILES
---------------
  Video:  .mkv  .mp4  .avi  .webm  .mov
  Audio:  .flac  .mp3  .ogg  .opus  .wav  .m4a
  Menu:   .png  .jpg  .webp  (images)   .ogg  .mp3  .wav  (sounds)

See cartridge-media-example.json in starter-cart for a bigger template.
