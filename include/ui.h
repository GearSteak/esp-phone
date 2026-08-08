#pragma once

#include "Config.h"
#include "notes_todo.h"

enum UiScreen : uint8_t {
  UI_MAIN = 0,
  UI_PHONE,
  UI_CALL,
  UI_MESSAGES,
  UI_COMPOSE,
  UI_GAMES_MENU,
  UI_GAME_SNAKE,
  UI_GAME_PONG,
  UI_GAME_TETRIS,
  UI_SETTINGS,
  UI_CAMERA,
  UI_MUSIC,
  UI_EBOOKS,
  UI_EBOOK_READ,
  UI_AUDIOBOOKS,
  UI_GPS,
  UI_NOTES,
  UI_NOTE_EDIT,
  UI_TODOS,
  UI_LOCK,
  UI_CONTACTS,
  UI_CONTACT_EDIT,
  UI_CALL_LOG,
  UI_SMS_THREADS,
  UI_SMS_THREAD,
  UI_NOTIFS,
  UI_CLOCK,
  UI_ALARMS,
  UI_TOOLS,
  UI_CALC,
  UI_CONVERT,
  UI_WEATHER,
  UI_CALENDAR,
  UI_MEDIA,
  UI_EMAIL,
  UI_EMAIL_READ,
  UI_BROWSER,
  UI_SET_SECURITY,
  UI_SET_NETWORK,
  UI_SET_ACCOUNTS,
  UI_SET_SOUNDS,
  UI_SET_ABOUT,
  UI_COMM,
  UI_GALLERY,
  UI_RECORDER,
  UI_RINGTONE,
  UI_HELP,
  UI_VIDEO,
  UI_VIDEO_PLAY,
  UI_GAME_SOLITAIRE,
  UI_GAME_UNO,
  UI_LORA,
};

class Ui {
 public:
  bool begin();
  void loop();
  void showScreen(UiScreen s);
  UiScreen current() const { return screen_; }
  bool isLocked() const { return locked_; }

  void setBackgroundColor(uint32_t hexRgb);
  void applyTheme();

  void updateStatusBar(const PhoneStatus& st);
  void setCallUi(CallState state, const char* remote, uint32_t seconds);
  void notifyIncoming(const char* from);
  void appendDialChar(char c);
  void backspaceDial();
  void clearDial();
  const char* dialBuffer() const;

  void onKey(uint16_t code, char ascii, bool shifted);
  bool sendComposeSms();
  void setComposeToDigit(char c);
  void appendComposeBody(char c);

  int fileCount() const { return fileCount_; }
  int fileIndex() const { return fileIndex_; }
  const char* fileAt(int i) const {
    return (i >= 0 && i < fileCount_) ? fileList_[i] : "";
  }
  void selectFileDelta(int d);
  void playSelectedMusic();
  void playSelectedAudiobook();
  void openSelectedEbook();
  void snapCamera();

  void todoToggleSelected();
  void todoAddDraft();
  void todoDeleteSelected();
  void notesOpenSelected();
  void notesNew();
  void notesSaveEdit();
  void notesDeleteSelected();
  void gpsToggle();
  void refreshGpsUi() { refreshGpsLabel(); }

  void lockNow();
  void tryUnlock();
  void contactDial();
  void contactSms();
  void contactSave();
  void contactDelete();
  void contactNew();
  void contactEditSelected();
  void saveVoicemailFromDraft();
  void alarmSnooze();
  void openSmsThread();
  void smsReplySend();
  void callLogDial();
  void alarmAddDefault();
  void alarmToggleSelected();
  void alarmDeleteSelected();
  void setPinFromDraft();
  void syncClock();
  void notifsClear();
  void markActivity();

