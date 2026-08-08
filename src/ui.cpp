#include "ui.h"
#include "keyboard.h"
#include "games.h"
#include "sip.h"
#include "modem.h"
#include "audio.h"
#include "storage.h"
#include "shared_state.h"
#include "wallpaper.h"
#include "camera_app.h"
#include "media_player.h"
#include "ebook.h"
#include "gps.h"
#include "notes_todo.h"
#include "phone_data.h"
#include "phone_tools.h"
#include "online_apps.h"
#include "voice_recorder.h"
#include "app_icons.h"
#include "status_icons.h"
#include "video_player.h"
#include "solitaire.h"
#include "uno.h"
#include "sd_assets.h"
#include "lora_radio.h"
#include <TFT_eSPI.h>
#include <lvgl.h>
#include <string.h>
#include <stdio.h>
#include <ctype.h>

Ui g_ui;

static TFT_eSPI tft;
static lv_disp_draw_buf_t draw_buf;
static lv_color_t* buf1 = nullptr;
static lv_color_t* buf2 = nullptr;
static lv_obj_t* wallpaperImg_ = nullptr;
static lv_obj_t* statusBar_ = nullptr;
static lv_obj_t* statusLabel_ = nullptr;
static lv_obj_t* statusSigImg_ = nullptr;
static lv_obj_t* statusBatImg_ = nullptr;
static lv_obj_t* statusBtImg_ = nullptr;
static lv_obj_t* rootContent_ = nullptr;
static lv_obj_t* focusables_[32];
static lv_obj_t* canvas_ = nullptr;
static lv_color_t* canvasBuf_ = nullptr;
static lv_obj_t* s_composeToLab = nullptr;
static lv_obj_t* camCanvas_ = nullptr;
static lv_color_t* camBuf_ = nullptr;
static lv_obj_t* fileLabel_ = nullptr;
static lv_obj_t* listLabel_ = nullptr;
static lv_obj_t* gpsLabel_ = nullptr;
static lv_obj_t* clockLabel_ = nullptr;
static lv_obj_t* cursorObj_ = nullptr;
static lv_obj_t* hoveredBtn_ = nullptr;
static lv_indev_t* ptrIndev_ = nullptr;
static constexpr int CAM_W = 320;
static constexpr int CAM_H = 240;

static void flush_cb(lv_disp_drv_t* disp, const lv_area_t* area,
                     lv_color_t* color_p) {
  uint32_t w = area->x2 - area->x1 + 1;
  uint32_t h = area->y2 - area->y1 + 1;
  tft.startWrite();
  tft.setAddrWindow(area->x1, area->y1, w, h);
  tft.pushColors((uint16_t*)&color_p->full, w * h, true);
  tft.endWrite();
  lv_disp_flush_ready(disp);
}

void Ui::setBackgroundColor(uint32_t hexRgb) {
  bgColor_ = hexRgb;
  applyTheme();
}

void Ui::applyTheme() {
  lv_obj_t* scr = lv_scr_act();
  lv_obj_set_style_bg_color(scr, lv_color_hex(bgColor_), 0);
  lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);

  if (statusBar_) {
    lv_obj_set_style_bg_color(statusBar_, lv_color_hex(UI_STATUS_BAR_COLOR), 0);
    lv_obj_set_style_bg_opa(statusBar_, UI_STATUS_BG_OPA, 0);
  }
  if (rootContent_) {
    lv_obj_set_style_bg_color(rootContent_, lv_color_hex(UI_CONTENT_BG_COLOR), 0);
    lv_obj_set_style_bg_opa(rootContent_, UI_CONTENT_BG_OPA, 0);
  }

