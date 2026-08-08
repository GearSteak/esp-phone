#include "app_icons.h"
#include "sd_assets.h"

/*
 * Prefer SD card JPGs under /ui/icons/<id>.jpg (loaded at boot into PSRAM).
 * Optional flash-baked arrays only if UI_USE_APP_ICONS is 1.
 */

#if UI_USE_APP_ICONS
#define I(x) &x
#else
#define I(x) nullptr
#endif

static const AppIconSlot kIcons[] = {
    {"icon_comm", UI_COMM, I(icon_comm_dsc)},
    {"icon_phone", UI_PHONE, I(icon_phone_dsc)},
    {"icon_contacts", UI_CONTACTS, I(icon_contacts_dsc)},
    {"icon_calllog", UI_CALL_LOG, I(icon_calllog_dsc)},
    {"icon_messages", UI_SMS_THREADS, I(icon_messages_dsc)},
    {"icon_notifs", UI_NOTIFS, I(icon_notifs_dsc)},
    {"icon_email", UI_EMAIL, I(icon_email_dsc)},
    {"icon_clock", UI_CLOCK, I(icon_clock_dsc)},
    {"icon_calendar", UI_CALENDAR, I(icon_calendar_dsc)},
    {"icon_browser", UI_BROWSER, I(icon_browser_dsc)},
    {"icon_tools", UI_TOOLS, I(icon_tools_dsc)},
    {"icon_media", UI_MEDIA, I(icon_media_dsc)},
    {"icon_games", UI_GAMES_MENU, I(icon_games_dsc)},
    {"icon_settings", UI_SETTINGS, I(icon_settings_dsc)},
    {"icon_camera", UI_CAMERA, I(icon_camera_dsc)},
    {"icon_gallery", UI_GALLERY, I(icon_gallery_dsc)},
    {"icon_gps", UI_GPS, I(icon_gps_dsc)},
    {"icon_notes", UI_NOTES, I(icon_notes_dsc)},
    {"icon_todos", UI_TODOS, I(icon_todos_dsc)},
    {"icon_music", UI_MUSIC, I(icon_music_dsc)},
    {"icon_ebooks", UI_EBOOKS, I(icon_ebooks_dsc)},
    {"icon_audiobooks", UI_AUDIOBOOKS, I(icon_audiobooks_dsc)},
    {"icon_voice", UI_RECORDER, I(icon_voice_dsc)},
    {"icon_calc", UI_CALC, I(icon_calc_dsc)},
    {"icon_weather", UI_WEATHER, I(icon_weather_dsc)},
    {"icon_alarms", UI_ALARMS, I(icon_alarms_dsc)},
    {"icon_video", UI_VIDEO, nullptr},
    {"icon_solitaire", UI_GAME_SOLITAIRE, nullptr},
    {"icon_uno", UI_GAME_UNO, nullptr},
    {"icon_snake", UI_GAME_SNAKE, nullptr},
    {"icon_pong", UI_GAME_PONG, nullptr},
    {"icon_tetris", UI_GAME_TETRIS, nullptr},
};

const AppIconSlot* appIconTable(int& countOut) {
  countOut = (int)(sizeof(kIcons) / sizeof(kIcons[0]));
  return kIcons;
}

const lv_img_dsc_t* appIconForScreen(UiScreen s) {
  for (const auto& e : kIcons) {
    if (e.screen != s) continue;
    const lv_img_dsc_t* sd = SdAssets::iconById(e.id);
    if (sd) return sd;
#if UI_USE_APP_ICONS
    return e.img;
#else
    return nullptr;
#endif
  }
  return nullptr;
}
