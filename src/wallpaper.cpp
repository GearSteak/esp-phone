/*
 * Placeholder wallpaper — replace with LVGL Image Converter output (320×480).
 * Only used when UI_USE_WALLPAPER is 1 in Config.h.
 */

#include "Config.h"

#if UI_USE_WALLPAPER
#include <lvgl.h>

static const uint8_t wallpaper_map[] = {
    0x00, 0x00,
};

const lv_img_dsc_t wallpaper_dsc = {
    {
        LV_IMG_CF_TRUE_COLOR,
        0,
        0,
        1,
        1,
    },
    2,
    wallpaper_map,
};
#endif
