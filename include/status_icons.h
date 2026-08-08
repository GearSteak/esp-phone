#pragma once

/*
 * Status-bar icon slots (sig / battery / bt).
 * Same workflow as app icons: drop PNGs in assets/status/, convert later.
 * Expected names (or map your Lopaka names):
 *   sig_0 … sig_4, bat_0 … bat_4, bat_chg, bt_on, bt_off
 */

#include "Config.h"
#include <lvgl.h>

#ifndef UI_USE_STATUS_ICONS
#define UI_USE_STATUS_ICONS 0
#endif

const lv_img_dsc_t* statusIconSignal(int bars0to4);
const lv_img_dsc_t* statusIconBattery(int pct, int chargeStatus);
const lv_img_dsc_t* statusIconBt(bool on);

#if UI_USE_STATUS_ICONS
extern const lv_img_dsc_t sig_0_dsc;
extern const lv_img_dsc_t sig_1_dsc;
extern const lv_img_dsc_t sig_2_dsc;
extern const lv_img_dsc_t sig_3_dsc;
extern const lv_img_dsc_t sig_4_dsc;
extern const lv_img_dsc_t bat_0_dsc;
extern const lv_img_dsc_t bat_1_dsc;
extern const lv_img_dsc_t bat_2_dsc;
extern const lv_img_dsc_t bat_3_dsc;
extern const lv_img_dsc_t bat_4_dsc;
extern const lv_img_dsc_t bat_chg_dsc;
extern const lv_img_dsc_t bt_on_dsc;
extern const lv_img_dsc_t bt_off_dsc;
#endif