  void cycleProfile();
  void toggleAirplane();
  void toggleHotspot();
  void toggleBluetooth();
  void dialVoicemail();
  void clearPin();
  void calcEquals();
  void calcClear();
  void convertRun();
  void weatherRefresh();
  void shareLocationSms();
  void calendarAddToday();
  void calendarDeleteSelected();
  void convertCycleCat();
  void convertCycleFrom();
  void convertCycleTo();
  void calendarSyncGoogle();
  void emailRefresh();
  void emailOpenSelected();
  void emailWifiConnect();
  void browserGo();
  void browserHome();
  void browserNext();
  void browserPrev();
  void toggleSounds();
  void cycleLockTimeout();
  void contactToggleFav();
  void smsQuickReply(int which);
  void rejectCall();
  void pickRingtone();
  void recorderToggle();
  void recorderPlayLast();
  void playSelectedVideo();
  void videoTogglePause();
  void loraSendDraft();
  void loraSendSos();
  void saveLoraDeviceIdFromDraft();
  void saveLoraTargetFromDraft();
  void refreshLoraUi();

 private:
  UiScreen screen_ = UI_MAIN;
  UiScreen preLockScreen_ = UI_MAIN;
  bool locked_ = false;
  char dial_[32] = {0};
  char compose_[256] = {0};
  char composeTo_[32] = {0};
  bool composeFocusTo_ = true;
  int focusIndex_ = 0;
  int focusCount_ = 0;
  uint32_t bgColor_ = UI_BG_COLOR;
  char fileList_[MEDIA_MAX_FILES][MEDIA_PATH_LEN];
  int fileCount_ = 0;
  int fileIndex_ = 0;

  int listIndex_ = 0;
  int noteEditIndex_ = -1;
  char draft_[NOTE_BODY_LEN] = {0};
  char draftTitle_[NOTE_TITLE_LEN] = {0};
  bool draftFocusTitle_ = true;
  char pinBuf_[8] = {0};
  int smsThreadIndex_ = 0;
  uint32_t lastActivityMs_ = 0;
  uint16_t activeCallDur_ = 0;
  CallState prevCallState_ = CALL_IDLE;

  // calculator / converter state
  char calcExpr_[64] = {0};
  int convCat_ = 0;
  int convFrom_ = 0;
  int convTo_ = 1;
  char convValue_[24] = {0};
  char browserUrl_[128] = {0};

  int contactEditIndex_ = -1;

  void buildMain();
  void buildPhone();
  void buildCall();
  void buildMessages();
  void buildCompose();
  void buildGamesMenu();
  void buildSettings();
  void buildSetSecurity();
  void buildSetNetwork();
  void buildSetAccounts();
  void buildSetSounds();
  void buildSetAbout();
  void buildComm();
  void buildGallery();
  void buildRecorder();
  void buildRingtone();
  void buildHelp();
  void buildCamera();
  void buildMusic();
  void buildEbooks();
  void buildEbookRead();
  void buildAudiobooks();
  void buildVideo();
  void buildVideoPlay();
  void buildSolitaire();
  void buildUno();
  void buildLora();
  void buildGps();
  void buildNotes();
  void buildNoteEdit();
  void buildTodos();
  void buildLock();
  void buildContacts();
  void buildContactEdit();
  void buildCallLog();
  void buildSmsThreads();
  void buildSmsThread();
  void buildNotifs();
  void buildClock();
  void buildAlarms();
  void buildTools();
  void buildCalc();
  void buildConvert();
  void buildWeather();
  void buildCalendar();
  void buildMedia();
  void buildEmail();
  void buildEmailRead();
  void buildBrowser();
  void clearRoot();
  void moveFocus(int delta);
  void activateFocus();
  void handleGlobalKeys(uint16_t code, char ascii);
  void setupChrome();
  void setupPointer();
  bool usesPointer() const;
  void syncPointerUi();
  void nudgeCursor(int dx, int dy);
  void pointerClick();
  void updatePointerHover();
  void refreshFileListLabel();
  void refreshListLabel();
  void cameraTick();
  void leaveCamera();
  void videoTick();
  void leaveVideo();
  void cardGameTick();
  void leaveCardGame();
  void refreshEbookPage();
  void refreshGpsLabel();
  void refreshLockClock();
  void refreshNetworkStatus();
  void pollCallState();
  void refreshCalcLabel();
  void refreshConvertLabel();
};

extern Ui g_ui;
