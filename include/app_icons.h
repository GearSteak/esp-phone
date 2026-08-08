#pragma once

/*
 * App icons — 48×48 for home / folder menus.
 *
 * Workflow
 * --------
 * 1) Design in Lopaka at 48×48 (or export square and resize).
 * 2) Either:
 *    A) PNG → assets/icons/<id>.png → LVGL Image Converter → C array
 *    B) Lopaka LVGL export → paste arrays into src/app_icons_data.cpp
 * 3) Set UI_USE_APP_ICONS 1 in Config.h when assets are ready.
 * 4) Register each icon in g_appIcons[] (see src/app_icons.cpp).
 *
 * Expected asset IDs (match Lopaka layer names to these if you can):
 *   icon_comm, icon_phone, icon_contacts, icon_calllog, icon_messages,
 *   icon_notifs, icon_email, icon_clock, icon_calendar, icon_browser,
 *   icon_tools, icon_media, icon_games, icon_settings, icon_camera,
 *   icon_gallery, icon_gps, icon_notes, icon_todos, icon_music,
 *   icon_ebooks, icon_audiobooks, icon_voice, icon_calc, icon_weather,
 *   icon_alarms, icon_back
 */

#include "Config.h"
#include <lvgl.h>
#include "ui.h"

#ifndef UI_USE_APP_ICONS
#define UI_USE_APP_ICONS 0
#endif

struct AppIconSlot {
  const char* id;                 // filename / Lopaka name key
  UiScreen screen;                // UI_MAIN folder targets use this
  const lv_img_dsc_t* img;        // nullptr until asset wired
};

// Returns image for a destination screen, or nullptr → text-only button.
const lv_img_dsc_t* appIconForScreen(UiScreen s);
const AppIconSlot* appIconTable(int& countOut);

#if UI_USE_APP_ICONS
// Declarations filled when you add converted assets in app_icons_data.cpp
extern const lv_img_dsc_t icon_comm_dsc;
extern const lv_img_dsc_t icon_phone_dsc;
extern const lv_img_dsc_t icon_contacts_dsc;
extern const lv_img_dsc_t icon_calllog_dsc;
extern const lv_img_dsc_t icon_messages_dsc;
extern const lv_img_dsc_t icon_notifs_dsc;
extern const lv_img_dsc_t icon_email_dsc;
extern const lv_img_dsc_t icon_clock_dsc;
extern const lv_img_dsc_t icon_calendar_dsc;
extern const lv_img_dsc_t icon_browser_dsc;
extern const lv_img_dsc_t icon_tools_dsc;
extern const lv_img_dsc_t icon_media_dsc;
extern const lv_img_dsc_t icon_games_dsc;
extern const lv_img_dsc_t icon_settings_dsc;
extern const lv_img_dsc_t icon_camera_dsc;
extern const lv_img_dsc_t icon_gallery_dsc;
extern const lv_img_dsc_t icon_gps_dsc;
extern const lv_img_dsc_t icon_notes_dsc;
extern const lv_img_dsc_t icon_todos_dsc;
extern const lv_img_dsc_t icon_music_dsc;
extern const lv_img_dsc_t icon_ebooks_dsc;
extern const lv_img_dsc_t icon_audiobooks_dsc;
extern const lv_img_dsc_t icon_voice_dsc;
extern const lv_img_dsc_t icon_calc_dsc;
extern const lv_img_dsc_t icon_weather_dsc;
extern const lv_img_dsc_t icon_alarms_dsc;
#endif
