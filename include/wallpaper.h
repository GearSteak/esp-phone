#pragma once

/*
 * Optional full-screen wallpaper (320×480).
 * See assets/README.md for how to generate wallpaper.c
 */

#include "Config.h"

#if UI_USE_WALLPAPER
#include <lvgl.h>
extern const lv_img_dsc_t wallpaper_dsc;
#endif
