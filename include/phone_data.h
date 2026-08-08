#pragma once

#include "Config.h"
#include <stdint.h>

// ---------------------------------------------------------------------------
// Phone settings (PIN, profiles, radio)
// ---------------------------------------------------------------------------
enum SoundProfile : uint8_t {
  PROFILE_SILENT = 0,
  PROFILE_NORMAL = 1,
  PROFILE_LOUD = 2,
  PROFILE_OUTDOOR = 3,
};

struct PhoneSettings {
  char pin[8];           // 4–6 digits, empty = no lock
  bool lockEnabled;
  uint32_t lockTimeoutSec;  // auto-lock; 0 = only at boot
  char voicemailNumber[24];
  SoundProfile profile;
  bool soundsEnabled;
  bool airplaneMode;
  bool hotspotEnabled;   // ESP32 SoftAP
  bool btEnabled;        // Classic BT name advertised (HFP later)
  char hotspotSsid[24];
  char hotspotPass[24];
  char ringtonePath[80];  // /music/foo.mp3 or empty = beep
  char loraCallsign[12];  // legacy label (unused on air)
  uint32_t loraDeviceId;  // 0 = auto from MAC (Heltec mesh compatible)
  uint32_t loraTargetId;  // 0 = broadcast to all mesh nodes
};

class SettingsStore {
 public:
  bool load();
  bool save();
  PhoneSettings& get() { return s_; }
  const PhoneSettings& get() const { return s_; }
  bool checkPin(const char* pin) const;
  void setPin(const char* pin);
  void cycleProfile();
  const char* profileName() const;
  bool soundsOn() const;
  void toggleSounds();
  void cycleLockTimeout();

 private:
  PhoneSettings s_{"", false, 120, "", PROFILE_NORMAL, true, false, false,
                   false, "ESP-Phone", "phone1234", "", "ESP1", 0, 0};
};

extern SettingsStore g_settings;

// ---------------------------------------------------------------------------
// Contacts
// ---------------------------------------------------------------------------
static constexpr int CONTACTS_MAX = 48;
struct Contact {
  char name[40];
  char number[24];
  bool favorite;
};

class Contacts {
 public:
  bool load();
  bool save();
  int count() const { return count_; }
  const Contact* at(int i) const;
  Contact* atMut(int i);
  bool add(const char* name, const char* number);
  bool remove(int i);
  bool update(int i, const char* name, const char* number);
  bool toggleFavorite(int i);
  void sortFavoritesFirst();
  int findByNumber(const char* number) const;
  const char* nameForNumber(const char* number) const;
  static void initials(const char* name, char out[3]);

 private:
  Contact items_[CONTACTS_MAX];
  int count_ = 0;
};

extern Contacts g_contacts;

// ---------------------------------------------------------------------------
// Call log
// ---------------------------------------------------------------------------
enum CallDir : uint8_t { CALL_OUT = 0, CALL_IN = 1, CALL_MISSED = 2 };

static constexpr int CALLLOG_MAX = 30;
struct CallLogEntry {
  CallDir dir;
  char number[24];
  char name[40];
  uint32_t epochApprox;  // millis-based stamp at record time (display relative)
  uint16_t durationSec;
};

class CallLog {
 public:
  bool load();
  bool save();
  int count() const { return count_; }
  const CallLogEntry* at(int i) const;
  void add(CallDir dir, const char* number, const char* name, uint16_t durSec);
  int missedUnread() const { return missedUnread_; }
  void clearMissedUnread() { missedUnread_ = 0; }

 private:
  CallLogEntry items_[CALLLOG_MAX];
  int count_ = 0;
  int missedUnread_ = 0;
};

extern CallLog g_callLog;

// ---------------------------------------------------------------------------
// SMS threads (local store; sync from modem inbox)
// ---------------------------------------------------------------------------
static constexpr int SMS_THREADS_MAX = 10;
static constexpr int SMS_PER_THREAD = 8;
struct SmsMsg {
  bool outbound;
  bool read;
  char text[160];
  uint32_t stampMs;
};
struct SmsThread {
  char number[24];
  char name[40];
  int msgCount;
  SmsMsg msgs[SMS_PER_THREAD];
  int unread;
};

