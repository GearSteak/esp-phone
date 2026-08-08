#include "status_icons.h"
#include "sd_assets.h"
#include <stdio.h>

static const lv_img_dsc_t* statusSdOrEmbed(const char* id,
                                           const lv_img_dsc_t* embed) {
  const lv_img_dsc_t* sd = SdAssets::statusById(id);
  if (sd) return sd;
  return embed;
}

const lv_img_dsc_t* statusIconSignal(int bars0to4) {
  if (bars0to4 < 0) bars0to4 = 0;
  if (bars0to4 > 4) bars0to4 = 4;
  char id[12];
  snprintf(id, sizeof(id), "sig_%d", bars0to4);
#if UI_USE_STATUS_ICONS
  static const lv_img_dsc_t* tab[] = {&sig_0_dsc, &sig_1_dsc, &sig_2_dsc,
                                     &sig_3_dsc, &sig_4_dsc};
  return statusSdOrEmbed(id, tab[bars0to4]);
#else
  return statusSdOrEmbed(id, nullptr);
#endif
}

const lv_img_dsc_t* statusIconBattery(int pct, int chargeStatus) {
  const char* id = "bat_0";
  if (chargeStatus == 1)
    id = "bat_chg";
  else if (pct > 80)
    id = "bat_4";
  else if (pct > 60)
    id = "bat_3";
  else if (pct > 40)
    id = "bat_2";
  else if (pct > 15)
    id = "bat_1";
#if UI_USE_STATUS_ICONS
  const lv_img_dsc_t* emb = &bat_0_dsc;
  if (chargeStatus == 1)
    emb = &bat_chg_dsc;
  else if (pct > 80)
    emb = &bat_4_dsc;
  else if (pct > 60)
    emb = &bat_3_dsc;
  else if (pct > 40)
    emb = &bat_2_dsc;
  else if (pct > 15)
    emb = &bat_1_dsc;
  return statusSdOrEmbed(id, emb);
#else
  return statusSdOrEmbed(id, nullptr);
#endif
}

const lv_img_dsc_t* statusIconBt(bool on) {
  const char* id = on ? "bt_on" : "bt_off";
#if UI_USE_STATUS_ICONS
  return statusSdOrEmbed(id, on ? &bt_on_dsc : &bt_off_dsc);
#else
  return statusSdOrEmbed(id, nullptr);
#endif
}