#if UI_USE_WALLPAPER
  if (wallpaperImg_) {
    lv_obj_clear_flag(wallpaperImg_, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_background(wallpaperImg_);
  }
#else
  if (wallpaperImg_) {
    lv_obj_clear_flag(wallpaperImg_, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_background(wallpaperImg_);
  }
#endif
}

void Ui::setupChrome() {
  lv_obj_t* scr = lv_scr_act();
  lv_obj_set_style_bg_color(scr, lv_color_hex(bgColor_), 0);
  lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);

#if UI_USE_WALLPAPER
  wallpaperImg_ = lv_img_create(scr);
  lv_img_set_src(wallpaperImg_, &wallpaper_dsc);
  lv_obj_set_size(wallpaperImg_, TFT_WIDTH_PX, TFT_HEIGHT_PX);
  lv_obj_align(wallpaperImg_, LV_ALIGN_TOP_LEFT, 0, 0);
  lv_obj_clear_flag(wallpaperImg_, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_move_background(wallpaperImg_);
#else
  // Prefer SD wallpaper when present (/ui/wallpaper.jpg)
  if (SdAssets::wallpaper()) {
    wallpaperImg_ = lv_img_create(scr);
    lv_img_set_src(wallpaperImg_, SdAssets::wallpaper());
    lv_obj_set_size(wallpaperImg_, TFT_WIDTH_PX, TFT_HEIGHT_PX);
    lv_obj_align(wallpaperImg_, LV_ALIGN_TOP_LEFT, 0, 0);
    lv_obj_clear_flag(wallpaperImg_, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_move_background(wallpaperImg_);
  }
#endif

  statusBar_ = lv_obj_create(scr);
  lv_obj_set_size(statusBar_, TFT_WIDTH_PX, UI_STATUS_BAR_HEIGHT);
  lv_obj_align(statusBar_, LV_ALIGN_TOP_MID, 0, 0);
  lv_obj_set_style_radius(statusBar_, 0, 0);
  lv_obj_set_style_border_width(statusBar_, 0, 0);
  lv_obj_set_style_pad_all(statusBar_, 4, 0);
  lv_obj_set_flex_flow(statusBar_, LV_FLEX_FLOW_ROW);
  lv_obj_set_flex_align(statusBar_, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER,
                        LV_FLEX_ALIGN_CENTER);
  lv_obj_set_style_pad_column(statusBar_, 4, 0);
  lv_obj_clear_flag(statusBar_, LV_OBJ_FLAG_SCROLLABLE);

  statusSigImg_ = lv_img_create(statusBar_);
  lv_obj_add_flag(statusSigImg_, LV_OBJ_FLAG_HIDDEN);
  statusBatImg_ = lv_img_create(statusBar_);
  lv_obj_add_flag(statusBatImg_, LV_OBJ_FLAG_HIDDEN);
  statusBtImg_ = lv_img_create(statusBar_);
  lv_obj_add_flag(statusBtImg_, LV_OBJ_FLAG_HIDDEN);

  statusLabel_ = lv_label_create(statusBar_);
  lv_label_set_text(statusLabel_, "");
  lv_obj_set_flex_grow(statusLabel_, 1);

  rootContent_ = lv_obj_create(scr);
  lv_obj_set_size(rootContent_, TFT_WIDTH_PX,
                  TFT_HEIGHT_PX - UI_STATUS_BAR_HEIGHT);
  lv_obj_align(rootContent_, LV_ALIGN_BOTTOM_MID, 0, 0);
  lv_obj_set_style_pad_all(rootContent_, 8, 0);
  lv_obj_set_style_radius(rootContent_, 0, 0);
  lv_obj_set_style_border_width(rootContent_, 0, 0);

  applyTheme();
}

bool Ui::begin() {
  tft.init();
  tft.setRotation(DISP_ROTATION);
  tft.fillScreen(TFT_BLACK);
  if (DISP_BL >= 0) {
    pinMode(DISP_BL, OUTPUT);
    digitalWrite(DISP_BL, HIGH);
  }

  lv_init();
  const size_t px = TFT_WIDTH_PX * 40;
  buf1 = (lv_color_t*)heap_caps_malloc(px * sizeof(lv_color_t), MALLOC_CAP_DMA);
  buf2 = (lv_color_t*)heap_caps_malloc(px * sizeof(lv_color_t), MALLOC_CAP_DMA);
  if (!buf1) buf1 = (lv_color_t*)malloc(px * sizeof(lv_color_t));
  if (!buf2) buf2 = (lv_color_t*)malloc(px * sizeof(lv_color_t));
  lv_disp_draw_buf_init(&draw_buf, buf1, buf2, px);

  static lv_disp_drv_t disp_drv;
  lv_disp_drv_init(&disp_drv);
  disp_drv.hor_res = TFT_WIDTH_PX;
  disp_drv.ver_res = TFT_HEIGHT_PX;
  disp_drv.flush_cb = flush_cb;
  disp_drv.draw_buf = &draw_buf;
  lv_disp_drv_register(&disp_drv);

  bgColor_ = UI_BG_COLOR;
  setupChrome();
  setupPointer();
  lastActivityMs_ = millis();
  if (g_settings.get().lockEnabled && g_settings.get().pin[0]) {
    lockNow();
  } else {
    showScreen(UI_MAIN);
  }
  return true;
}

void Ui::loop() {
  g_media.loop();
  g_clock.tick();
  g_calendar.tickReminders();
  if (screen_ == UI_RECORDER && g_recorder.isRecording()) g_recorder.pump();
  pollCallState();
  if (screen_ == UI_CAMERA) cameraTick();
  if (screen_ == UI_VIDEO_PLAY) videoTick();
  if (screen_ == UI_GAME_SOLITAIRE || screen_ == UI_GAME_UNO) cardGameTick();
  if (screen_ == UI_GPS && g_gps.isOn()) {
    g_gps.poll();
    refreshGpsLabel();
  }
  if (screen_ == UI_LOCK || screen_ == UI_CLOCK) refreshLockClock();
  if (screen_ == UI_SET_NETWORK) refreshNetworkStatus();
  if (screen_ == UI_LORA) {
    g_lora.poll();
    refreshLoraUi();
  } else if (g_lora.isReady()) {
    g_lora.poll();
  }
  if (usesPointer()) updatePointerHover();

  // Auto-lock
  if (!locked_ && g_settings.get().lockEnabled &&
      g_settings.get().lockTimeoutSec > 0 &&
      millis() - lastActivityMs_ > g_settings.get().lockTimeoutSec * 1000UL) {
    lockNow();
  }
  lv_timer_handler();
}

void Ui::leaveCamera() {
  g_camera.end();
  camCanvas_ = nullptr;
}

void Ui::selectFileDelta(int d) {
  if (fileCount_ <= 0) return;
  fileIndex_ = (fileIndex_ + d + fileCount_) % fileCount_;
  refreshFileListLabel();
}

void Ui::playSelectedMusic() {
  if (g_media.isPlaying())
    g_media.pause();
  else if (g_media.isPaused())
    g_media.resume();
  else if (fileCount_ > 0)
    g_media.play(fileList_[fileIndex_], MEDIA_MUSIC);
}

void Ui::playSelectedAudiobook() {
  if (g_media.isPlaying())
    g_media.pause();
  else if (g_media.isPaused())
    g_media.resume();
  else if (fileCount_ > 0)
    g_media.play(fileList_[fileIndex_], MEDIA_AUDIOBOOK);
}

void Ui::openSelectedEbook() {
  if (fileCount_ > 0 && g_ebook.open(fileList_[fileIndex_])) {
    showScreen(UI_EBOOK_READ);
  }
}

void Ui::snapCamera() {
  char path[64];
  g_camera.saveJpeg(path, sizeof(path));
}

static void styleFocus(lv_obj_t* obj, bool on);

void Ui::clearRoot() {
  if (hoveredBtn_) {
    styleFocus(hoveredBtn_, false);
    hoveredBtn_ = nullptr;
  }
  lv_obj_clean(rootContent_);
  focusCount_ = 0;
  focusIndex_ = 0;
  canvas_ = nullptr;
  clockLabel_ = nullptr;
  memset(focusables_, 0, sizeof(focusables_));
}

static lv_obj_t* makeBtn(lv_obj_t* parent, const char* txt, lv_event_cb_t cb,
                         void* user) {
  lv_obj_t* btn = lv_btn_create(parent);
  lv_obj_set_height(btn, 44);
  lv_obj_set_style_bg_color(btn, lv_color_hex(0x238636), 0);
  lv_obj_add_event_cb(btn, cb, LV_EVENT_CLICKED, user);
  lv_obj_t* lab = lv_label_create(btn);
  lv_label_set_text(lab, txt);
  lv_obj_center(lab);
  return btn;
}

// Home / folder entry: icon (48×48) + label when UI_USE_APP_ICONS and asset exist
static lv_obj_t* makeAppBtn(lv_obj_t* parent, const char* txt, UiScreen dest,
                            lv_event_cb_t cb) {
  const lv_img_dsc_t* ic = appIconForScreen(dest);
  lv_obj_t* btn = lv_btn_create(parent);
  lv_obj_set_width(btn, 220);
  lv_obj_set_style_bg_color(btn, lv_color_hex(0x238636), 0);
  lv_obj_add_event_cb(btn, cb, LV_EVENT_CLICKED, (void*)(uintptr_t)dest);
  if (ic) {
    lv_obj_set_height(btn, 64);
    lv_obj_set_flex_flow(btn, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(btn, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_column(btn, 12, 0);
    lv_obj_t* img = lv_img_create(btn);
    lv_img_set_src(img, ic);
    lv_obj_t* lab = lv_label_create(btn);
    lv_label_set_text(lab, txt);
  } else {
    lv_obj_set_height(btn, 44);
    lv_obj_t* lab = lv_label_create(btn);
    lv_label_set_text(lab, txt);
    lv_obj_center(lab);
  }
  return btn;
}

void Ui::showScreen(UiScreen s) {
  if (screen_ == UI_CAMERA && s != UI_CAMERA) leaveCamera();
  if (screen_ == UI_VIDEO_PLAY && s != UI_VIDEO_PLAY) leaveVideo();
  if ((screen_ == UI_GAME_SOLITAIRE || screen_ == UI_GAME_UNO) &&
      s != UI_GAME_SOLITAIRE && s != UI_GAME_UNO)
    leaveCardGame();
  screen_ = s;
  clearRoot();
  fileLabel_ = nullptr;
  listLabel_ = nullptr;
  gpsLabel_ = nullptr;
  camCanvas_ = nullptr;
  switch (s) {
    case UI_MAIN: buildMain(); break;
    case UI_PHONE: buildPhone(); break;
    case UI_CALL: buildCall(); break;
    case UI_MESSAGES: buildMessages(); break;
    case UI_COMPOSE: buildCompose(); break;
    case UI_GAMES_MENU: buildGamesMenu(); break;
    case UI_SETTINGS: buildSettings(); break;
    case UI_SET_SECURITY: buildSetSecurity(); break;
    case UI_SET_NETWORK: buildSetNetwork(); break;
    case UI_SET_ACCOUNTS: buildSetAccounts(); break;
    case UI_SET_SOUNDS: buildSetSounds(); break;
    case UI_SET_ABOUT: buildSetAbout(); break;
    case UI_HELP: buildHelp(); break;
    case UI_COMM: buildComm(); break;
    case UI_GALLERY: buildGallery(); break;
    case UI_RECORDER: buildRecorder(); break;
    case UI_RINGTONE: buildRingtone(); break;
    case UI_CAMERA: buildCamera(); break;
    case UI_MUSIC: buildMusic(); break;
    case UI_EBOOKS: buildEbooks(); break;
    case UI_EBOOK_READ: buildEbookRead(); break;
    case UI_AUDIOBOOKS: buildAudiobooks(); break;
    case UI_VIDEO: buildVideo(); break;
    case UI_VIDEO_PLAY: buildVideoPlay(); break;
    case UI_GPS: buildGps(); break;
    case UI_NOTES: buildNotes(); break;
    case UI_NOTE_EDIT: buildNoteEdit(); break;
    case UI_TODOS: buildTodos(); break;
    case UI_LOCK: buildLock(); break;
    case UI_CONTACTS: buildContacts(); break;
    case UI_CONTACT_EDIT: buildContactEdit(); break;
    case UI_CALL_LOG: buildCallLog(); break;
    case UI_SMS_THREADS: buildSmsThreads(); break;
    case UI_SMS_THREAD: buildSmsThread(); break;
    case UI_NOTIFS: buildNotifs(); break;
    case UI_CLOCK: buildClock(); break;
    case UI_ALARMS: buildAlarms(); break;
    case UI_TOOLS: buildTools(); break;
    case UI_CALC: buildCalc(); break;
    case UI_CONVERT: buildConvert(); break;
    case UI_WEATHER: buildWeather(); break;
    case UI_CALENDAR: buildCalendar(); break;
    case UI_MEDIA: buildMedia(); break;
    case UI_EMAIL: buildEmail(); break;
    case UI_EMAIL_READ: buildEmailRead(); break;
    case UI_BROWSER: buildBrowser(); break;
    case UI_GAME_SNAKE:
    case UI_GAME_PONG:
    case UI_GAME_TETRIS: {
      canvasBuf_ = (lv_color_t*)heap_caps_malloc(
          Games::FB_W * Games::FB_H * sizeof(lv_color_t), MALLOC_CAP_SPIRAM);
      if (!canvasBuf_)
        canvasBuf_ = (lv_color_t*)malloc(Games::FB_W * Games::FB_H *
                                         sizeof(lv_color_t));
      canvas_ = lv_canvas_create(rootContent_);
      lv_canvas_set_buffer(canvas_, canvasBuf_, Games::FB_W, Games::FB_H,
                           LV_IMG_CF_TRUE_COLOR);
      lv_obj_center(canvas_);
      GameId gid = GAME_SNAKE;
      if (s == UI_GAME_PONG) gid = GAME_PONG;
      if (s == UI_GAME_TETRIS) gid = GAME_TETRIS;
      g_games.start(gid);
      break;
    }
    case UI_GAME_SOLITAIRE: buildSolitaire(); break;
    case UI_GAME_UNO: buildUno(); break;
    case UI_LORA: buildLora(); break;
  }
  syncPointerUi();
}

void Ui::updateStatusBar(const PhoneStatus& st) {
  if (!statusLabel_) return;

  auto setIcon = [](lv_obj_t* img, const lv_img_dsc_t* dsc) {
    if (!img) return;
    if (dsc) {
      lv_img_set_src(img, dsc);
      lv_obj_clear_flag(img, LV_OBJ_FLAG_HIDDEN);
    } else {
      lv_obj_add_flag(img, LV_OBJ_FLAG_HIDDEN);
    }
  };
  setIcon(statusSigImg_, statusIconSignal(st.signalBars));
  setIcon(statusBatImg_,
          statusIconBattery(st.batteryPercent, st.chargeStatus));
  setIcon(statusBtImg_, statusIconBt(g_settings.get().btEnabled));

  const bool haveSigIcon = statusSigImg_ &&
                           !lv_obj_has_flag(statusSigImg_, LV_OBJ_FLAG_HIDDEN);
  const bool haveBatIcon = statusBatImg_ &&
                           !lv_obj_has_flag(statusBatImg_, LV_OBJ_FLAG_HIDDEN);

  char line[140];
  const char* reg = st.airplaneMode ? "AIR" : (st.registered ? "4G" : "--");
  int unread = g_smsStore.totalUnread() + g_notifs.unread();
  int miss = g_callLog.missedUnread();
  const char* chg =
      st.chargeStatus == 1 ? "+" : (st.chargeStatus == 2 ? "=" : "");
  const char* net =
      locked_ ? "LOCK"
              : (st.sipRegistered ? "SIP" : (st.pdpActive ? "PDP" : ""));

  char sig[6];
  {
    int b = st.signalBars;
    if (b < 0) b = 0;
    if (b > 4) b = 4;
    memset(sig, '|', (size_t)b);
    sig[b] = 0;
    if (!b) {
      sig[0] = '.';
      sig[1] = 0;
    }
  }

  if (haveSigIcon && haveBatIcon) {
    if (miss > 0)
      snprintf(line, sizeof(line), "%s m:%d !%d %s", reg, unread, miss, net);
    else
      snprintf(line, sizeof(line), "%s m:%d %s", reg, unread, net);
  } else if (miss > 0) {
    snprintf(line, sizeof(line), "%s [%s] %d%%%s m:%d !%d %s", reg, sig,
             st.batteryPercent, chg, unread, miss, net);
  } else {
    snprintf(line, sizeof(line), "%s [%s] %d%%%s m:%d %s", reg, sig,
             st.batteryPercent, chg, unread, net);
  }
  lv_label_set_text(statusLabel_, line);
}

void Ui::setCallUi(CallState state, const char* remote, uint32_t seconds) {
  if (screen_ != UI_CALL) {
    showScreen(UI_CALL);
    return;
  }
  (void)state;
  (void)remote;
  lv_obj_t* timer = (lv_obj_t*)lv_obj_get_user_data(rootContent_);
  if (timer) {
    char tbuf[32];
    snprintf(tbuf, sizeof(tbuf), "%02u:%02u", seconds / 60, seconds % 60);
    lv_label_set_text(timer, tbuf);
  }
}

void Ui::notifyIncoming(const char* from) {
  statusLock();
  strncpy(g_status.callerId, from, sizeof(g_status.callerId) - 1);
  statusUnlock();
  // Show contact name if known
  const char* nm = g_contacts.nameForNumber(from);
  if (nm && nm[0]) {
    statusLock();
    snprintf(g_status.callerId, sizeof(g_status.callerId), "%s", nm);
    statusUnlock();
  }
  phonePlayRingtone();
  showScreen(UI_CALL);
}

void Ui::appendDialChar(char c) {
  size_t n = strlen(dial_);
  if (n + 1 < sizeof(dial_)) {
    dial_[n] = c;
    dial_[n + 1] = 0;
  }
}

void Ui::backspaceDial() {
  size_t n = strlen(dial_);
  if (n) dial_[n - 1] = 0;
}

void Ui::clearDial() { dial_[0] = 0; }

const char* Ui::dialBuffer() const { return dial_; }

static bool containsInsensitive(const char* hay, const char* needle) {
  if (!needle || !needle[0]) return true;
  if (!hay) return false;
  size_t nlen = strlen(needle);
  for (const char* p = hay; *p; p++) {
    size_t i = 0;
    while (i < nlen && p[i] &&
           tolower((unsigned char)p[i]) == tolower((unsigned char)needle[i]))
      i++;
    if (i == nlen) return true;
  }
  return false;
}

static void styleFocus(lv_obj_t* obj, bool on) {
  if (!obj) return;
  lv_obj_set_style_outline_width(obj, on ? 3 : 0, 0);
  lv_obj_set_style_outline_color(obj, lv_color_hex(0x58a6ff), 0);
}

static int16_t s_ptrX = TFT_WIDTH_PX / 2;
static int16_t s_ptrY = TFT_HEIGHT_PX / 2;
static bool s_ptrPressed = false;

static void pointer_read_cb(lv_indev_drv_t*, lv_indev_data_t* data) {
  data->point.x = s_ptrX;
  data->point.y = s_ptrY;
  data->state = s_ptrPressed ? LV_INDEV_STATE_PRESSED : LV_INDEV_STATE_RELEASED;
}

void Ui::setupPointer() {
  static lv_indev_drv_t indev_drv;
  lv_indev_drv_init(&indev_drv);
  indev_drv.type = LV_INDEV_TYPE_POINTER;
  indev_drv.read_cb = pointer_read_cb;
  ptrIndev_ = lv_indev_drv_register(&indev_drv);

  cursorObj_ = lv_label_create(lv_scr_act());
  lv_label_set_text(cursorObj_, ">");
  lv_obj_set_style_text_font(cursorObj_, &lv_font_montserrat_28, 0);
  lv_obj_set_style_text_color(cursorObj_, lv_color_hex(0xffffff), 0);
  lv_obj_set_style_text_opa(cursorObj_, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_opa(cursorObj_, LV_OPA_TRANSP, 0);
  lv_obj_clear_flag(cursorObj_, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_flag(cursorObj_, LV_OBJ_FLAG_FLOATING);
  lv_indev_set_cursor(ptrIndev_, cursorObj_);
  lv_obj_add_flag(cursorObj_, LV_OBJ_FLAG_HIDDEN);
}

bool Ui::usesPointer() const {
  switch (screen_) {
    case UI_MAIN:
    case UI_COMM:
    case UI_TOOLS:
    case UI_MEDIA:
    case UI_GAMES_MENU:
    case UI_SETTINGS:
    case UI_SET_SECURITY:
    case UI_SET_NETWORK:
    case UI_SET_ACCOUNTS:
    case UI_SET_SOUNDS:
    case UI_SET_ABOUT:
    case UI_HELP:
    case UI_MUSIC:
    case UI_EBOOKS:
    case UI_AUDIOBOOKS:
    case UI_GALLERY:
    case UI_RINGTONE:
    case UI_VIDEO:
    case UI_CLOCK:
    case UI_RECORDER:
    case UI_GAME_SOLITAIRE:
    case UI_GAME_UNO:
      return true;
    default:
      return false;
  }
}

void Ui::syncPointerUi() {
  if (!cursorObj_) return;
  if (usesPointer()) {
    lv_obj_clear_flag(cursorObj_, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(cursorObj_);
  } else {
    lv_obj_add_flag(cursorObj_, LV_OBJ_FLAG_HIDDEN);
    if (hoveredBtn_) {
      styleFocus(hoveredBtn_, false);
      hoveredBtn_ = nullptr;
    }
  }
}

void Ui::nudgeCursor(int dx, int dy) {
  s_ptrX = (int16_t)constrain((int)s_ptrX + dx, 0, TFT_WIDTH_PX - 1);
  s_ptrY = (int16_t)constrain((int)s_ptrY + dy, 0, TFT_HEIGHT_PX - 1);
  updatePointerHover();
}

void Ui::pointerClick() {
  s_ptrPressed = true;
  lv_timer_handler();
  s_ptrPressed = false;
  lv_timer_handler();
}

void Ui::updatePointerHover() {
  if (!usesPointer() || focusCount_ <= 0) return;
  lv_obj_t* hit = nullptr;
  for (int i = 0; i < focusCount_; i++) {
    lv_obj_t* o = focusables_[i];
    if (!o) continue;
    lv_area_t a;
    lv_obj_get_coords(o, &a);
    if (s_ptrX >= a.x1 && s_ptrX <= a.x2 && s_ptrY >= a.y1 && s_ptrY <= a.y2) {
      hit = o;
      break;
    }
  }
  if (hit == hoveredBtn_) return;
  if (hoveredBtn_) styleFocus(hoveredBtn_, false);
  hoveredBtn_ = hit;
  if (hoveredBtn_) styleFocus(hoveredBtn_, true);
}

void Ui::moveFocus(int delta) {
  if (focusCount_ <= 0) return;
  styleFocus(focusables_[focusIndex_], false);
  int next = focusIndex_ + delta;
  while (next < 0) next += focusCount_;
  focusIndex_ = next % focusCount_;
  styleFocus(focusables_[focusIndex_], true);
}

void Ui::activateFocus() {
  if (focusCount_ <= 0 || !focusables_[focusIndex_]) return;
  lv_event_send(focusables_[focusIndex_], LV_EVENT_CLICKED, nullptr);
}

void Ui::buildMain() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_ROW_WRAP);
  lv_obj_set_flex_align(rootContent_, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START,
                        LV_FLEX_ALIGN_START);
  lv_obj_set_style_pad_row(rootContent_, 8, 0);
  lv_obj_set_style_pad_column(rootContent_, 8, 0);

  lv_obj_t* title = lv_label_create(rootContent_);
  lv_label_set_text(title, "ESP Phone");
  lv_obj_set_style_text_font(title, &lv_font_montserrat_28, 0);
  lv_obj_set_width(title, TFT_WIDTH_PX - 16);

  auto add = [&](const char* name, UiScreen dest) {
    if (focusCount_ >= 32) return;
    auto cb = [](lv_event_t* e) {
      UiScreen s = (UiScreen)(uintptr_t)lv_event_get_user_data(e);
      g_ui.showScreen(s);
    };
    lv_obj_t* btn = makeAppBtn(rootContent_, name, dest, cb);
    lv_obj_set_width(btn, 148);
    focusables_[focusCount_++] = btn;
  };
  add("Phone / Comm", UI_COMM);
  add("Clock", UI_CLOCK);
  add("Calendar", UI_CALENDAR);
  add("Browser", UI_BROWSER);
  add("Tools", UI_TOOLS);
  add("Media", UI_MEDIA);
  add("Games", UI_GAMES_MENU);
  add("Settings", UI_SETTINGS);
  // Pointer mode: no focus ring — cursor starts mid-screen
  s_ptrX = TFT_WIDTH_PX / 2;
  s_ptrY = UI_STATUS_BAR_HEIGHT + 120;
}

void Ui::buildComm() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_ROW_WRAP);
  lv_obj_set_flex_align(rootContent_, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START,
                        LV_FLEX_ALIGN_START);
  lv_obj_set_style_pad_row(rootContent_, 8, 0);
  lv_obj_set_style_pad_column(rootContent_, 8, 0);
  lv_obj_t* title = lv_label_create(rootContent_);
  lv_label_set_text(title, "Communications");
  lv_obj_set_width(title, TFT_WIDTH_PX - 16);
  auto add = [&](const char* name, UiScreen dest) {
    if (focusCount_ >= 32) return;
    auto cb = [](lv_event_t* e) {
      g_ui.showScreen((UiScreen)(uintptr_t)lv_event_get_user_data(e));
    };
    lv_obj_t* btn = makeAppBtn(rootContent_, name, dest, cb);
    lv_obj_set_width(btn, 148);
    focusables_[focusCount_++] = btn;
  };
  add("Phone", UI_PHONE);
  add("Contacts", UI_CONTACTS);
  add("Call Log", UI_CALL_LOG);
  add("Messages", UI_SMS_THREADS);
  add("Notifs", UI_NOTIFS);
  add("Email", UI_EMAIL);
  add("LoRa SOS", UI_LORA);
  lv_obj_t* back = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MAIN); },
      nullptr);
  lv_obj_set_width(back, 148);
  focusables_[focusCount_++] = back;
}

