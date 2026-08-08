#pragma once

#include "Config.h"
#include <lvgl.h>

/*
 * Load UI art from the TF card into PSRAM (not flash).
 *
 * Layout on SD:
 *   /ui/wallpaper.jpg     — optional 320×480 desktop background
 *   /ui/icons/<id>.jpg    — 48×48 app icons (see assets/icons/README.md names)
 *   /ui/status/<id>.jpg   — 24×24 status glyphs (sig_0…, bat_0…, bt_on…)
 *
 * Missing files → text-only UI (same as today). Drop files anytime and reboot.
 */

#ifndef UI_SD_ASSETS
#define UI_SD_ASSETS 1
#endif

#ifndef UI_ICON_DIR
#define UI_ICON_DIR "/ui/icons"
#endif
#ifndef UI_STATUS_DIR
#define UI_STATUS_DIR "/ui/status"
#endif
#ifndef UI_WALLPAPER_PATH
#define UI_WALLPAPER_PATH "/ui/wallpaper.jpg"
#endif

namespace SdAssets {
bool begin();  // call after Storage::begin()
const lv_img_dsc_t* iconById(const char* id);  // e.g. "icon_comm"
const lv_img_dsc_t* wallpaper();
const lv_img_dsc_t* statusById(const char* id);
}  // namespace SdAssets