class SmsStore {
 public:
  bool load();
  bool save();
  int threadCount() const { return tcount_; }
  SmsThread* threadAt(int i);
  const SmsThread* threadAt(int i) const;
  int findThread(const char* number) const;
  SmsThread* getOrCreate(const char* number);
  void addInbound(const char* number, const char* text);
  void addOutbound(const char* number, const char* text);
  void markThreadRead(int ti);
  int totalUnread() const;

 private:
  SmsThread threads_[SMS_THREADS_MAX];
  int tcount_ = 0;
};

extern SmsStore g_smsStore;

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------
enum NotifKind : uint8_t {
  NOTIF_SMS = 0,
  NOTIF_MISSED_CALL,
  NOTIF_ALARM,
  NOTIF_INFO,
};

static constexpr int NOTIF_MAX = 16;
struct Notification {
  NotifKind kind;
  char title[40];
  char body[96];
  uint32_t stampMs;
  bool read;
};

class NotifCenter {
 public:
  bool load();
  bool save();
  int count() const { return count_; }
  int unread() const;
  const Notification* at(int i) const;
  void push(NotifKind k, const char* title, const char* body);
  void markAllRead();
  void clear();

 private:
  Notification items_[NOTIF_MAX];
  int count_ = 0;
};

extern NotifCenter g_notifs;

// ---------------------------------------------------------------------------
// Alarms
// ---------------------------------------------------------------------------
static constexpr int ALARMS_MAX = 8;
struct Alarm {
  bool enabled;
  uint8_t hour;    // 0–23
  uint8_t minute;  // 0–59
  char label[32];
  bool firedToday;
};

class AlarmClock {
 public:
  bool load();
  bool save();
  int count() const { return count_; }
  Alarm* at(int i);
  const Alarm* at(int i) const;
  bool add(uint8_t h, uint8_t m, const char* label);
  bool remove(int i);
  bool toggle(int i);
  void setTime(int y, int mo, int d, int h, int mi, int s);
  bool timeValid() const { return timeValid_; }
  void getTime(int& h, int& mi, int& s) const;
  void getDate(int& y, int& mo, int& d) const;
  void tick();  // call ~1 Hz — fires notifications
  void syncFromModem();  // AT+CCLK?
  bool isRinging() const { return ringingIndex_ >= 0; }
  void snooze(uint8_t minutes = 9);
  void dismissRinging();
  void formatNextAlarm(char* buf, size_t len) const;

 private:
  Alarm items_[ALARMS_MAX];
  int count_ = 0;
  bool timeValid_ = false;
  int year_ = 2026, month_ = 1, day_ = 1;
  int hour_ = 0, minute_ = 0, second_ = 0;
  uint32_t lastTickMs_ = 0;
  int ringingIndex_ = -1;
  int snoozeIndex_ = -1;
  uint32_t snoozeAtMs_ = 0;
};

extern AlarmClock g_clock;

// ---------------------------------------------------------------------------
// Calendar (simple day events + reminders)
// ---------------------------------------------------------------------------
static constexpr int CAL_MAX = 28;
struct CalEvent {
  int year, month, day;
  uint8_t hour, minute;
  char title[48];
  bool reminded;
  bool synced;  // imported from Google ICS
};

class Calendar {
 public:
  bool load();
  bool save();
  int count() const { return count_; }
  const CalEvent* at(int i) const;
  bool add(int y, int mo, int d, uint8_t h, uint8_t mi, const char* title,
           bool synced = false);
  bool remove(int i);
  void clearSynced();
  // events on a given day (writes indices into outIdx, returns count)
  int eventsOn(int y, int mo, int d, int* outIdx, int maxOut) const;
  void tickReminders();  // ~1 Hz with valid clock

 private:
  CalEvent items_[CAL_MAX];
  int count_ = 0;
};

extern Calendar g_calendar;

// Cached weather line for UI
struct WeatherCache {
  bool valid = false;
  float tempC = 0;
  int code = 0;
  char summary[64] = {0};
  uint32_t fetchedMs = 0;
};
extern WeatherCache g_weather;

void phonePlayNotify(uint16_t freqHz, uint32_t ms);
void phonePlayRingtone();