void Ui::buildLora() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_style_pad_row(rootContent_, 6, 0);
  lv_label_set_text(lv_label_create(rootContent_), "LoRa emergency");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  draft_[0] = 0;
  if (!g_lora.isReady()) g_lora.begin();
  refreshLoraUi();
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "SOS NOW", [](lv_event_t*) { g_ui.loraSendSos(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Send text", [](lv_event_t*) { g_ui.loraSendDraft(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Refresh", [](lv_event_t*) { g_ui.refreshLoraUi(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_COMM); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::refreshLoraUi() {
  if (!listLabel_ || screen_ != UI_LORA) return;
  if (!g_lora.isReady()) g_lora.begin();
  char buf[900];
  size_t n = 0;
  uint32_t devId = g_lora.deviceId();
  uint32_t target = g_settings.get().loraTargetId;
  n += snprintf(buf + n, sizeof(buf) - n,
                "Status: %s\nMy ID: %lu (0x%08lX)\nTarget: %s\nDraft: %s\n---\n",
                g_lora.status()[0] ? g_lora.status() : "-",
                (unsigned long)devId, (unsigned long)devId,
                target ? "direct" : "broadcast",
                draft_[0] ? draft_ : "_");
  if (target)
    n += snprintf(buf + n, sizeof(buf) - n, "Target ID: %lu\n---\n",
                  (unsigned long)target);
  int start = g_lora.logCount() > 8 ? g_lora.logCount() - 8 : 0;
  for (int i = start; i < g_lora.logCount() && n + 40 < sizeof(buf); i++) {
    const LoraMsg* m = g_lora.logAt(i);
    if (!m) continue;
    n += snprintf(buf + n, sizeof(buf) - n, "%s %s\n", m->outgoing ? ">" : "<",
                  m->text);
  }
  if (g_lora.logCount() == 0)
    n += snprintf(buf + n, sizeof(buf) - n, "(no traffic yet)");
  lv_label_set_text(listLabel_, buf);
}

void Ui::loraSendDraft() {
  if (!draft_[0]) {
    if (!g_lora.isReady()) g_lora.begin();
    refreshLoraUi();
    return;
  }
  if (g_lora.sendText(draft_)) draft_[0] = 0;
  refreshLoraUi();
}

void Ui::loraSendSos() {
  g_lora.sendSos();
  refreshLoraUi();
}

void Ui::saveLoraDeviceIdFromDraft() {
  if (!draft_[0]) return;
  PhoneSettings& s = g_settings.get();
  s.loraDeviceId = (uint32_t)strtoul(draft_, nullptr, 10);
  g_settings.save();
  draft_[0] = 0;
  g_lora.end();
}

void Ui::saveLoraTargetFromDraft() {
  PhoneSettings& s = g_settings.get();
  if (!draft_[0]) {
    s.loraTargetId = 0;
  } else {
    s.loraTargetId = (uint32_t)strtoul(draft_, nullptr, 10);
  }
  g_settings.save();
  draft_[0] = 0;
}

void Ui::buildPhone() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_style_pad_row(rootContent_, 8, 0);

  lv_obj_t* hint = lv_label_create(rootContent_);
  lv_label_set_text(hint, "Type number (Shift=digits)  CALL/Confirm to dial");

  lv_obj_t* num = lv_label_create(rootContent_);
  lv_label_set_text(num, dial_[0] ? dial_ : "_");
  lv_obj_set_style_text_font(num, &lv_font_montserrat_28, 0);
  lv_obj_set_style_text_color(num, lv_color_hex(0x58a6ff), 0);

  auto dialCb = [](lv_event_t*) {
    if (g_ui.dialBuffer()[0]) g_sip.dial(g_ui.dialBuffer());
    g_ui.showScreen(UI_CALL);
  };
  auto endCb = [](lv_event_t*) { g_sip.hangup(); };
  auto backCb = [](lv_event_t*) { g_ui.showScreen(UI_MAIN); };

  focusables_[focusCount_++] = makeBtn(rootContent_, "Call", dialCb, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "End", endCb, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "Back", backCb, nullptr);
  styleFocus(focusables_[0], true);

  // Keep label updated via user_data pointer stored globally — refresh on key
  lv_obj_set_user_data(rootContent_, num);
}

void Ui::buildCall() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_flex_align(rootContent_, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER,
                        LV_FLEX_ALIGN_CENTER);

  PhoneStatus st;
  statusLock();
  st = g_status;
  statusUnlock();

  const char* stateStr = "Idle";
  switch (st.callState) {
    case CALL_DIALING: stateStr = "Dialing..."; break;
    case CALL_RINGING: stateStr = "Incoming / Ringing"; break;
    case CALL_IN_CALL: stateStr = "In call"; break;
    case CALL_ENDED: stateStr = "Ended"; break;
    default: break;
  }

  lv_obj_t* stLab = lv_label_create(rootContent_);
  lv_label_set_text(stLab, stateStr);
  lv_obj_set_style_text_font(stLab, &lv_font_montserrat_20, 0);

  lv_obj_t* id = lv_label_create(rootContent_);
  lv_label_set_text(id, st.callerId[0] ? st.callerId : st.dialBuffer);
  lv_obj_set_style_text_font(id, &lv_font_montserrat_16, 0);

  char tbuf[32];
  snprintf(tbuf, sizeof(tbuf), "%02u:%02u", st.callSeconds / 60,
           st.callSeconds % 60);
  lv_obj_t* timer = lv_label_create(rootContent_);
  lv_label_set_text(timer, tbuf);
  lv_obj_set_user_data(rootContent_, timer);

  auto ans = [](lv_event_t*) {
    g_media.stop();
    g_sip.answer();
  };
  auto reject = [](lv_event_t*) { g_ui.rejectCall(); };
  auto end = [](lv_event_t*) {
    g_media.stop();
    g_sip.hangup();
    g_ui.showScreen(UI_PHONE);
  };
  if (st.callState == CALL_RINGING) {
    focusables_[focusCount_++] = makeBtn(rootContent_, "Answer", ans, nullptr);
    focusables_[focusCount_++] =
        makeBtn(rootContent_, "Reject", reject, nullptr);
  }
  focusables_[focusCount_++] = makeBtn(rootContent_, "End Call", end, nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildMessages() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_obj_t* title = lv_label_create(rootContent_);
  lv_label_set_text(title, "Messages");

  SmsMessage msgs[8];
  int n = g_modem.listSms(msgs, 8);
  lv_obj_t* list = lv_list_create(rootContent_);
  lv_obj_set_size(list, TFT_WIDTH_PX - 24, 240);
  if (n == 0) {
    lv_list_add_text(list, "(empty — inbox via AT+CMGL)");
  } else {
    for (int i = 0; i < n; i++) {
      char line[96];
      snprintf(line, sizeof(line), "%s: %.40s", msgs[i].number, msgs[i].text);
      lv_list_add_btn(list, nullptr, line);
    }
  }

  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Compose",
      [](lv_event_t*) { g_ui.showScreen(UI_COMPOSE); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MAIN); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildCompose() {
  composeFocusTo_ = true;
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_obj_t* h = lv_label_create(rootContent_);
  lv_label_set_text(h, "Shift+letters=digits. Confirm: To->Msg->Send. Bksp=back");

  lv_obj_t* toLab = lv_label_create(rootContent_);
  lv_label_set_text_fmt(toLab, "To: %s", composeTo_[0] ? composeTo_ : "_");
  s_composeToLab = toLab;

  lv_obj_t* body = lv_textarea_create(rootContent_);
  lv_obj_set_size(body, TFT_WIDTH_PX - 24, 160);
  lv_textarea_set_text(body, compose_);
  lv_textarea_set_max_length(body, sizeof(compose_) - 1);

  // user_data on root: [0]=body textarea pointer stored via child index — keep body in user_data
  lv_obj_set_user_data(rootContent_, body);

  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Send SMS",
      [](lv_event_t*) { g_ui.sendComposeSms(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_SMS_THREADS); },
      nullptr);
  styleFocus(focusables_[0], true);
}

bool Ui::sendComposeSms() {
  if (!composeTo_[0] || !compose_[0]) return false;
  if (!g_modem.sendSms(composeTo_, compose_)) {
    g_notifs.push(NOTIF_INFO, "SMS failed", composeTo_);
    return false;
  }
  g_smsStore.addOutbound(composeTo_, compose_);
  Storage::appendSmsLog("OUT", composeTo_, compose_);
  g_notifs.push(NOTIF_INFO, "SMS sent", composeTo_);
  compose_[0] = 0;
  composeTo_[0] = 0;
  showScreen(UI_SMS_THREADS);
  return true;
}

void Ui::setComposeToDigit(char c) {
  size_t n = strlen(composeTo_);
  if (n + 1 < sizeof(composeTo_)) {
    composeTo_[n] = c;
    composeTo_[n + 1] = 0;
  }
  if (s_composeToLab)
    lv_label_set_text_fmt(s_composeToLab, "To: %s",
                          composeTo_[0] ? composeTo_ : "_");
}

void Ui::appendComposeBody(char c) {
  size_t n = strlen(compose_);
  if (n + 1 < sizeof(compose_)) {
    compose_[n] = c;
    compose_[n + 1] = 0;
  }
}

void Ui::buildGamesMenu() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_ROW_WRAP);
  lv_obj_set_flex_align(rootContent_, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START,
                        LV_FLEX_ALIGN_START);
  lv_obj_set_style_pad_row(rootContent_, 8, 0);
  lv_obj_set_style_pad_column(rootContent_, 8, 0);
  lv_obj_t* title = lv_label_create(rootContent_);
  lv_label_set_text(title, "Games");
  lv_obj_set_style_text_font(title, &lv_font_montserrat_28, 0);
  lv_obj_set_width(title, TFT_WIDTH_PX - 16);
  auto add = [&](const char* name, UiScreen dest) {
    if (focusCount_ >= 32) return;
    auto cb = [](lv_event_t* e) {
      g_ui.showScreen((UiScreen)(uintptr_t)lv_event_get_user_data(e));
    };
    lv_obj_t* btn = makeAppBtn(rootContent_, name, dest, cb);
    lv_obj_set_width(btn, 148);
    focusables_[focusCount_++] = btn;
  };
  add("Snake", UI_GAME_SNAKE);
  add("Pong", UI_GAME_PONG);
  add("Tetris", UI_GAME_TETRIS);
  add("Solitaire", UI_GAME_SOLITAIRE);
  add("Uno", UI_GAME_UNO);
  lv_obj_t* back = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MAIN); },
      nullptr);
  lv_obj_set_width(back, 148);
  focusables_[focusCount_++] = back;
}

void Ui::refreshFileListLabel() {
  if (!fileLabel_) return;
  if (fileCount_ <= 0) {
    lv_label_set_text(fileLabel_, "(no files on SD — see folder note)");
    return;
  }
  const char* p = fileList_[fileIndex_];
  const char* base = strrchr(p, '/');
  base = base ? base + 1 : p;
  char line[128];
  snprintf(line, sizeof(line), "%d/%d  %s", fileIndex_ + 1, fileCount_, base);
  lv_label_set_text(fileLabel_, line);
}

void Ui::cameraTick() {
  if (!g_camera.isActive() || !camCanvas_ || !camBuf_) return;
  int w = 0, h = 0;
  if (!g_camera.captureRgb565((uint16_t*)camBuf_, CAM_W, CAM_H, &w, &h)) return;
  lv_obj_invalidate(camCanvas_);
}

