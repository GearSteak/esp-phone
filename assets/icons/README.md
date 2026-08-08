# App icons — keep these on the SD card

Copy **48×48 JPEG** files onto the phone TF card:

```
/ui/icons/icon_comm.jpg
/ui/icons/icon_phone.jpg
...
```

Firmware loads them at boot into PSRAM (nothing baked into flash unless you opt in).

| File (no path) | App / folder |
|----------------|--------------|
| `icon_comm.jpg` | Phone / Comm |
| `icon_phone.jpg` | Phone |
| `icon_contacts.jpg` | Contacts |
| `icon_calllog.jpg` | Call Log |
| `icon_messages.jpg` | Messages |
| `icon_notifs.jpg` | Notifications |
| `icon_email.jpg` | Email |
| `icon_clock.jpg` | Clock |
| `icon_calendar.jpg` | Calendar |
| `icon_browser.jpg` | Browser |
| `icon_tools.jpg` | Tools |
| `icon_media.jpg` | Media |
| `icon_games.jpg` | Games |
| `icon_settings.jpg` | Settings |
| `icon_camera.jpg` | Camera |
| `icon_gallery.jpg` | Gallery |
| `icon_gps.jpg` | GPS |
| `icon_notes.jpg` | Notes |
| `icon_todos.jpg` | Todos |
| `icon_music.jpg` | Music |
| `icon_video.jpg` | Videos |
| `icon_ebooks.jpg` | Ebooks |
| `icon_audiobooks.jpg` | Audiobooks |
| `icon_voice.jpg` | Voice notes |
| `icon_calc.jpg` | Calculator |
| `icon_weather.jpg` | Weather |
| `icon_alarms.jpg` | Alarms |
| `icon_snake.jpg` | Snake |
| `icon_pong.jpg` | Pong |
| `icon_tetris.jpg` | Tetris |
| `icon_solitaire.jpg` | Solitaire |
| `icon_uno.jpg` | Uno |

## Specs
- **48×48** JPEG (baseline)
- No transparency (JPEG); use a solid or matching background color
- Missing files → text label only for that app

## Also on SD
- `/ui/wallpaper.jpg` — optional 320×480 desktop background  
- `/ui/status/sig_0.jpg` … `sig_4.jpg`, `bat_0`…`bat_4`, `bat_chg`, `bt_on`, `bt_off`

You can keep working copies of the same files under `assets/icons/` in this repo for editing; the phone reads the **card**, not the PC folder.