void Ui::buildCamera() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_obj_t* tip = lv_label_create(rootContent_);
  lv_label_set_text(tip, "OV2640  Snap=GPIO1  Back=GPIO42\nEnable CAM DIP  (matrix paused)");

  if (!camBuf_) {
    camBuf_ = (lv_color_t*)heap_caps_malloc(CAM_W * CAM_H * sizeof(lv_color_t),
                                            MALLOC_CAP_SPIRAM);
    if (!camBuf_)
      camBuf_ = (lv_color_t*)malloc(CAM_W * CAM_H * sizeof(lv_color_t));
  }
  camCanvas_ = lv_canvas_create(rootContent_);
  lv_canvas_set_buffer(camCanvas_, camBuf_, CAM_W, CAM_H, LV_IMG_CF_TRUE_COLOR);
  lv_obj_set_size(camCanvas_, CAM_W, CAM_H);

  if (!g_camera.begin()) {
    lv_obj_t* err = lv_label_create(rootContent_);
    lv_label_set_text(err, "Camera init failed");
  }

  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Snap to SD",
      [](lv_event_t*) { g_ui.snapCamera(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back",
      [](lv_event_t*) { g_ui.showScreen(UI_MAIN); }, nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildMusic() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_obj_t* h = lv_label_create(rootContent_);
  lv_label_set_text(h, "Music  SD:/music\nCursor · Confirm click");

  fileCount_ = g_media.listFiles(MUSIC_DIR, fileList_, MEDIA_MAX_FILES, ".mp3");
  fileIndex_ = 0;
  fileLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(fileLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(fileLabel_, TFT_WIDTH_PX - 24);
  refreshFileListLabel();

  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Prev", [](lv_event_t*) { g_ui.selectFileDelta(-1); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Next", [](lv_event_t*) { g_ui.selectFileDelta(1); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Play / Pause",
      [](lv_event_t*) { g_ui.playSelectedMusic(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Stop", [](lv_event_t*) { g_media.stop(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MEDIA); },
      nullptr);
}

void Ui::buildAudiobooks() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_obj_t* h = lv_label_create(rootContent_);
  lv_label_set_text(h, "Audiobooks  SD:/audiobooks\nCursor · Confirm click");

  fileCount_ =
      g_media.listFiles(AUDIOBOOK_DIR, fileList_, MEDIA_MAX_FILES, ".mp3");
  fileIndex_ = 0;
  fileLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(fileLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(fileLabel_, TFT_WIDTH_PX - 24);
  refreshFileListLabel();

  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Prev", [](lv_event_t*) { g_ui.selectFileDelta(-1); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Next", [](lv_event_t*) { g_ui.selectFileDelta(1); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Play / Pause",
      [](lv_event_t*) { g_ui.playSelectedAudiobook(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Stop", [](lv_event_t*) { g_media.stop(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MEDIA); },
      nullptr);
}

void Ui::buildEbooks() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_obj_t* h = lv_label_create(rootContent_);
  lv_label_set_text(h, "Ebooks  SD:/books\nCursor · Confirm click");

  fileCount_ = g_ebook.listBooks(fileList_, MEDIA_MAX_FILES);
  fileIndex_ = 0;
  fileLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(fileLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(fileLabel_, TFT_WIDTH_PX - 24);
  refreshFileListLabel();

  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Prev", [](lv_event_t*) { g_ui.selectFileDelta(-1); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Next", [](lv_event_t*) { g_ui.selectFileDelta(1); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Open",
      [](lv_event_t*) { g_ui.openSelectedEbook(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MEDIA); },
      nullptr);
}

void Ui::buildEbookRead() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  char hdr[48];
  snprintf(hdr, sizeof(hdr), "Page %d / %d  (L/R pages)", g_ebook.pageIndex() + 1,
           g_ebook.pageCount());
  lv_obj_t* h = lv_label_create(rootContent_);
  lv_label_set_text(h, hdr);

  lv_obj_t* body = lv_label_create(rootContent_);
  lv_label_set_long_mode(body, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(body, TFT_WIDTH_PX - 24);
  char page[EBOOK_PAGE_CHARS + 1];
  if (g_ebook.pageText(page, sizeof(page)))
    lv_label_set_text(body, page);
  else
    lv_label_set_text(body, "(empty)");
  lv_obj_set_user_data(rootContent_, body);

  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back",
      [](lv_event_t*) {
        g_ebook.close();
        g_ui.showScreen(UI_EBOOKS);
      },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::refreshEbookPage() {
  lv_obj_t* body = (lv_obj_t*)lv_obj_get_user_data(rootContent_);
  if (!body) return;
  char page[EBOOK_PAGE_CHARS + 1];
  if (g_ebook.pageText(page, sizeof(page))) lv_label_set_text(body, page);
}

void Ui::refreshListLabel() {
  if (!listLabel_) return;
  if (screen_ == UI_NOTES) {
    if (g_notes.count() <= 0) {
      lv_label_set_text(listLabel_, "(no notes — Confirm=open/new)");
      return;
    }
    if (listIndex_ >= g_notes.count()) listIndex_ = g_notes.count() - 1;
    const NoteItem* n = g_notes.at(listIndex_);
    char line[160];
    snprintf(line, sizeof(line), "%d/%d  %s", listIndex_ + 1, g_notes.count(),
             n ? n->title : "?");
    lv_label_set_text(listLabel_, line);
  } else if (screen_ == UI_TODOS) {
    if (g_todos.count() <= 0) {
      lv_label_set_text(listLabel_, "(empty — type then Confirm to add)");
      return;
    }
    if (listIndex_ >= g_todos.count()) listIndex_ = g_todos.count() - 1;
    const TodoItem* t = g_todos.at(listIndex_);
    char line[160];
    snprintf(line, sizeof(line), "%d/%d  [%c] %s", listIndex_ + 1,
             g_todos.count(), (t && t->done) ? 'x' : ' ', t ? t->text : "?");
    lv_label_set_text(listLabel_, line);
  } else if (screen_ == UI_CONTACTS) {
    if (g_contacts.count() <= 0) {
      lv_label_set_text(listLabel_, "(no contacts)");
      return;
    }
    if (listIndex_ >= g_contacts.count()) listIndex_ = g_contacts.count() - 1;
    const Contact* c = g_contacts.at(listIndex_);
    char ini[3];
    Contacts::initials(c->name, ini);
    char line[160];
    snprintf(line, sizeof(line), "%d/%d [%s]%s %s\n%s", listIndex_ + 1,
             g_contacts.count(), ini, c->favorite ? "*" : " ", c->name,
             c->number);
    lv_label_set_text(listLabel_, line);
  } else if (screen_ == UI_CALL_LOG) {
    if (g_callLog.count() <= 0) {
      lv_label_set_text(listLabel_, "(empty)");
      return;
    }
    if (listIndex_ >= g_callLog.count()) listIndex_ = g_callLog.count() - 1;
    const CallLogEntry* e = g_callLog.at(listIndex_);
    const char* dir =
        e->dir == CALL_MISSED ? "MISS" : (e->dir == CALL_IN ? "IN" : "OUT");
    char line[160];
    snprintf(line, sizeof(line), "%d/%d [%s] %s\n%s %us", listIndex_ + 1,
             g_callLog.count(), dir, e->name[0] ? e->name : e->number, e->number,
             (unsigned)e->durationSec);
    lv_label_set_text(listLabel_, line);
  } else if (screen_ == UI_SMS_THREADS) {
    int tc = g_smsStore.threadCount();
    if (tc <= 0) {
      lv_label_set_text(listLabel_, "(no threads — Compose)");
      return;
    }
    // Optional search filter in draft_
    int visible = 0;
    int matchIdx = -1;
    for (int i = 0; i < tc; i++) {
      const SmsThread* t = g_smsStore.threadAt(i);
      if (draft_[0]) {
        if (!containsInsensitive(t->name, draft_) &&
            !containsInsensitive(t->number, draft_))
          continue;
      }
      if (visible == listIndex_) matchIdx = i;
      visible++;
    }
    if (visible <= 0) {
      lv_label_set_text_fmt(listLabel_, "No match for \"%s\"", draft_);
      return;
    }
    if (listIndex_ >= visible) listIndex_ = visible - 1;
    // re-find matchIdx after clamp
    visible = 0;
    matchIdx = 0;
    for (int i = 0; i < tc; i++) {
      const SmsThread* t = g_smsStore.threadAt(i);
      if (draft_[0] && !containsInsensitive(t->name, draft_) &&
          !containsInsensitive(t->number, draft_))
        continue;
      if (visible == listIndex_) {
        matchIdx = i;
        break;
      }
      visible++;
    }
    const SmsThread* t = g_smsStore.threadAt(matchIdx);
    smsThreadIndex_ = matchIdx;
    char line[200];
    snprintf(line, sizeof(line), "%d/%d %s (%d new)\n%.60s%s", listIndex_ + 1,
             visible, t->name, t->unread,
             t->msgCount ? t->msgs[t->msgCount - 1].text : "",
             draft_[0] ? "\n(filter active)" : "");
    lv_label_set_text(listLabel_, line);
  } else if (screen_ == UI_NOTIFS) {
    if (g_notifs.count() <= 0) {
      lv_label_set_text(listLabel_, "(none)");
      return;
    }
    if (listIndex_ >= g_notifs.count()) listIndex_ = g_notifs.count() - 1;
    const Notification* n = g_notifs.at(listIndex_);
    char line[160];
    snprintf(line, sizeof(line), "%d/%d  %s\n%s", listIndex_ + 1, g_notifs.count(),
             n->title, n->body);
    lv_label_set_text(listLabel_, line);
  } else if (screen_ == UI_ALARMS) {
    if (g_clock.count() <= 0) {
      lv_label_set_text(listLabel_, "(no alarms)");
      return;
    }
    if (listIndex_ >= g_clock.count()) listIndex_ = g_clock.count() - 1;
    const Alarm* a = g_clock.at(listIndex_);
    char line[120];
    snprintf(line, sizeof(line), "%d/%d  %s %02u:%02u  %s", listIndex_ + 1,
             g_clock.count(), a->enabled ? "ON " : "off", (unsigned)a->hour,
             (unsigned)a->minute, a->label);
    lv_label_set_text(listLabel_, line);
  } else if (screen_ == UI_CALENDAR) {
    if (g_calendar.count() <= 0) {
      lv_label_set_text(listLabel_, "(no events — Add today)");
      return;
    }
    if (listIndex_ >= g_calendar.count()) listIndex_ = g_calendar.count() - 1;
    const CalEvent* e = g_calendar.at(listIndex_);
    char line[140];
    snprintf(line, sizeof(line), "%d/%d  %04d-%02d-%02d %02u:%02u\n%s%s",
             listIndex_ + 1, g_calendar.count(), e->year, e->month, e->day,
             (unsigned)e->hour, (unsigned)e->minute, e->synced ? "[G] " : "",
             e->title);
    lv_label_set_text(listLabel_, line);
  } else if (screen_ == UI_EMAIL) {
    if (g_email.count() <= 0) {
      lv_label_set_text_fmt(listLabel_, "%s\n(no messages — Refresh)",
                            g_email.status());
      return;
    }
    if (listIndex_ >= g_email.count()) listIndex_ = g_email.count() - 1;
    const EmailItem* m = g_email.at(listIndex_);
    char line[200];
    snprintf(line, sizeof(line), "%d/%d  %.40s\n%.60s", listIndex_ + 1,
             g_email.count(), m->from, m->subject);
    lv_label_set_text(listLabel_, line);
  }
}

void Ui::refreshGpsLabel() {
  if (!gpsLabel_) return;
  char line[192];
  if (!g_gps.isOn()) {
    lv_label_set_text(
        gpsLabel_,
        "GNSS off\nConfirm = power on\nNeeds GNSS antenna (IPEX)");
    return;
  }
  const GpsFix& f = g_gps.fix();
  if (!f.valid) {
    lv_label_set_text(
        gpsLabel_, "Searching for satellites...\nGo outdoors, wait 30-120s");
    return;
  }
  snprintf(line, sizeof(line),
           "FIX OK\nLat %.5f\nLon %.5f\nAlt %.1f m\nUTC %s", f.lat, f.lon,
           (double)f.altitudeM, f.utcTime[0] ? f.utcTime : "--");
  lv_label_set_text(gpsLabel_, line);
}

void Ui::gpsToggle() {
  if (g_gps.isOn())
    g_gps.end();
  else
    g_gps.begin();
  refreshGpsLabel();
}

void Ui::todoToggleSelected() {
  if (g_todos.count() > 0) {
    g_todos.toggle(listIndex_);
    refreshListLabel();
  }
}

void Ui::todoAddDraft() {
  if (draft_[0] && g_todos.add(draft_)) {
    draft_[0] = 0;
    listIndex_ = g_todos.count() - 1;
    refreshListLabel();
    lv_obj_t* draftLab = (lv_obj_t*)lv_obj_get_user_data(rootContent_);
    if (draftLab) lv_label_set_text(draftLab, "New: _");
  }
}

void Ui::todoDeleteSelected() {
  if (g_todos.count() > 0) {
    g_todos.remove(listIndex_);
    if (listIndex_ >= g_todos.count() && listIndex_ > 0) listIndex_--;
    refreshListLabel();
  }
}

void Ui::notesOpenSelected() {
  if (g_notes.count() <= 0) {
    notesNew();
    return;
  }
  noteEditIndex_ = listIndex_;
  const NoteItem* n = g_notes.at(listIndex_);
  if (n) {
    strncpy(draftTitle_, n->title, sizeof(draftTitle_) - 1);
    strncpy(draft_, n->body, sizeof(draft_) - 1);
  }
  draftFocusTitle_ = false;
  showScreen(UI_NOTE_EDIT);
}

void Ui::notesNew() {
  noteEditIndex_ = -1;
  draftTitle_[0] = 0;
  draft_[0] = 0;
  draftFocusTitle_ = true;
  showScreen(UI_NOTE_EDIT);
}

void Ui::notesSaveEdit() {
  if (noteEditIndex_ < 0)
    g_notes.add(draftTitle_, draft_);
  else
    g_notes.update(noteEditIndex_, draftTitle_, draft_);
  showScreen(UI_NOTES);
}

void Ui::notesDeleteSelected() {
  if (g_notes.count() > 0) {
    g_notes.remove(listIndex_);
    if (listIndex_ >= g_notes.count() && listIndex_ > 0) listIndex_--;
    refreshListLabel();
  }
}

void Ui::buildGps() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_obj_t* h = lv_label_create(rootContent_);
  lv_label_set_text(h, "GPS / GNSS (SIM7670G)\nConnect antenna to GNSS IPEX");

  gpsLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(gpsLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(gpsLabel_, TFT_WIDTH_PX - 24);
  refreshGpsLabel();

  focusables_[focusCount_++] = makeBtn(
      rootContent_, "On / Off", [](lv_event_t*) { g_ui.gpsToggle(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Refresh",
      [](lv_event_t*) {
        g_gps.poll();
        g_ui.refreshGpsUi();
      },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "SMS location", [](lv_event_t*) { g_ui.shareLocationSms(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MEDIA); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildNotes() {
  g_notes.load();
  listIndex_ = 0;
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_obj_t* h = lv_label_create(rootContent_);
  lv_label_set_text(h, "Notes  Up/Down  Confirm=open");

  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  refreshListLabel();

  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Open", [](lv_event_t*) { g_ui.notesOpenSelected(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "New", [](lv_event_t*) { g_ui.notesNew(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Delete", [](lv_event_t*) { g_ui.notesDeleteSelected(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MAIN); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildNoteEdit() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_obj_t* h = lv_label_create(rootContent_);
  lv_label_set_text(h, "Edit  Confirm: title->body->save");

  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  char line[600];
  snprintf(line, sizeof(line), "Title: %s\n\n%s",
           draftTitle_[0] ? draftTitle_ : "_", draft_[0] ? draft_ : "_");
  lv_label_set_text(listLabel_, line);

  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Save", [](lv_event_t*) { g_ui.notesSaveEdit(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_NOTES); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildTodos() {
  g_todos.load();
  listIndex_ = 0;
  draft_[0] = 0;
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_obj_t* h = lv_label_create(rootContent_);
  lv_label_set_text(h, "Todos  type+Confirm=add  Confirm=toggle");

  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  refreshListLabel();

  lv_obj_t* draftLab = lv_label_create(rootContent_);
  lv_label_set_text(draftLab, "New: _");
  lv_obj_set_user_data(rootContent_, draftLab);

  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Toggle", [](lv_event_t*) { g_ui.todoToggleSelected(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Add draft", [](lv_event_t*) { g_ui.todoAddDraft(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Delete", [](lv_event_t*) { g_ui.todoDeleteSelected(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MAIN); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildSettings() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_ROW_WRAP);
  lv_obj_set_flex_align(rootContent_, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START,
                        LV_FLEX_ALIGN_START);
  lv_obj_set_style_pad_row(rootContent_, 8, 0);
  lv_obj_set_style_pad_column(rootContent_, 8, 0);
  lv_obj_t* title = lv_label_create(rootContent_);
  lv_label_set_text(title, "Settings");
  lv_obj_set_style_text_font(title, &lv_font_montserrat_28, 0);
  lv_obj_set_width(title, TFT_WIDTH_PX - 16);
  auto add = [&](const char* name, UiScreen dest) {
    if (focusCount_ >= 32) return;
    lv_obj_t* btn = makeBtn(
        rootContent_, name,
        [](lv_event_t* e) {
          g_ui.showScreen((UiScreen)(uintptr_t)lv_event_get_user_data(e));
        },
        (void*)(uintptr_t)dest);
    lv_obj_set_width(btn, 148);
    focusables_[focusCount_++] = btn;
  };
  add("Security", UI_SET_SECURITY);
  add("Network", UI_SET_NETWORK);
  add("Accounts", UI_SET_ACCOUNTS);
  add("Sounds", UI_SET_SOUNDS);
  add("About", UI_SET_ABOUT);
  add("Help", UI_HELP);
  lv_obj_t* back = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MAIN); },
      nullptr);
  lv_obj_set_width(back, 148);
  focusables_[focusCount_++] = back;
}

void Ui::buildSetSecurity() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_), "Security");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  char line[160];
  snprintf(line, sizeof(line),
           "PIN: %s\nTimeout: %lus\nType digits then Confirm to set PIN",
           g_settings.get().lockEnabled ? "ON" : "off",
           (unsigned long)g_settings.get().lockTimeoutSec);
  lv_label_set_text(listLabel_, line);
  draft_[0] = 0;
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Clear PIN", [](lv_event_t*) { g_ui.clearPin(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Cycle lock timeout",
      [](lv_event_t*) { g_ui.cycleLockTimeout(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Lock now", [](lv_event_t*) { g_ui.lockNow(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_SETTINGS); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildSetNetwork() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_), "Network");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  refreshNetworkStatus();
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Airplane toggle", [](lv_event_t*) { g_ui.toggleAirplane(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Hotspot toggle", [](lv_event_t*) { g_ui.toggleHotspot(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "WiFi STA connect",
      [](lv_event_t*) { g_ui.emailWifiConnect(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Bluetooth pref",
      [](lv_event_t*) { g_ui.toggleBluetooth(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_SETTINGS); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::refreshNetworkStatus() {
  if (!listLabel_ || screen_ != UI_SET_NETWORK) return;
  PhoneStatus st;
  statusLock();
  st = g_status;
  statusUnlock();
  char line[280];
  snprintf(line, sizeof(line),
           "Airplane: %s\nHotspot SoftAP: %s\nWiFi STA: %s\n"
           "4G reg: %s  PDP: %s\nSIP: %s\nBT pref: %s\n"
           "WiFi file: /wifi_sta.txt",
           g_settings.get().airplaneMode ? "ON" : "off",
           connectivityHotspotOn() ? "ON" : "off",
           g_email.wifiReady() ? g_email.status() : "not connected",
           st.registered ? "Y" : "N", st.pdpActive ? "Y" : "N",
           st.sipRegistered ? "registered" : "down",
           g_settings.get().btEnabled ? "ON" : "off");
  lv_label_set_text(listLabel_, line);
}

void Ui::buildSetAccounts() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_), "Accounts");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  draft_[0] = 0;
  const char* ics = calendarIcsUrl();
  char line[300];
  char devLine[24];
  char tgtLine[24];
  if (g_settings.get().loraDeviceId)
    snprintf(devLine, sizeof(devLine), "%lu",
             (unsigned long)g_settings.get().loraDeviceId);
  else
    strncpy(devLine, "auto (MAC)", sizeof(devLine) - 1);
  if (g_settings.get().loraTargetId)
    snprintf(tgtLine, sizeof(tgtLine), "%lu",
             (unsigned long)g_settings.get().loraTargetId);
  else
    strncpy(tgtLine, "broadcast", sizeof(tgtLine) - 1);
  snprintf(line, sizeof(line),
           "Google ICS: %s\nFile: /google_ics.url\n"
           "Email: /email.txt\nInbox cache: %d msgs (%s)\n"
           "Voicemail: %s\nLoRa ID override: %s\n"
           "LoRa target: %s\n"
           "Confirm = save VM#\n"
           "Save LoRa ID / Target = buttons",
           ics && ics[0] ? "configured" : "not set", g_email.count(),
           g_email.status()[0] ? g_email.status() : "-",
           g_settings.get().voicemailNumber[0] ? g_settings.get().voicemailNumber
                                              : "*86 default",
           devLine, tgtLine);
  lv_label_set_text(listLabel_, line);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Sync Google Calendar",
      [](lv_event_t*) { g_ui.calendarSyncGoogle(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Open Email app",
      [](lv_event_t*) { g_ui.showScreen(UI_EMAIL); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Call voicemail", [](lv_event_t*) { g_ui.dialVoicemail(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Save LoRa ID",
      [](lv_event_t*) {
        g_ui.saveLoraDeviceIdFromDraft();
        g_ui.showScreen(UI_SET_ACCOUNTS);
      },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Save LoRa target",
      [](lv_event_t*) {
        g_ui.saveLoraTargetFromDraft();
        g_ui.showScreen(UI_SET_ACCOUNTS);
      },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_SETTINGS); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildHelp() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_), "Help / Keys");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  lv_label_set_text(
      listLabel_,
      "Confirm (Enter) — click / save\n"
      "Bksp — delete char or go back\n"
      "Arrows — move mouse cursor\n"
      "  (on desktop / folders / explorers)\n"
      "Shift + letter — digits & symbols\n"
      "CALL — dial from Phone\n"
      "END — hang up\n\n"
      "Videos: SD /videos/*.mjpeg\n"
      "LoRa: Comm → LoRa SOS (Heltec mesh)\n"
      "SD templates on first boot");
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_SETTINGS); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildSetSounds() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_), "Sounds");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  char line[120];
  snprintf(line, sizeof(line), "Profile: %s\nMaster sounds: %s",
           g_settings.profileName(),
           g_settings.get().soundsEnabled ? "ON" : "off");
  lv_label_set_text(listLabel_, line);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Cycle profile", [](lv_event_t*) { g_ui.cycleProfile(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Toggle sounds", [](lv_event_t*) { g_ui.toggleSounds(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Ringtone file",
      [](lv_event_t*) { g_ui.showScreen(UI_RINGTONE); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Tone test",
      [](lv_event_t*) { phonePlayNotify(800, 400); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Ringtone test",
      [](lv_event_t*) { phonePlayRingtone(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_SETTINGS); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildSetAbout() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_), "About");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  PhoneStatus st;
  statusLock();
  st = g_status;
  statusUnlock();
  char buf[360];
  snprintf(buf, sizeof(buf),
           "ESP Phone 1.0\nAPN: %s\nSIP: %s\nSIM: %s  Reg: %s\n"
           "PDP: %s  CSQ: %d\nBat: %d%% (%dmV) chg:%d\n"
           "Storage: %s\nIP: %s\nAudio: ESP32 I2S only\n"
           "Online setup: assets/online_setup.md",
           APN_NAME, SIP_USERNAME, st.simReady ? "OK" : "NO",
           st.registered ? "Y" : "N", st.pdpActive ? "Y" : "N", st.csq,
           st.batteryPercent, st.batteryMv, st.chargeStatus,
           Storage::backendName(), st.ipAddr[0] ? st.ipAddr : "-");
  lv_label_set_text(listLabel_, buf);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Audio tone",
      [](lv_event_t*) { phonePlayNotify(1000, 500); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_SETTINGS); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::handleGlobalKeys(uint16_t code, char ascii) {
  if (code == KEY_END) {
    g_sip.hangup();
    if (screen_ == UI_CALL) showScreen(UI_PHONE);
    return;
  }
  if (code == KEY_CALL && screen_ == UI_PHONE && dial_[0]) {
    g_sip.dial(dial_);
    showScreen(UI_CALL);
    return;
  }
  if (g_games.isActive()) {
    g_games.onKey(code, ascii);
    return;
  }

  // Lists: Up/Down change selection (non-pointer screens only)
  if (!usesPointer() &&
      (screen_ == UI_NOTES || screen_ == UI_TODOS || screen_ == UI_CONTACTS ||
       screen_ == UI_CALL_LOG || screen_ == UI_SMS_THREADS ||
       screen_ == UI_NOTIFS || screen_ == UI_ALARMS || screen_ == UI_CALENDAR ||
       screen_ == UI_EMAIL) &&
      (code == KEY_UP || code == KEY_DOWN)) {
    int maxn = 0;
    if (screen_ == UI_NOTES) maxn = g_notes.count();
    else if (screen_ == UI_TODOS) maxn = g_todos.count();
    else if (screen_ == UI_CONTACTS) maxn = g_contacts.count();
    else if (screen_ == UI_CALL_LOG) maxn = g_callLog.count();
    else if (screen_ == UI_SMS_THREADS) {
      maxn = 0;
      for (int i = 0; i < g_smsStore.threadCount(); i++) {
        const SmsThread* t = g_smsStore.threadAt(i);
        if (draft_[0] && !containsInsensitive(t->name, draft_) &&
            !containsInsensitive(t->number, draft_))
          continue;
        maxn++;
      }
    } else if (screen_ == UI_NOTIFS) maxn = g_notifs.count();
    else if (screen_ == UI_ALARMS) maxn = g_clock.count();
    else if (screen_ == UI_CALENDAR) maxn = g_calendar.count();
    else if (screen_ == UI_EMAIL) maxn = g_email.count();
    if (maxn > 0) {
      listIndex_ = (listIndex_ + (code == KEY_DOWN ? 1 : -1) + maxn) % maxn;
      refreshListLabel();
    }
    return;
  }

  if (screen_ == UI_EBOOK_READ && (code == KEY_LEFT || code == KEY_RIGHT)) {
    if (code == KEY_RIGHT) g_ebook.nextPage();
    else g_ebook.prevPage();
    refreshEbookPage();
    return;
  }

  if (screen_ == UI_BROWSER && (code == KEY_LEFT || code == KEY_RIGHT)) {
    if (code == KEY_RIGHT) browserNext();
    else browserPrev();
    return;
  }

  if (usesPointer() &&
      (code == KEY_UP || code == KEY_DOWN || code == KEY_LEFT ||
       code == KEY_RIGHT)) {
    int dx = 0, dy = 0;
    if (code == KEY_LEFT) dx = -POINTER_STEP_PX;
    if (code == KEY_RIGHT) dx = POINTER_STEP_PX;
    if (code == KEY_UP) dy = -POINTER_STEP_PX;
    if (code == KEY_DOWN) dy = POINTER_STEP_PX;
    nudgeCursor(dx, dy);
    return;
  }

  if (code == KEY_UP) {
    moveFocus(-1);
    return;
  }
  if (code == KEY_DOWN) {
    moveFocus(1);
    return;
  }
  if (code == KEY_LEFT || code == KEY_RIGHT) {
    moveFocus(code == KEY_RIGHT ? 1 : -1);
    return;
  }
  if (code == '\n') {
    if (screen_ == UI_GAME_SOLITAIRE) {
      int lx = s_ptrX, ly = s_ptrY;
      if (canvas_) {
        lv_area_t a;
        lv_obj_get_coords(canvas_, &a);
        lx -= a.x1;
        ly -= a.y1;
      }
      g_solitaire.click(lx, ly);
      g_solitaire.draw();
      if (listLabel_) lv_label_set_text(listLabel_, g_solitaire.status());
      return;
    }
    if (screen_ == UI_GAME_UNO) {
      int lx = s_ptrX, ly = s_ptrY;
      if (canvas_) {
        lv_area_t a;
        lv_obj_get_coords(canvas_, &a);
        lx -= a.x1;
        ly -= a.y1;
      }
      g_uno.click(lx, ly);
      g_uno.draw();
      if (listLabel_) lv_label_set_text(listLabel_, g_uno.status());
      return;
    }
    if (usesPointer()) {
      pointerClick();
      return;
    }
    if (screen_ == UI_VIDEO_PLAY) {
      videoTogglePause();
      return;
    }
    if (screen_ == UI_LOCK) {
      tryUnlock();
      return;
    }
    if (screen_ == UI_CALL && g_sip.state() == CALL_RINGING) {
      g_sip.answer();
      return;
    }
    if (screen_ == UI_CAMERA) {
      snapCamera();
      return;
    }
    if (screen_ == UI_GPS) {
      gpsToggle();
      return;
    }
    if (screen_ == UI_MUSIC) {
      playSelectedMusic();
      return;
    }
    if (screen_ == UI_AUDIOBOOKS) {
      playSelectedAudiobook();
      return;
    }
    if (screen_ == UI_EBOOKS) {
      openSelectedEbook();
      return;
    }
    if (screen_ == UI_NOTES) {
      notesOpenSelected();
      return;
    }
    if (screen_ == UI_NOTE_EDIT) {
      if (draftFocusTitle_) {
        draftFocusTitle_ = false;
        return;
      }
      notesSaveEdit();
      return;
    }
    if (screen_ == UI_CONTACT_EDIT) {
      if (draftFocusTitle_) {
        draftFocusTitle_ = false;
        return;
      }
      contactSave();
      return;
    }
    if (screen_ == UI_CONTACTS) {
      contactDial();
      return;
    }
    if (screen_ == UI_CALL_LOG) {
      callLogDial();
      return;
    }
    if (screen_ == UI_SMS_THREADS) {
      openSmsThread();
      return;
    }
    if (screen_ == UI_SMS_THREAD) {
      smsReplySend();
      return;
    }
    if (screen_ == UI_ALARMS) {
      alarmToggleSelected();
      return;
    }
    if (screen_ == UI_CALENDAR) {
      calendarAddToday();
      return;
    }
    if (screen_ == UI_EMAIL) {
      emailOpenSelected();
      return;
    }
    if (screen_ == UI_BROWSER) {
      browserGo();
      return;
    }
    if (screen_ == UI_CALC) {
      calcEquals();
      return;
    }
    if (screen_ == UI_CONVERT) {
      convertRun();
      return;
    }
    if (screen_ == UI_SET_SECURITY) {
      if (draft_[0]) setPinFromDraft();
      showScreen(UI_SET_SECURITY);
      return;
    }
    if (screen_ == UI_SET_ACCOUNTS) {
      if (draft_[0]) {
        saveVoicemailFromDraft();
        showScreen(UI_SET_ACCOUNTS);
      } else {
        activateFocus();
      }
      return;
    }
    if (screen_ == UI_LORA) {
      if (draft_[0])
        loraSendDraft();
      else
        activateFocus();
      return;
    }
    if (screen_ == UI_TODOS) {
      if (draft_[0])
        todoAddDraft();
      else
        todoToggleSelected();
      return;
    }
    if (screen_ == UI_COMPOSE) {
      if (composeFocusTo_) {
        composeFocusTo_ = false;
        return;
      }
      sendComposeSms();
      return;
    }
    activateFocus();
    return;
  }
  if (code == '\b') {
    if (screen_ == UI_PHONE) {
      backspaceDial();
      lv_obj_t* num = (lv_obj_t*)lv_obj_get_user_data(rootContent_);
      if (num) lv_label_set_text(num, dial_[0] ? dial_ : "_");
    } else if (screen_ == UI_LOCK) {
      size_t n = strlen(pinBuf_);
      if (n) pinBuf_[n - 1] = 0;
      if (listLabel_)
        lv_label_set_text_fmt(listLabel_, "PIN: %s", pinBuf_[0] ? pinBuf_ : "____");
    } else if (screen_ == UI_COMPOSE) {
      if (composeFocusTo_) {
        size_t n = strlen(composeTo_);
        if (n) composeTo_[n - 1] = 0;
        if (s_composeToLab)
          lv_label_set_text_fmt(s_composeToLab, "To: %s",
                                composeTo_[0] ? composeTo_ : "_");
      } else {
        size_t n = strlen(compose_);
        if (n) {
          compose_[n - 1] = 0;
          lv_obj_t* ta = (lv_obj_t*)lv_obj_get_user_data(rootContent_);
          if (ta) lv_textarea_set_text(ta, compose_);
        }
      }
    } else if (screen_ == UI_CONTACT_EDIT) {
      char* t = draftFocusTitle_ ? draftTitle_ : draft_;
      size_t n = strlen(t);
      if (n) {
        t[n - 1] = 0;
        char line[160];
        snprintf(line, sizeof(line), "Name: %s\nNum: %s",
                 draftTitle_[0] ? draftTitle_ : "_", draft_[0] ? draft_ : "_");
        if (listLabel_) lv_label_set_text(listLabel_, line);
      } else if (!draftFocusTitle_) {
        draftFocusTitle_ = true;
      } else {
        showScreen(UI_CONTACTS);
      }
    } else if (screen_ == UI_SMS_THREAD) {
      size_t n = strlen(draft_);
      if (n) {
        draft_[n - 1] = 0;
        lv_obj_t* reply = (lv_obj_t*)lv_obj_get_user_data(rootContent_);
        if (reply)
          lv_label_set_text_fmt(reply, "Reply: %s", draft_[0] ? draft_ : "_");
      } else {
        showScreen(UI_SMS_THREADS);
      }
    } else if (screen_ == UI_SET_SECURITY) {
      size_t n = strlen(draft_);
      if (n) draft_[n - 1] = 0;
      if (listLabel_)
        lv_label_set_text_fmt(listLabel_, "PIN draft: %s\nConfirm to save",
                              draft_[0] ? draft_ : "_");
    } else if (screen_ == UI_SET_ACCOUNTS) {
      size_t n = strlen(draft_);
      if (n) draft_[n - 1] = 0;
      if (listLabel_)
        lv_label_set_text_fmt(listLabel_,
                              "Draft: %s\nConfirm=VM  LoRa ID/Target=btns",
                              draft_[0] ? draft_ : "_");
    } else if (screen_ == UI_LORA) {
      size_t n = strlen(draft_);
      if (n) {
        draft_[n - 1] = 0;
        refreshLoraUi();
      } else {
        showScreen(UI_COMM);
      }
    } else if (screen_ == UI_CALC) {
      size_t n = strlen(calcExpr_);
      if (n) calcExpr_[n - 1] = 0;
      refreshCalcLabel();
    } else if (screen_ == UI_CONVERT) {
      size_t n = strlen(convValue_);
      if (n) convValue_[n - 1] = 0;
      refreshConvertLabel();
    } else if (screen_ == UI_BROWSER) {
      size_t n = strlen(browserUrl_);
      if (n) {
        browserUrl_[n - 1] = 0;
        if (listLabel_)
          lv_label_set_text_fmt(listLabel_, "URL: %s",
                                browserUrl_[0] ? browserUrl_ : "_");
      } else {
        showScreen(UI_MAIN);
      }
    } else if (screen_ == UI_SMS_THREADS) {
      size_t n = strlen(draft_);
      if (n) {
        draft_[n - 1] = 0;
        refreshListLabel();
      } else {
        showScreen(UI_COMM);
      }
    } else if (screen_ == UI_EMAIL_READ) {
      showScreen(UI_EMAIL);
    } else if (screen_ == UI_NOTE_EDIT) {
      char* t = draftFocusTitle_ ? draftTitle_ : draft_;
      size_t n = strlen(t);
      if (n) {
        t[n - 1] = 0;
        char line[600];
        snprintf(line, sizeof(line), "Title: %s\n\n%s",
                 draftTitle_[0] ? draftTitle_ : "_", draft_[0] ? draft_ : "_");
        if (listLabel_) lv_label_set_text(listLabel_, line);
      } else if (!draftFocusTitle_) {
        draftFocusTitle_ = true;
      } else {
        showScreen(UI_NOTES);
      }
    } else if (screen_ == UI_TODOS) {
      size_t n = strlen(draft_);
      if (n) {
        draft_[n - 1] = 0;
        lv_obj_t* draftLab = (lv_obj_t*)lv_obj_get_user_data(rootContent_);
        if (draftLab)
          lv_label_set_text_fmt(draftLab, "New: %s", draft_[0] ? draft_ : "_");
      } else {
        showScreen(UI_MAIN);
      }
    } else if (screen_ == UI_VIDEO_PLAY) {
      leaveVideo();
      showScreen(UI_VIDEO);
    } else if (screen_ == UI_EBOOK_READ) {
      g_ebook.close();
      showScreen(UI_EBOOKS);
    } else if (screen_ == UI_GAME_SOLITAIRE || screen_ == UI_GAME_UNO) {
      leaveCardGame();
      showScreen(UI_GAMES_MENU);
    } else if (screen_ == UI_GAME_SNAKE || screen_ == UI_GAME_PONG ||
               screen_ == UI_GAME_TETRIS) {
      g_games.stop();
      showScreen(UI_GAMES_MENU);
    } else if (screen_ != UI_MAIN) {
      showScreen(UI_MAIN);
    }
    return;
  }

  // Typing
  if (ascii) {
    if (screen_ == UI_PHONE) {
      char d = ascii;
      if (d >= 'a' && d <= 'z') d = (char)(d - 32);
      if ((d >= '0' && d <= '9') || d == '*' || d == '#' || d == '+') {
        appendDialChar(d);
      } else if (ascii >= '0' && ascii <= '9') {
        appendDialChar(ascii);
      }
      lv_obj_t* num = (lv_obj_t*)lv_obj_get_user_data(rootContent_);
      if (num) lv_label_set_text(num, dial_[0] ? dial_ : "_");
    } else if (screen_ == UI_LOCK) {
      char d = ascii;
      if (d >= 'a' && d <= 'z') {
        // shift map digit
        int idx = d - 'a';
        if (idx >= 0 && idx < 26) d = KB_SHIFT_MAP[idx];
      }
      if (d >= '0' && d <= '9') {
        size_t n = strlen(pinBuf_);
        if (n + 1 < sizeof(pinBuf_)) {
          pinBuf_[n] = d;
          pinBuf_[n + 1] = 0;
        }
        if (listLabel_)
          lv_label_set_text_fmt(listLabel_, "PIN: %s", pinBuf_);
      }
    } else if (screen_ == UI_COMPOSE) {
      char d = ascii;
      if ((d >= '0' && d <= '9') || d == '*' || d == '#' || d == '+') {
        if (composeFocusTo_)
          setComposeToDigit(d);
        else
          appendComposeBody(d);
      } else if (!composeFocusTo_) {
        appendComposeBody(ascii);
      }
      lv_obj_t* ta = (lv_obj_t*)lv_obj_get_user_data(rootContent_);
      if (ta && !composeFocusTo_) lv_textarea_set_text(ta, compose_);
    } else if (screen_ == UI_CONTACT_EDIT) {
      if (draftFocusTitle_) {
        size_t n = strlen(draftTitle_);
        if (n + 1 < sizeof(draftTitle_)) {
          draftTitle_[n] = ascii;
          draftTitle_[n + 1] = 0;
        }
      } else {
        char d = ascii;
        if (d >= 'a' && d <= 'z') {
          int idx = d - 'a';
          if (idx >= 0 && idx < 26) d = KB_SHIFT_MAP[idx];
        }
        if ((d >= '0' && d <= '9') || d == '+' || d == '*' || d == '#') {
          size_t n = strlen(draft_);
          if (n + 1 < sizeof(draft_)) {
            draft_[n] = d;
            draft_[n + 1] = 0;
          }
        }
      }
      char line[160];
      snprintf(line, sizeof(line), "Name: %s\nNum: %s",
               draftTitle_[0] ? draftTitle_ : "_", draft_[0] ? draft_ : "_");
      if (listLabel_) lv_label_set_text(listLabel_, line);
    } else if (screen_ == UI_SMS_THREAD) {
      size_t n = strlen(draft_);
      if (n + 1 < sizeof(draft_)) {
        draft_[n] = ascii;
        draft_[n + 1] = 0;
      }
      lv_obj_t* reply = (lv_obj_t*)lv_obj_get_user_data(rootContent_);
      if (reply) lv_label_set_text_fmt(reply, "Reply: %s", draft_);
    } else if (screen_ == UI_SET_SECURITY) {
      char d = ascii;
      if (d >= 'a' && d <= 'z') {
        int idx = d - 'a';
        if (idx >= 0 && idx < 26) d = KB_SHIFT_MAP[idx];
      }
      if (d >= '0' && d <= '9') {
        size_t n = strlen(draft_);
        if (n + 1 < sizeof(draft_) && n < 6) {
          draft_[n] = d;
          draft_[n + 1] = 0;
        }
        if (listLabel_)
          lv_label_set_text_fmt(listLabel_, "PIN draft: %s\nConfirm to save",
                                draft_);
      }
    } else if (screen_ == UI_SET_ACCOUNTS) {
      char d = ascii;
      if ((d >= 'a' && d <= 'z') || (d >= 'A' && d <= 'Z') ||
          (d >= '0' && d <= '9') || d == '+' || d == '*' || d == '#' ||
          d == '-' || d == '_') {
        if (d >= 'a' && d <= 'z') d = (char)(d - 'a' + 'A');
        size_t n = strlen(draft_);
        if (n + 1 < sizeof(draft_) && n < 23) {
          draft_[n] = d;
          draft_[n + 1] = 0;
        }
        if (listLabel_)
          lv_label_set_text_fmt(listLabel_,
                                "Draft: %s\nConfirm=VM  LoRa ID/Target=btns",
                                draft_);
      }
    } else if (screen_ == UI_LORA) {
      if (ascii >= 32 && ascii < 127) {
        size_t n = strlen(draft_);
        if (n + 1 < 120) {
          draft_[n] = ascii;
          draft_[n + 1] = 0;
          refreshLoraUi();
        }
      }
    } else if (screen_ == UI_CALC) {
      char d = ascii;
      if ((d >= '0' && d <= '9') || d == '.' || d == '+' || d == '-' ||
          d == '*' || d == '/') {
        size_t n = strlen(calcExpr_);
        if (n + 1 < sizeof(calcExpr_)) {
          calcExpr_[n] = d;
          calcExpr_[n + 1] = 0;
          refreshCalcLabel();
        }
      } else if (d >= 'a' && d <= 'z') {
        int idx = d - 'a';
        char m = KB_SHIFT_MAP[idx];
        if ((m >= '0' && m <= '9') || m == '+' || m == '-' || m == '*' ||
            m == '/' || m == '.') {
          size_t n = strlen(calcExpr_);
          if (n + 1 < sizeof(calcExpr_)) {
            calcExpr_[n] = m;
            calcExpr_[n + 1] = 0;
            refreshCalcLabel();
          }
        }
      }
    } else if (screen_ == UI_CONVERT) {
      char d = ascii;
      if (d >= 'a' && d <= 'z') {
        int idx = d - 'a';
        d = KB_SHIFT_MAP[idx];
      }
      if ((d >= '0' && d <= '9') || d == '.' || d == '-') {
        size_t n = strlen(convValue_);
        if (n + 1 < sizeof(convValue_)) {
          convValue_[n] = d;
          convValue_[n + 1] = 0;
          refreshConvertLabel();
        }
      }
    } else if (screen_ == UI_BROWSER) {
      size_t n = strlen(browserUrl_);
      if (n + 1 < sizeof(browserUrl_)) {
        browserUrl_[n] = ascii;
        browserUrl_[n + 1] = 0;
        if (listLabel_)
          lv_label_set_text_fmt(listLabel_, "URL: %s", browserUrl_);
      }
    } else if (screen_ == UI_SMS_THREADS) {
      size_t n = strlen(draft_);
      if (n + 1 < sizeof(draft_)) {
        draft_[n] = ascii;
        draft_[n + 1] = 0;
      }
      listIndex_ = 0;
      refreshListLabel();
    } else if (screen_ == UI_NOTE_EDIT) {
      char* t = draftFocusTitle_ ? draftTitle_ : draft_;
      size_t maxn = draftFocusTitle_ ? sizeof(draftTitle_) : sizeof(draft_);
      size_t n = strlen(t);
      if (n + 1 < maxn) {
        t[n] = ascii;
        t[n + 1] = 0;
      }
      char line[600];
      snprintf(line, sizeof(line), "Title: %s\n\n%s",
               draftTitle_[0] ? draftTitle_ : "_", draft_[0] ? draft_ : "_");
      if (listLabel_) lv_label_set_text(listLabel_, line);
    } else if (screen_ == UI_TODOS) {
      size_t n = strlen(draft_);
      if (n + 1 < sizeof(draft_)) {
        draft_[n] = ascii;
        draft_[n + 1] = 0;
      }
      lv_obj_t* draftLab = (lv_obj_t*)lv_obj_get_user_data(rootContent_);
      if (draftLab)
        lv_label_set_text_fmt(draftLab, "New: %s", draft_);
    }
  }
}

void Ui::onKey(uint16_t code, char ascii, bool shifted) {
  (void)shifted;
  markActivity();
  if (locked_ && screen_ != UI_LOCK) {
    showScreen(UI_LOCK);
    return;
  }
  handleGlobalKeys(code, ascii);

  // Refresh call timer label
  if (screen_ == UI_CALL) {
    lv_obj_t* timer = (lv_obj_t*)lv_obj_get_user_data(rootContent_);
    if (timer) {
      statusLock();
      uint32_t sec = g_status.callSeconds;
      statusUnlock();
      char tbuf[32];
      snprintf(tbuf, sizeof(tbuf), "%02u:%02u", sec / 60, sec % 60);
      lv_label_set_text(timer, tbuf);
    }
  }

  // Blit game framebuffer
  if (g_games.isActive() && canvas_ && canvasBuf_) {
    const uint16_t* fb = g_games.framebuffer();
    for (int i = 0; i < Games::FB_W * Games::FB_H; i++) {
      canvasBuf_[i].full = fb[i];
    }
    lv_obj_invalidate(canvas_);
  }
}
void Ui::markActivity() { lastActivityMs_ = millis(); }

void Ui::lockNow() {
  locked_ = true;
  pinBuf_[0] = 0;
  if (screen_ != UI_LOCK) preLockScreen_ = screen_;
  showScreen(UI_LOCK);
}

void Ui::tryUnlock() {
  if (g_clock.isRinging() && !pinBuf_[0]) {
    g_clock.snooze(9);
    refreshLockClock();
    return;
  }
  if (g_settings.checkPin(pinBuf_)) {
    locked_ = false;
    pinBuf_[0] = 0;
    g_clock.dismissRinging();
    markActivity();
    showScreen(preLockScreen_ == UI_LOCK ? UI_MAIN : preLockScreen_);
  } else {
    pinBuf_[0] = 0;
    if (listLabel_) lv_label_set_text(listLabel_, "Wrong PIN");
  }
}

void Ui::pollCallState() {
  CallState st = g_sip.state();
  if (st == CALL_IN_CALL) {
    statusLock();
    activeCallDur_ = (uint16_t)g_status.callSeconds;
    statusUnlock();
  }
  if (prevCallState_ == st) return;

  statusLock();
  char num[64];
  strncpy(num, g_status.callerId, sizeof(num) - 1);
  num[sizeof(num) - 1] = 0;
  statusUnlock();

  if (prevCallState_ == CALL_RINGING && st == CALL_IDLE) {
    g_callLog.add(CALL_MISSED, num, g_contacts.nameForNumber(num), 0);
    g_notifs.push(NOTIF_MISSED_CALL, "Missed call", num);
  } else if (prevCallState_ == CALL_IN_CALL &&
             (st == CALL_IDLE || st == CALL_ENDED)) {
    g_callLog.add(CALL_IN, num, g_contacts.nameForNumber(num), activeCallDur_);
    activeCallDur_ = 0;
  } else if (prevCallState_ == CALL_DIALING &&
             (st == CALL_IDLE || st == CALL_ENDED)) {
    g_callLog.add(CALL_OUT, num, g_contacts.nameForNumber(num), activeCallDur_);
    activeCallDur_ = 0;
  } else if (prevCallState_ == CALL_DIALING && st == CALL_IN_CALL) {
    // connected outbound — duration tracked until end
  }
  prevCallState_ = st;
}

void Ui::refreshLockClock() {
  lv_obj_t* lab = clockLabel_ ? clockLabel_ : nullptr;
  if (!lab) return;
  char next[40];
  g_clock.formatNextAlarm(next, sizeof(next));
  int h, m, s, y, mo, d;
  if (g_clock.timeValid()) {
    g_clock.getTime(h, m, s);
    g_clock.getDate(y, mo, d);
    char line[120];
    if (g_clock.isRinging())
      snprintf(line, sizeof(line),
               "%02d:%02d:%02d\nALARM — Confirm=snooze\n%s", h, m, s, next);
    else
      snprintf(line, sizeof(line), "%02d:%02d:%02d\n%04d-%02d-%02d\n%s", h, m, s,
               y, mo, d, next);
    lv_label_set_text(lab, line);
  } else {
    char line[80];
    snprintf(line, sizeof(line), "--:--:--\nSync modem time\n%s", next);
    lv_label_set_text(lab, line);
  }
}

void Ui::buildLock() {
  clockLabel_ = nullptr;
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_flex_align(rootContent_, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER,
                        LV_FLEX_ALIGN_CENTER);
  clockLabel_ = lv_label_create(rootContent_);
  lv_obj_set_style_text_font(clockLabel_, &lv_font_montserrat_28, 0);
  refreshLockClock();
  // Notification / missed preview
  lv_obj_t* prev = lv_label_create(rootContent_);
  lv_label_set_long_mode(prev, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(prev, TFT_WIDTH_PX - 32);
  char pre[160];
  int nu = g_notifs.unread() + g_smsStore.totalUnread();
  int miss = g_callLog.missedUnread();
  const Notification* n0 = g_notifs.count() ? g_notifs.at(0) : nullptr;
  snprintf(pre, sizeof(pre), "Msgs/notifs: %d   Missed: %d\n%s", nu, miss,
           n0 ? n0->title : "(no alerts)");
  lv_label_set_text(prev, pre);
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_text(listLabel_, "PIN: ____");
  lv_obj_t* hint = lv_label_create(rootContent_);
  lv_label_set_text(hint, "Shift+letters = digits\nConfirm = unlock");
}

void Ui::buildContacts() {
  listIndex_ = 0;
  g_contacts.sortFavoritesFirst();
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_), "Contacts  *=fav");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  refreshListLabel();
  focusables_[focusCount_++] = makeBtn(rootContent_, "Dial", [](lv_event_t*) { g_ui.contactDial(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "SMS", [](lv_event_t*) { g_ui.contactSms(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "Fav", [](lv_event_t*) { g_ui.contactToggleFav(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "New", [](lv_event_t*) { g_ui.contactNew(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "Edit", [](lv_event_t*) { g_ui.contactEditSelected(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "Delete", [](lv_event_t*) { g_ui.contactDelete(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_COMM); }, nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildContactEdit() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_),
                    contactEditIndex_ >= 0 ? "Edit contact" : "New contact");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  char line[160];
  snprintf(line, sizeof(line), "Name: %s\nNum: %s",
           draftTitle_[0] ? draftTitle_ : "_", draft_[0] ? draft_ : "_");
  lv_label_set_text(listLabel_, line);
  focusables_[focusCount_++] =
      makeBtn(rootContent_, "Save", [](lv_event_t*) { g_ui.contactSave(); },
              nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_CONTACTS); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildCallLog() {
  listIndex_ = 0;
  g_callLog.clearMissedUnread();
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_), "Call log");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  refreshListLabel();
  focusables_[focusCount_++] = makeBtn(rootContent_, "Dial", [](lv_event_t*) { g_ui.callLogDial(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_COMM); }, nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildSmsThreads() {
  listIndex_ = 0;
  draft_[0] = 0;
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  char hdr[64];
  snprintf(hdr, sizeof(hdr), "Messages unread:%d\nType to search",
           g_smsStore.totalUnread());
  lv_label_set_text(lv_label_create(rootContent_), hdr);
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  refreshListLabel();
  focusables_[focusCount_++] = makeBtn(rootContent_, "Open", [](lv_event_t*) { g_ui.openSmsThread(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "Compose", [](lv_event_t*) { g_ui.showScreen(UI_COMPOSE); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_COMM); }, nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildSmsThread() {
  SmsThread* t = g_smsStore.threadAt(smsThreadIndex_);
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_), t ? t->name : "Thread");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  if (!t || t->msgCount == 0) lv_label_set_text(listLabel_, "(empty)");
  else {
    char buf[700] = {0};
    int start = t->msgCount > 6 ? t->msgCount - 6 : 0;
    for (int i = start; i < t->msgCount; i++) {
      char line[360];
      snprintf(line, sizeof(line), "%s: %.80s\n", t->msgs[i].outbound ? "You" : "Them", t->msgs[i].text);
      strncat(buf, line, sizeof(buf) - strlen(buf) - 1);
    }
    lv_label_set_text(listLabel_, buf);
  }
  draft_[0] = 0;
  lv_obj_t* reply = lv_label_create(rootContent_);
  lv_label_set_text(reply, "Reply: _");
  lv_obj_set_user_data(rootContent_, reply);
  focusables_[focusCount_++] = makeBtn(rootContent_, "Send", [](lv_event_t*) { g_ui.smsReplySend(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "OK", [](lv_event_t*) { g_ui.smsQuickReply(0); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "On my way", [](lv_event_t*) { g_ui.smsQuickReply(1); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "Later", [](lv_event_t*) { g_ui.smsQuickReply(2); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_SMS_THREADS); }, nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildNotifs() {
  listIndex_ = 0;
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text_fmt(lv_label_create(rootContent_), "Notifications unread:%d", g_notifs.unread());
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  refreshListLabel();
  g_notifs.markAllRead();
  focusables_[focusCount_++] = makeBtn(rootContent_, "Clear", [](lv_event_t*) { g_ui.notifsClear(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MAIN); }, nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildClock() {
  clockLabel_ = nullptr;
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_flex_align(rootContent_, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
  clockLabel_ = lv_label_create(rootContent_);
  lv_obj_set_style_text_font(clockLabel_, &lv_font_montserrat_28, 0);
  refreshLockClock();
  focusables_[focusCount_++] = makeBtn(rootContent_, "Sync modem time", [](lv_event_t*) { g_ui.syncClock(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "Alarms", [](lv_event_t*) { g_ui.showScreen(UI_ALARMS); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MAIN); }, nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildAlarms() {
  listIndex_ = 0;
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_), "Alarms");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  refreshListLabel();
  focusables_[focusCount_++] = makeBtn(rootContent_, "Add 7:00", [](lv_event_t*) { g_ui.alarmAddDefault(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "Toggle", [](lv_event_t*) { g_ui.alarmToggleSelected(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "Snooze 9m", [](lv_event_t*) { g_ui.alarmSnooze(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "Delete", [](lv_event_t*) { g_ui.alarmDeleteSelected(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_CLOCK); }, nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::contactDial() {
  const Contact* c = g_contacts.at(listIndex_);
  if (!c) return;
  g_sip.dial(c->number);
  showScreen(UI_CALL);
}
void Ui::contactSms() {
  const Contact* c = g_contacts.at(listIndex_);
  if (!c) return;
  strncpy(composeTo_, c->number, sizeof(composeTo_) - 1);
  compose_[0] = 0;
  composeFocusTo_ = false;
  showScreen(UI_COMPOSE);
}
void Ui::contactNew() {
  contactEditIndex_ = -1;
  draftTitle_[0] = draft_[0] = 0;
  draftFocusTitle_ = true;
  showScreen(UI_CONTACT_EDIT);
}
void Ui::contactEditSelected() {
  const Contact* c = g_contacts.at(listIndex_);
  if (!c) return;
  contactEditIndex_ = listIndex_;
  strncpy(draftTitle_, c->name, sizeof(draftTitle_) - 1);
  draftTitle_[sizeof(draftTitle_) - 1] = 0;
  strncpy(draft_, c->number, sizeof(draft_) - 1);
  draft_[sizeof(draft_) - 1] = 0;
  draftFocusTitle_ = true;
  showScreen(UI_CONTACT_EDIT);
}
void Ui::contactSave() {
  if (!draft_[0]) {
    showScreen(UI_CONTACTS);
    return;
  }
  if (contactEditIndex_ >= 0)
    g_contacts.update(contactEditIndex_, draftTitle_, draft_);
  else
    g_contacts.add(draftTitle_, draft_);
  contactEditIndex_ = -1;
  showScreen(UI_CONTACTS);
}
void Ui::contactDelete() {
  g_contacts.remove(listIndex_);
  if (listIndex_ >= g_contacts.count() && listIndex_ > 0) listIndex_--;
  refreshListLabel();
}
void Ui::callLogDial() {
  const CallLogEntry* e = g_callLog.at(listIndex_);
  if (!e) return;
  g_sip.dial(e->number);
  showScreen(UI_CALL);
}
void Ui::openSmsThread() {
  if (g_smsStore.threadCount() <= 0) { showScreen(UI_COMPOSE); return; }
  // smsThreadIndex_ set by refreshListLabel when filtering
  if (smsThreadIndex_ < 0 || smsThreadIndex_ >= g_smsStore.threadCount())
    smsThreadIndex_ = listIndex_;
  g_smsStore.markThreadRead(smsThreadIndex_);
  draft_[0] = 0;
  showScreen(UI_SMS_THREAD);
}
void Ui::smsReplySend() {
  SmsThread* t = g_smsStore.threadAt(smsThreadIndex_);
  if (!t || !draft_[0]) return;
  if (g_modem.sendSms(t->number, draft_)) {
    g_smsStore.addOutbound(t->number, draft_);
    g_notifs.push(NOTIF_INFO, "SMS sent", t->number);
    draft_[0] = 0;
    showScreen(UI_SMS_THREAD);
  } else {
    g_notifs.push(NOTIF_INFO, "SMS failed", t->number);
  }
}

void Ui::smsQuickReply(int which) {
  static const char* kQr[] = {"OK", "On my way", "Call you later", "Can't talk"};
  if (which < 0 || which > 3) return;
  strncpy(draft_, kQr[which], sizeof(draft_) - 1);
  smsReplySend();
}

void Ui::contactToggleFav() {
  g_contacts.toggleFavorite(listIndex_);
  refreshListLabel();
}

void Ui::rejectCall() {
  g_media.stop();
  g_sip.hangup();
  showScreen(UI_PHONE);
}

void Ui::alarmAddDefault() { g_clock.add(7, 0, "Morning"); refreshListLabel(); }
void Ui::alarmToggleSelected() { g_clock.toggle(listIndex_); refreshListLabel(); }
void Ui::alarmDeleteSelected() {
  g_clock.remove(listIndex_);
  if (listIndex_ >= g_clock.count() && listIndex_ > 0) listIndex_--;
  refreshListLabel();
}
void Ui::setPinFromDraft() { g_settings.setPin(draft_); draft_[0] = 0; }
void Ui::saveVoicemailFromDraft() {
  PhoneSettings& s = g_settings.get();
  strncpy(s.voicemailNumber, draft_, sizeof(s.voicemailNumber) - 1);
  s.voicemailNumber[sizeof(s.voicemailNumber) - 1] = 0;
  g_settings.save();
  draft_[0] = 0;
}
void Ui::alarmSnooze() {
  g_clock.snooze(9);
  if (listLabel_ && screen_ == UI_ALARMS) refreshListLabel();
  if (screen_ == UI_LOCK || screen_ == UI_CLOCK) refreshLockClock();
}
void Ui::syncClock() { g_clock.syncFromModem(); refreshLockClock(); }
void Ui::notifsClear() { g_notifs.clear(); refreshListLabel(); }

void Ui::clearPin() {
  g_settings.setPin("");
  showScreen(UI_SET_SECURITY);
}

void Ui::cycleProfile() {
  g_settings.cycleProfile();
  showScreen(UI_SET_SOUNDS);
}

void Ui::toggleSounds() {
  g_settings.toggleSounds();
  showScreen(UI_SET_SOUNDS);
}

void Ui::cycleLockTimeout() {
  g_settings.cycleLockTimeout();
  showScreen(UI_SET_SECURITY);
}

void Ui::toggleAirplane() {
  bool next = !g_settings.get().airplaneMode;
  if (g_modem.setAirplaneMode(next)) {
    g_settings.get().airplaneMode = next;
    g_settings.save();
    statusLock();
    g_status.airplaneMode = next;
    if (next) {
      g_status.registered = false;
      g_status.pdpActive = false;
    }
    statusUnlock();
  }
  showScreen(UI_SET_NETWORK);
}

void Ui::toggleHotspot() {
  connectivitySetHotspot(!connectivityHotspotOn());
  showScreen(UI_SET_NETWORK);
}

void Ui::toggleBluetooth() {
  connectivitySetBluetooth(!connectivityBluetoothOn());
  showScreen(UI_SET_NETWORK);
}

void Ui::dialVoicemail() {
  const char* vm = g_settings.get().voicemailNumber;
  if (!vm[0]) {
    strncpy(composeTo_, "", sizeof(composeTo_));
    // prompt: use draft as number entry via settings — dial *86 default
    g_sip.dial("*86");
  } else {
    g_sip.dial(vm);
  }
  showScreen(UI_CALL);
}

void Ui::refreshCalcLabel() {
  if (listLabel_)
    lv_label_set_text_fmt(listLabel_, "%s", calcExpr_[0] ? calcExpr_ : "0");
}

void Ui::refreshConvertLabel() {
  if (!listLabel_) return;
  char line[160];
  snprintf(line, sizeof(line), "%s: %s %s -> %s\n(type value, Confirm)",
           converterCategoryName(convCat_),
           convValue_[0] ? convValue_ : "0",
           converterUnitName(convCat_, convFrom_),
           converterUnitName(convCat_, convTo_));
  lv_label_set_text(listLabel_, line);
}

void Ui::calcEquals() {
  double v = 0;
  if (calcEval(calcExpr_, v)) {
    snprintf(calcExpr_, sizeof(calcExpr_), "%.8g", v);
  } else {
    strncpy(calcExpr_, "ERR", sizeof(calcExpr_) - 1);
  }
  refreshCalcLabel();
}

void Ui::calcClear() {
  calcExpr_[0] = 0;
  refreshCalcLabel();
}

void Ui::convertRun() {
  double in = atof(convValue_[0] ? convValue_ : "0");
  double out = 0;
  if (converterConvert(convCat_, convFrom_, convTo_, in, out)) {
    char line[160];
    snprintf(line, sizeof(line), "%.6g %s = %.6g %s", in,
             converterUnitName(convCat_, convFrom_), out,
             converterUnitName(convCat_, convTo_));
    if (listLabel_) lv_label_set_text(listLabel_, line);
  }
}

void Ui::convertCycleCat() {
  convCat_ = (convCat_ + 1) % converterCategoryCount();
  convFrom_ = 0;
  convTo_ = converterUnitCount(convCat_) > 1 ? 1 : 0;
  refreshConvertLabel();
}
void Ui::convertCycleFrom() {
  int n = converterUnitCount(convCat_);
  if (n) convFrom_ = (convFrom_ + 1) % n;
  refreshConvertLabel();
}
void Ui::convertCycleTo() {
  int n = converterUnitCount(convCat_);
  if (n) convTo_ = (convTo_ + 1) % n;
  refreshConvertLabel();
}

void Ui::weatherRefresh() {
  double lat = 49.28, lon = -123.12;  // default Vancouver if no GPS
  if (g_gps.fix().valid) {
    lat = g_gps.fix().lat;
    lon = g_gps.fix().lon;
  }
  weatherFetchOpenMeteo(lat, lon);
  showScreen(UI_WEATHER);
}

void Ui::shareLocationSms() {
  char link[160];
  if (g_gps.fix().valid) {
    snprintf(link, sizeof(link), "https://maps.google.com/?q=%.5f,%.5f",
             g_gps.fix().lat, g_gps.fix().lon);
  } else {
    strncpy(link, "(no GPS fix yet)", sizeof(link) - 1);
  }
  strncpy(compose_, link, sizeof(compose_) - 1);
  composeTo_[0] = 0;
  composeFocusTo_ = true;
  showScreen(UI_COMPOSE);
}

void Ui::calendarAddToday() {
  int y = 2026, mo = 1, d = 1, h = 12, mi = 0, s = 0;
  if (g_clock.timeValid()) {
    g_clock.getDate(y, mo, d);
    g_clock.getTime(h, mi, s);
  }
  g_calendar.add(y, mo, d, (uint8_t)h, (uint8_t)((mi / 30) * 30), "Reminder");
  refreshListLabel();
}

void Ui::calendarDeleteSelected() {
  g_calendar.remove(listIndex_);
  if (listIndex_ >= g_calendar.count() && listIndex_ > 0) listIndex_--;
  refreshListLabel();
}

void Ui::buildTools() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_ROW_WRAP);
  lv_obj_set_flex_align(rootContent_, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START,
                        LV_FLEX_ALIGN_START);
  lv_obj_set_style_pad_row(rootContent_, 8, 0);
  lv_obj_set_style_pad_column(rootContent_, 8, 0);
  lv_obj_t* title = lv_label_create(rootContent_);
  lv_label_set_text(title, "Tools");
  lv_obj_set_width(title, TFT_WIDTH_PX - 16);
  auto add = [&](const char* name, UiScreen dest) {
    if (focusCount_ >= 32) return;
    auto cb = [](lv_event_t* e) {
      g_ui.showScreen((UiScreen)(uintptr_t)lv_event_get_user_data(e));
    };
    lv_obj_t* btn = makeAppBtn(rootContent_, name, dest, cb);
    lv_obj_set_width(btn, 148);
    focusables_[focusCount_++] = btn;
  };
  add("Calculator", UI_CALC);
  add("Converter", UI_CONVERT);
  add("Weather", UI_WEATHER);
  add("Alarms", UI_ALARMS);
  lv_obj_t* share = makeBtn(
      rootContent_, "Share GPS", [](lv_event_t*) { g_ui.shareLocationSms(); },
      nullptr);
  lv_obj_set_width(share, 148);
  focusables_[focusCount_++] = share;
  lv_obj_t* back = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MAIN); },
      nullptr);
  lv_obj_set_width(back, 148);
  focusables_[focusCount_++] = back;
}

void Ui::buildMedia() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_ROW_WRAP);
  lv_obj_set_flex_align(rootContent_, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START,
                        LV_FLEX_ALIGN_START);
  lv_obj_set_style_pad_row(rootContent_, 8, 0);
  lv_obj_set_style_pad_column(rootContent_, 8, 0);
  lv_obj_t* title = lv_label_create(rootContent_);
  lv_label_set_text(title, "Media");
  lv_obj_set_width(title, TFT_WIDTH_PX - 16);
  auto add = [&](const char* name, UiScreen dest) {
    if (focusCount_ >= 32) return;
    auto cb = [](lv_event_t* e) {
      g_ui.showScreen((UiScreen)(uintptr_t)lv_event_get_user_data(e));
    };
    lv_obj_t* btn = makeAppBtn(rootContent_, name, dest, cb);
    lv_obj_set_width(btn, 148);
    focusables_[focusCount_++] = btn;
  };
  add("Camera", UI_CAMERA);
  add("Gallery", UI_GALLERY);
  add("Voice notes", UI_RECORDER);
  add("GPS", UI_GPS);
  add("Notes", UI_NOTES);
  add("Todos", UI_TODOS);
  add("Music", UI_MUSIC);
  add("Videos", UI_VIDEO);
  add("Ebooks", UI_EBOOKS);
  add("Audiobooks", UI_AUDIOBOOKS);
  lv_obj_t* back = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MAIN); },
      nullptr);
  lv_obj_set_width(back, 148);
  focusables_[focusCount_++] = back;
}

void Ui::buildCalc() {
  calcExpr_[0] = 0;
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_), "Calculator");
  listLabel_ = lv_label_create(rootContent_);
  lv_obj_set_style_text_font(listLabel_, &lv_font_montserrat_28, 0);
  refreshCalcLabel();
  lv_label_set_text(lv_label_create(rootContent_),
                    "Type digits/operators\nConfirm = =");
  focusables_[focusCount_++] =
      makeBtn(rootContent_, "=", [](lv_event_t*) { g_ui.calcEquals(); }, nullptr);
  focusables_[focusCount_++] =
      makeBtn(rootContent_, "Clear", [](lv_event_t*) { g_ui.calcClear(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_TOOLS); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildConvert() {
  if (!convValue_[0]) strncpy(convValue_, "1", sizeof(convValue_) - 1);
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_), "Converter");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  refreshConvertLabel();
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Category", [](lv_event_t*) { g_ui.convertCycleCat(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "From unit", [](lv_event_t*) { g_ui.convertCycleFrom(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "To unit", [](lv_event_t*) { g_ui.convertCycleTo(); },
      nullptr);
  focusables_[focusCount_++] =
      makeBtn(rootContent_, "Convert", [](lv_event_t*) { g_ui.convertRun(); },
              nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_TOOLS); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildWeather() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_), "Weather");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  if (g_weather.valid)
    lv_label_set_text(listLabel_, g_weather.summary);
  else
    lv_label_set_text(listLabel_,
                      "Uses GPS fix if available\n(else Vancouver default)\n"
                      "Needs 4G data + HTTPS");
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Refresh", [](lv_event_t*) { g_ui.weatherRefresh(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_TOOLS); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildCalendar() {
  listIndex_ = 0;
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_), "Calendar");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  refreshListLabel();
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Add now", [](lv_event_t*) { g_ui.calendarAddToday(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Sync Google", [](lv_event_t*) { g_ui.calendarSyncGoogle(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Delete", [](lv_event_t*) { g_ui.calendarDeleteSelected(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MAIN); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::calendarSyncGoogle() {
  UiScreen back = screen_;
  if (listLabel_) lv_label_set_text(listLabel_, "Syncing Google ICS...");
  lv_timer_handler();
  int n = calendarSyncGoogleIcs();
  char line[80];
  if (n < 0)
    snprintf(line, sizeof(line), "Sync failed — set /google_ics.url");
  else
    snprintf(line, sizeof(line), "Imported %d Google events", n);
  g_notifs.push(NOTIF_INFO, "Calendar", line);
  if (back == UI_SET_ACCOUNTS)
    showScreen(UI_SET_ACCOUNTS);
  else {
    listIndex_ = 0;
    refreshListLabel();
    if (listLabel_ && g_calendar.count() <= 0) lv_label_set_text(listLabel_, line);
  }
}

void Ui::buildEmail() {
  listIndex_ = 0;
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_), "Email (IMAP / WiFi)");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  refreshListLabel();
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "WiFi connect", [](lv_event_t*) { g_ui.emailWifiConnect(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Refresh inbox", [](lv_event_t*) { g_ui.emailRefresh(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Open", [](lv_event_t*) { g_ui.emailOpenSelected(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MAIN); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::buildEmailRead() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  const EmailItem* m = g_email.at(listIndex_);
  lv_label_set_text(lv_label_create(rootContent_), m ? m->subject : "Message");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  lv_label_set_text(listLabel_, g_email.body()[0] ? g_email.body() : "(empty)");
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_EMAIL); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::emailWifiConnect() {
  UiScreen back = screen_;
  if (listLabel_) lv_label_set_text(listLabel_, "Connecting WiFi...");
  lv_timer_handler();
  g_email.connectWifiSta();
  if (back == UI_SET_NETWORK)
    showScreen(UI_SET_NETWORK);
  else {
    refreshListLabel();
  }
}

void Ui::emailRefresh() {
  if (listLabel_) lv_label_set_text(listLabel_, "Fetching inbox...");
  lv_timer_handler();
  g_email.refreshInbox();
  listIndex_ = 0;
  refreshListLabel();
}

void Ui::emailOpenSelected() {
  if (g_email.count() <= 0) return;
  if (listLabel_) lv_label_set_text(listLabel_, "Opening...");
  lv_timer_handler();
  if (g_email.openMessage(listIndex_)) showScreen(UI_EMAIL_READ);
  else refreshListLabel();
}

void Ui::buildBrowser() {
  if (!browserUrl_[0]) strncpy(browserUrl_, BROWSER_HOME_URL, sizeof(browserUrl_) - 1);
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_), "Text Browser (4G)");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  if (g_browser.pageSlice()[0]) {
    char hdr[80];
    snprintf(hdr, sizeof(hdr), "%s  p%d/%d\n", g_browser.status(),
             g_browser.page() + 1, g_browser.pageCount());
    // show URL line + content via draftLabel pattern — reuse listLabel for body
    static char pageBuf[520];
    snprintf(pageBuf, sizeof(pageBuf), "URL: %s\n%s\n---\n%s", browserUrl_,
             hdr, g_browser.pageSlice());
    lv_label_set_text(listLabel_, pageBuf);
  } else {
    lv_label_set_text_fmt(listLabel_, "URL: %s\nType URL, Confirm=Go\nLeft/Right=page",
                          browserUrl_);
  }
  focusables_[focusCount_++] =
      makeBtn(rootContent_, "Go", [](lv_event_t*) { g_ui.browserGo(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Home", [](lv_event_t*) { g_ui.browserHome(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Next pg", [](lv_event_t*) { g_ui.browserNext(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Prev pg", [](lv_event_t*) { g_ui.browserPrev(); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MAIN); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::browserGo() {
  if (!browserUrl_[0]) return;
  if (listLabel_) lv_label_set_text(listLabel_, "Fetching...");
  lv_timer_handler();
  g_browser.load(browserUrl_);
  showScreen(UI_BROWSER);
}

void Ui::browserHome() {
  strncpy(browserUrl_, BROWSER_HOME_URL, sizeof(browserUrl_) - 1);
  browserGo();
}

void Ui::browserNext() {
  g_browser.nextPage();
  showScreen(UI_BROWSER);
}

void Ui::browserPrev() {
  g_browser.prevPage();
  showScreen(UI_BROWSER);
}

void Ui::buildGallery() {
  fileCount_ = g_media.listFiles(CAM_PHOTOS_DIR, fileList_, MEDIA_MAX_FILES, ".jpg");
  if (fileCount_ <= 0)
    fileCount_ = g_media.listFiles(CAM_PHOTOS_DIR, fileList_, MEDIA_MAX_FILES, ".jpeg");
  fileIndex_ = 0;
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_),
                    "Gallery /photos\nCursor · Confirm click");
  fileLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(fileLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(fileLabel_, TFT_WIDTH_PX - 24);
  refreshFileListLabel();
  if (fileCount_ <= 0 && fileLabel_)
    lv_label_set_text(fileLabel_, "(no JPG photos yet — use Camera)");
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Prev",
      [](lv_event_t*) { g_ui.selectFileDelta(-1); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Next",
      [](lv_event_t*) { g_ui.selectFileDelta(1); }, nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MEDIA); },
      nullptr);
}

void Ui::buildRecorder() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_), "Voice notes");
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(listLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(listLabel_, TFT_WIDTH_PX - 24);
  lv_label_set_text_fmt(listLabel_, "%s\n%s",
                        g_recorder.isRecording() ? "RECORDING..." : "Idle",
                        g_recorder.lastPath()[0] ? g_recorder.lastPath()
                                                : "(no file yet)");
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Rec / Stop", [](lv_event_t*) { g_ui.recorderToggle(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Play last", [](lv_event_t*) { g_ui.recorderPlayLast(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MEDIA); },
      nullptr);
  styleFocus(focusables_[0], true);
}

void Ui::recorderToggle() {
  if (g_recorder.isRecording()) {
    g_recorder.stop();
  } else {
    g_recorder.start();
  }
  showScreen(UI_RECORDER);
}

void Ui::recorderPlayLast() {
  if (listLabel_) lv_label_set_text(listLabel_, "Playing...");
  lv_timer_handler();
  g_recorder.playLast();
  showScreen(UI_RECORDER);
}

void Ui::buildRingtone() {
  fileCount_ = g_media.listFiles(RINGTONE_DIR, fileList_, MEDIA_MAX_FILES, ".mp3");
  fileIndex_ = 0;
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_),
                    "Pick ringtone (/music)\nCursor · Confirm click");
  fileLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(fileLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(fileLabel_, TFT_WIDTH_PX - 24);
  refreshFileListLabel();
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_text_fmt(listLabel_, "Current:\n%s",
                        g_settings.get().ringtonePath[0]
                            ? g_settings.get().ringtonePath
                            : "(beep tones)");
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Prev", [](lv_event_t*) { g_ui.selectFileDelta(-1); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Next", [](lv_event_t*) { g_ui.selectFileDelta(1); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Use selected", [](lv_event_t*) { g_ui.pickRingtone(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Clear (beeps)",
      [](lv_event_t*) {
        g_settings.get().ringtonePath[0] = 0;
        g_settings.save();
        g_ui.showScreen(UI_RINGTONE);
      },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_SET_SOUNDS); },
      nullptr);
}

void Ui::pickRingtone() {
  if (fileCount_ <= 0) return;
  strncpy(g_settings.get().ringtonePath, fileList_[fileIndex_],
          sizeof(g_settings.get().ringtonePath) - 1);
  g_settings.save();
  showScreen(UI_RINGTONE);
}

void Ui::buildVideo() {
  fileCount_ = g_media.listFiles(VIDEO_DIR, fileList_, MEDIA_MAX_FILES, ".mjpeg");
  if (fileCount_ <= 0)
    fileCount_ = g_media.listFiles(VIDEO_DIR, fileList_, MEDIA_MAX_FILES, ".mjpg");
  fileIndex_ = 0;
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_label_set_text(lv_label_create(rootContent_),
                    "Videos  SD:/videos\nMJPEG only · Cursor click");
  fileLabel_ = lv_label_create(rootContent_);
  lv_label_set_long_mode(fileLabel_, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(fileLabel_, TFT_WIDTH_PX - 24);
  refreshFileListLabel();
  if (fileCount_ <= 0 && fileLabel_)
    lv_label_set_text(fileLabel_, "(no .mjpeg clips yet)");
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Prev", [](lv_event_t*) { g_ui.selectFileDelta(-1); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Next", [](lv_event_t*) { g_ui.selectFileDelta(1); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Play", [](lv_event_t*) { g_ui.playSelectedVideo(); },
      nullptr);
  focusables_[focusCount_++] = makeBtn(
      rootContent_, "Back", [](lv_event_t*) { g_ui.showScreen(UI_MEDIA); },
      nullptr);
}

void Ui::playSelectedVideo() {
  if (fileCount_ <= 0) return;
  if (!g_video.open(fileList_[fileIndex_])) return;
  showScreen(UI_VIDEO_PLAY);
}

void Ui::buildVideoPlay() {
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_flex_align(rootContent_, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER,
                        LV_FLEX_ALIGN_CENTER);
  lv_label_set_text(lv_label_create(rootContent_),
                    "Confirm=pause  Bksp=stop");
  canvasBuf_ = (lv_color_t*)heap_caps_malloc(
      VIDEO_MAX_W * VIDEO_MAX_H * sizeof(lv_color_t), MALLOC_CAP_SPIRAM);
  if (!canvasBuf_)
    canvasBuf_ =
        (lv_color_t*)malloc(VIDEO_MAX_W * VIDEO_MAX_H * sizeof(lv_color_t));
  canvas_ = lv_canvas_create(rootContent_);
  if (canvasBuf_) {
    lv_canvas_set_buffer(canvas_, canvasBuf_, VIDEO_MAX_W, VIDEO_MAX_H,
                         LV_IMG_CF_TRUE_COLOR);
    lv_canvas_fill_bg(canvas_, lv_color_black(), LV_OPA_COVER);
  }
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_text(listLabel_, g_video.path());
}

void Ui::leaveVideo() {
  g_video.close();
  if (canvasBuf_) {
    free(canvasBuf_);
    canvasBuf_ = nullptr;
  }
  canvas_ = nullptr;
}

void Ui::videoTick() {
  if (!g_video.isOpen()) return;
  if (!g_video.tick()) {
    leaveVideo();
    showScreen(UI_VIDEO);
    return;
  }
  if (!canvas_ || !canvasBuf_ || !g_video.frameRgb565()) return;
  int w = g_video.frameW();
  int h = g_video.frameH();
  if (w <= 0 || h <= 0 || w > VIDEO_MAX_W || h > VIDEO_MAX_H) return;
  const uint16_t* src = g_video.frameRgb565();
  for (int y = 0; y < h; y++) {
    for (int x = 0; x < w; x++) {
      canvasBuf_[y * VIDEO_MAX_W + x].full = src[y * w + x];
    }
  }
  lv_obj_invalidate(canvas_);
  if (listLabel_) {
    lv_label_set_text_fmt(listLabel_, "%s\n%dx%d %s", g_video.path(), w, h,
                          g_video.isPaused() ? "PAUSED" : "PLAY");
  }
}

void Ui::videoTogglePause() {
  if (!g_video.isOpen()) return;
  if (g_video.isPaused())
    g_video.resume();
  else
    g_video.pause();
}

void Ui::buildSolitaire() {
  g_solitaire.begin();
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_text(listLabel_, g_solitaire.status());
  lv_label_set_text(lv_label_create(rootContent_),
                    "Cursor+Confirm  Bottom=new deal");
  canvasBuf_ = (lv_color_t*)heap_caps_malloc(
      Solitaire::FB_W * Solitaire::FB_H * sizeof(lv_color_t), MALLOC_CAP_SPIRAM);
  if (!canvasBuf_)
    canvasBuf_ = (lv_color_t*)malloc(Solitaire::FB_W * Solitaire::FB_H *
                                     sizeof(lv_color_t));
  canvas_ = lv_canvas_create(rootContent_);
  if (canvasBuf_) {
    lv_canvas_set_buffer(canvas_, canvasBuf_, Solitaire::FB_W, Solitaire::FB_H,
                         LV_IMG_CF_TRUE_COLOR);
  }
  g_solitaire.draw();
}

void Ui::buildUno() {
  g_uno.begin();
  lv_obj_set_flex_flow(rootContent_, LV_FLEX_FLOW_COLUMN);
  listLabel_ = lv_label_create(rootContent_);
  lv_label_set_text(listLabel_, g_uno.status());
  lv_label_set_text(lv_label_create(rootContent_),
                    "Play matching card · Draw pile · Wild=pick color");
  canvasBuf_ = (lv_color_t*)heap_caps_malloc(
      UnoGame::FB_W * UnoGame::FB_H * sizeof(lv_color_t), MALLOC_CAP_SPIRAM);
  if (!canvasBuf_)
    canvasBuf_ =
        (lv_color_t*)malloc(UnoGame::FB_W * UnoGame::FB_H * sizeof(lv_color_t));
  canvas_ = lv_canvas_create(rootContent_);
  if (canvasBuf_) {
    lv_canvas_set_buffer(canvas_, canvasBuf_, UnoGame::FB_W, UnoGame::FB_H,
                         LV_IMG_CF_TRUE_COLOR);
  }
  g_uno.draw();
}

void Ui::leaveCardGame() {
  g_solitaire.stop();
  g_uno.stop();
  if (canvasBuf_) {
    free(canvasBuf_);
    canvasBuf_ = nullptr;
  }
  canvas_ = nullptr;
}

void Ui::cardGameTick() {
  if (screen_ == UI_GAME_UNO) {
    g_uno.tick();
    if (listLabel_) lv_label_set_text(listLabel_, g_uno.status());
  }
  const uint16_t* src = nullptr;
  int w = 0, h = 0;
  if (screen_ == UI_GAME_SOLITAIRE && g_solitaire.isActive()) {
    src = g_solitaire.framebuffer();
    w = Solitaire::FB_W;
    h = Solitaire::FB_H;
  } else if (screen_ == UI_GAME_UNO && g_uno.isActive()) {
    src = g_uno.framebuffer();
    w = UnoGame::FB_W;
    h = UnoGame::FB_H;
  }
  if (!src || !canvas_ || !canvasBuf_) return;
  for (int i = 0; i < w * h; i++) canvasBuf_[i].full = src[i];
  lv_obj_invalidate(canvas_);
}

