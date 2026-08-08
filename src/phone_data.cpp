#include "phone_data.h"
#include "storage.h"
#include "modem.h"
#include "audio.h"
#include "media_player.h"
#include <ArduinoJson.h>
#include <string.h>
#include <stdlib.h>
#include <ctype.h>
#include <stdio.h>

SettingsStore g_settings;
Contacts g_contacts;
CallLog g_callLog;
SmsStore g_smsStore;
NotifCenter g_notifs;
AlarmClock g_clock;

static void normNumber(const char* in, char* out, size_t outLen) {
  size_t j = 0;
  for (size_t i = 0; in && in[i] && j + 1 < outLen; i++) {
    if (isdigit((unsigned char)in[i]) || in[i] == '+') out[j++] = in[i];
  }
  out[j] = 0;
}

// ---- Settings ----
bool SettingsStore::load() {
  File f = Storage::fs().open("/settings.json", FILE_READ);
  if (!f) return true;
  JsonDocument doc;
  if (deserializeJson(doc, f)) {
    f.close();
    return false;
  }
  f.close();
  strncpy(s_.pin, doc["pin"] | "", sizeof(s_.pin) - 1);
  s_.lockEnabled = doc["lockEnabled"] | false;
  s_.lockTimeoutSec = doc["lockTimeoutSec"] | 120;
  strncpy(s_.voicemailNumber, doc["voicemail"] | "", sizeof(s_.voicemailNumber) - 1);
  s_.profile = (SoundProfile)(int)(doc["profile"] | (int)PROFILE_NORMAL);
  s_.soundsEnabled = doc["sounds"] | true;
  s_.airplaneMode = doc["airplane"] | false;
  s_.hotspotEnabled = doc["hotspot"] | false;
  s_.btEnabled = doc["bt"] | false;
  strncpy(s_.hotspotSsid, doc["hsSsid"] | "ESP-Phone", sizeof(s_.hotspotSsid) - 1);
  strncpy(s_.hotspotPass, doc["hsPass"] | "phone1234", sizeof(s_.hotspotPass) - 1);
  strncpy(s_.ringtonePath, doc["ringtone"] | "", sizeof(s_.ringtonePath) - 1);
  strncpy(s_.loraCallsign, doc["loraCs"] | "ESP1", sizeof(s_.loraCallsign) - 1);
  s_.loraDeviceId = doc["loraDevId"] | 0;
  s_.loraTargetId = doc["loraTargetId"] | 0;
  return true;
}

bool SettingsStore::save() {
  JsonDocument doc;
  doc["pin"] = s_.pin;
  doc["lockEnabled"] = s_.lockEnabled;
  doc["lockTimeoutSec"] = s_.lockTimeoutSec;
  doc["voicemail"] = s_.voicemailNumber;
  doc["profile"] = (int)s_.profile;
  doc["sounds"] = s_.soundsEnabled;
  doc["airplane"] = s_.airplaneMode;
  doc["hotspot"] = s_.hotspotEnabled;
  doc["bt"] = s_.btEnabled;
  doc["hsSsid"] = s_.hotspotSsid;
  doc["hsPass"] = s_.hotspotPass;
  doc["ringtone"] = s_.ringtonePath;
  doc["loraCs"] = s_.loraCallsign;
  doc["loraDevId"] = s_.loraDeviceId;
  doc["loraTargetId"] = s_.loraTargetId;
  File f = Storage::fs().open("/settings.json", FILE_WRITE);
  if (!f) return false;
  serializeJson(doc, f);
  f.close();
  return true;
}

bool SettingsStore::checkPin(const char* pin) const {
  if (!s_.lockEnabled || !s_.pin[0]) return true;
  return pin && strcmp(pin, s_.pin) == 0;
}

void SettingsStore::setPin(const char* pin) {
  strncpy(s_.pin, pin ? pin : "", sizeof(s_.pin) - 1);
  s_.lockEnabled = s_.pin[0] != 0;
  save();
}

void SettingsStore::cycleProfile() {
  s_.profile = (SoundProfile)(((int)s_.profile + 1) % 4);
  save();
}

const char* SettingsStore::profileName() const {
  switch (s_.profile) {
    case PROFILE_SILENT: return "Silent";
    case PROFILE_LOUD: return "Loud";
    case PROFILE_OUTDOOR: return "Outdoor";
    default: return "Normal";
  }
}

bool SettingsStore::soundsOn() const {
  return s_.soundsEnabled && s_.profile != PROFILE_SILENT;
}

void SettingsStore::toggleSounds() {
  s_.soundsEnabled = !s_.soundsEnabled;
  save();
}

void SettingsStore::cycleLockTimeout() {
  // 0 = boot only, then 30s / 2m / 5m / 15m
  const uint32_t steps[] = {0, 30, 120, 300, 900};
  int i = 0;
  for (; i < 5; i++)
    if (s_.lockTimeoutSec == steps[i]) break;
  s_.lockTimeoutSec = steps[(i + 1) % 5];
  save();
}

WeatherCache g_weather;
Calendar g_calendar;

void phonePlayNotify(uint16_t freqHz, uint32_t ms) {
  if (!g_settings.soundsOn()) return;
  float amp = 6000.0f;
  if (g_settings.get().profile == PROFILE_LOUD) amp = 12000.0f;
  if (g_settings.get().profile == PROFILE_OUTDOOR) amp = 16000.0f;
  g_audio.playTone(freqHz, ms, amp);
}

void phonePlayRingtone() {
  if (!g_settings.soundsOn()) return;
  const char* path = g_settings.get().ringtonePath;
  if (path && path[0]) {
    // Best-effort MP3 ring; falls back to tones if play fails
    extern MediaPlayer g_media;
    if (g_media.play(path, MEDIA_MUSIC)) return;
  }
  phonePlayNotify(880, 180);
  delay(80);
  phonePlayNotify(1175, 220);
}

// ---- Contacts ----
bool Contacts::load() {
  count_ = 0;
  File f = Storage::fs().open("/contacts.json", FILE_READ);
  if (!f) return true;
  JsonDocument doc;
  if (deserializeJson(doc, f)) {
    f.close();
    return false;
  }
  f.close();
  for (JsonObject o : doc["contacts"].as<JsonArray>()) {
    if (count_ >= CONTACTS_MAX) break;
    strncpy(items_[count_].name, o["name"] | "", sizeof(items_[0].name) - 1);
    strncpy(items_[count_].number, o["number"] | "", sizeof(items_[0].number) - 1);
    items_[count_].favorite = o["fav"] | false;
    count_++;
  }
  return true;
}

bool Contacts::save() {
  JsonDocument doc;
  JsonArray arr = doc["contacts"].to<JsonArray>();
  for (int i = 0; i < count_; i++) {
    JsonObject o = arr.add<JsonObject>();
    o["name"] = items_[i].name;
    o["number"] = items_[i].number;
    o["fav"] = items_[i].favorite;
  }
  File f = Storage::fs().open("/contacts.json", FILE_WRITE);
  if (!f) return false;
  serializeJson(doc, f);
  f.close();
  return true;
}

const Contact* Contacts::at(int i) const {
  return (i >= 0 && i < count_) ? &items_[i] : nullptr;
}
Contact* Contacts::atMut(int i) {
  return (i >= 0 && i < count_) ? &items_[i] : nullptr;
}

bool Contacts::add(const char* name, const char* number) {
  if (count_ >= CONTACTS_MAX || !number || !number[0]) return false;
  strncpy(items_[count_].name, name && name[0] ? name : number,
          sizeof(items_[0].name) - 1);
  normNumber(number, items_[count_].number, sizeof(items_[0].number));
  items_[count_].favorite = false;
  count_++;
  return save();
}

bool Contacts::remove(int i) {
  if (i < 0 || i >= count_) return false;
  for (int k = i; k < count_ - 1; k++) items_[k] = items_[k + 1];
  count_--;
  return save();
}

bool Contacts::update(int i, const char* name, const char* number) {
  if (i < 0 || i >= count_) return false;
  if (name) strncpy(items_[i].name, name, sizeof(items_[0].name) - 1);
  if (number) normNumber(number, items_[i].number, sizeof(items_[0].number));
  return save();
}

int Contacts::findByNumber(const char* number) const {
  char n[24];
  normNumber(number, n, sizeof(n));
  for (int i = 0; i < count_; i++) {
    char c[24];
    normNumber(items_[i].number, c, sizeof(c));
    if (strcmp(c, n) == 0) return i;
  }
  return -1;
}

const char* Contacts::nameForNumber(const char* number) const {
  int i = findByNumber(number);
  return i >= 0 ? items_[i].name : nullptr;
}

bool Contacts::toggleFavorite(int i) {
  if (i < 0 || i >= count_) return false;
  items_[i].favorite = !items_[i].favorite;
  save();
  sortFavoritesFirst();
  return true;
}

void Contacts::sortFavoritesFirst() {
  // Simple stable-ish partition: favorites bubble up
  for (int i = 0; i < count_; i++) {
    for (int j = i + 1; j < count_; j++) {
      if (!items_[i].favorite && items_[j].favorite) {
        Contact tmp = items_[i];
        items_[i] = items_[j];
        items_[j] = tmp;
      }
    }
  }
}

void Contacts::initials(const char* name, char out[3]) {
  out[0] = out[1] = '?';
  out[2] = 0;
  if (!name || !name[0]) return;
  out[0] = (char)toupper((unsigned char)name[0]);
  const char* sp = strchr(name, ' ');
  if (sp && sp[1])
    out[1] = (char)toupper((unsigned char)sp[1]);
  else if (name[1])
    out[1] = (char)toupper((unsigned char)name[1]);
}

// ---- Call log ----
bool CallLog::load() {
  count_ = 0;
  File f = Storage::fs().open("/call_log.json", FILE_READ);
  if (!f) return true;
  JsonDocument doc;
  if (deserializeJson(doc, f)) {
    f.close();
    return false;
  }
  f.close();
  for (JsonObject o : doc["log"].as<JsonArray>()) {
    if (count_ >= CALLLOG_MAX) break;
    items_[count_].dir = (CallDir)(int)(o["dir"] | 0);
    strncpy(items_[count_].number, o["number"] | "", sizeof(items_[0].number) - 1);
    strncpy(items_[count_].name, o["name"] | "", sizeof(items_[0].name) - 1);
    items_[count_].epochApprox = o["t"] | 0;
    items_[count_].durationSec = o["dur"] | 0;
    count_++;
  }
  return true;
}

bool CallLog::save() {
  JsonDocument doc;
  JsonArray arr = doc["log"].to<JsonArray>();
  for (int i = 0; i < count_; i++) {
    JsonObject o = arr.add<JsonObject>();
    o["dir"] = (int)items_[i].dir;
    o["number"] = items_[i].number;
    o["name"] = items_[i].name;
    o["t"] = items_[i].epochApprox;
    o["dur"] = items_[i].durationSec;
  }
  File f = Storage::fs().open("/call_log.json", FILE_WRITE);
  if (!f) return false;
  serializeJson(doc, f);
  f.close();
  return true;
}

const CallLogEntry* CallLog::at(int i) const {
  return (i >= 0 && i < count_) ? &items_[i] : nullptr;
}

void CallLog::add(CallDir dir, const char* number, const char* name,
                  uint16_t durSec) {
  if (count_ >= CALLLOG_MAX) {
    for (int i = CALLLOG_MAX - 1; i > 0; i--) items_[i] = items_[i - 1];
  } else {
    for (int i = count_; i > 0; i--) items_[i] = items_[i - 1];
    count_++;
  }
  items_[0].dir = dir;
  strncpy(items_[0].number, number ? number : "", sizeof(items_[0].number) - 1);
  if (name && name[0])
    strncpy(items_[0].name, name, sizeof(items_[0].name) - 1);
  else {
    const char* cn = g_contacts.nameForNumber(number);
    strncpy(items_[0].name, cn ? cn : "", sizeof(items_[0].name) - 1);
  }
  items_[0].epochApprox = millis();
  items_[0].durationSec = durSec;
  if (dir == CALL_MISSED) missedUnread_++;
  save();
}

// ---- SMS store ----
bool SmsStore::load() {
  tcount_ = 0;
  File f = Storage::fs().open("/sms_store.json", FILE_READ);
  if (!f) return true;
  JsonDocument doc;
  if (deserializeJson(doc, f)) {
    f.close();
    return false;
  }
  f.close();
  for (JsonObject th : doc["threads"].as<JsonArray>()) {
    if (tcount_ >= SMS_THREADS_MAX) break;
    SmsThread& t = threads_[tcount_];
    memset(&t, 0, sizeof(t));
    strncpy(t.number, th["number"] | "", sizeof(t.number) - 1);
    strncpy(t.name, th["name"] | "", sizeof(t.name) - 1);
    t.unread = th["unread"] | 0;
    for (JsonObject m : th["msgs"].as<JsonArray>()) {
      if (t.msgCount >= SMS_PER_THREAD) break;
      SmsMsg& msg = t.msgs[t.msgCount++];
      msg.outbound = m["out"] | false;
      msg.read = m["read"] | true;
      strncpy(msg.text, m["text"] | "", sizeof(msg.text) - 1);
      msg.stampMs = m["t"] | 0;
    }
    tcount_++;
  }
  return true;
}

bool SmsStore::save() {
  JsonDocument doc;
  JsonArray arr = doc["threads"].to<JsonArray>();
  for (int i = 0; i < tcount_; i++) {
    JsonObject th = arr.add<JsonObject>();
    th["number"] = threads_[i].number;
    th["name"] = threads_[i].name;
    th["unread"] = threads_[i].unread;
    JsonArray msgs = th["msgs"].to<JsonArray>();
    for (int j = 0; j < threads_[i].msgCount; j++) {
      JsonObject m = msgs.add<JsonObject>();
      m["out"] = threads_[i].msgs[j].outbound;
      m["read"] = threads_[i].msgs[j].read;
      m["text"] = threads_[i].msgs[j].text;
      m["t"] = threads_[i].msgs[j].stampMs;
    }
  }
  File f = Storage::fs().open("/sms_store.json", FILE_WRITE);
  if (!f) return false;
  serializeJson(doc, f);
  f.close();
  return true;
}

SmsThread* SmsStore::threadAt(int i) {
  return (i >= 0 && i < tcount_) ? &threads_[i] : nullptr;
}
const SmsThread* SmsStore::threadAt(int i) const {
  return (i >= 0 && i < tcount_) ? &threads_[i] : nullptr;
}

int SmsStore::findThread(const char* number) const {
  char n[24];
  normNumber(number, n, sizeof(n));
  for (int i = 0; i < tcount_; i++) {
    char c[24];
    normNumber(threads_[i].number, c, sizeof(c));
    if (strcmp(c, n) == 0) return i;
  }
  return -1;
}

SmsThread* SmsStore::getOrCreate(const char* number) {
  int i = findThread(number);
  if (i >= 0) return &threads_[i];
  if (tcount_ >= SMS_THREADS_MAX) return nullptr;
  SmsThread& t = threads_[tcount_++];
  memset(&t, 0, sizeof(t));
  normNumber(number, t.number, sizeof(t.number));
  const char* cn = g_contacts.nameForNumber(t.number);
  strncpy(t.name, cn ? cn : t.number, sizeof(t.name) - 1);
  return &t;
}

static void pushMsg(SmsThread& t, bool out, const char* text, bool read) {
  if (t.msgCount >= SMS_PER_THREAD) {
    for (int i = 0; i < SMS_PER_THREAD - 1; i++) t.msgs[i] = t.msgs[i + 1];
    t.msgCount = SMS_PER_THREAD - 1;
  }
  SmsMsg& m = t.msgs[t.msgCount++];
  m.outbound = out;
  m.read = read;
  strncpy(m.text, text ? text : "", sizeof(m.text) - 1);
  m.stampMs = millis();
}

void SmsStore::addInbound(const char* number, const char* text) {
  SmsThread* t = getOrCreate(number);
  if (!t) return;
  pushMsg(*t, false, text, false);
  t->unread++;
  // Move thread to front
  int idx = (int)(t - threads_);
  if (idx > 0) {
    SmsThread tmp = *t;
    for (int i = idx; i > 0; i--) threads_[i] = threads_[i - 1];
    threads_[0] = tmp;
  }
  save();
}

void SmsStore::addOutbound(const char* number, const char* text) {
  SmsThread* t = getOrCreate(number);
  if (!t) return;
  pushMsg(*t, true, text, true);
  save();
}

void SmsStore::markThreadRead(int ti) {
  SmsThread* t = threadAt(ti);
  if (!t) return;
  t->unread = 0;
  for (int i = 0; i < t->msgCount; i++) t->msgs[i].read = true;
  save();
}

int SmsStore::totalUnread() const {
  int u = 0;
  for (int i = 0; i < tcount_; i++) u += threads_[i].unread;
  return u;
}

// ---- Notifications ----
bool NotifCenter::load() {
  count_ = 0;
  File f = Storage::fs().open("/notifs.json", FILE_READ);
  if (!f) return true;
  JsonDocument doc;
  if (deserializeJson(doc, f)) {
    f.close();
    return false;
  }
  f.close();
  for (JsonObject o : doc["n"].as<JsonArray>()) {
    if (count_ >= NOTIF_MAX) break;
    items_[count_].kind = (NotifKind)(int)(o["k"] | 0);
    strncpy(items_[count_].title, o["t"] | "", sizeof(items_[0].title) - 1);
    strncpy(items_[count_].body, o["b"] | "", sizeof(items_[0].body) - 1);
    items_[count_].stampMs = o["s"] | 0;
    items_[count_].read = o["r"] | false;
    count_++;
  }
  return true;
}

bool NotifCenter::save() {
  JsonDocument doc;
  JsonArray arr = doc["n"].to<JsonArray>();
  for (int i = 0; i < count_; i++) {
    JsonObject o = arr.add<JsonObject>();
    o["k"] = (int)items_[i].kind;
    o["t"] = items_[i].title;
    o["b"] = items_[i].body;
    o["s"] = items_[i].stampMs;
    o["r"] = items_[i].read;
  }
  File f = Storage::fs().open("/notifs.json", FILE_WRITE);
  if (!f) return false;
  serializeJson(doc, f);
  f.close();
  return true;
}

int NotifCenter::unread() const {
  int u = 0;
  for (int i = 0; i < count_; i++)
    if (!items_[i].read) u++;
  return u;
}

const Notification* NotifCenter::at(int i) const {
  return (i >= 0 && i < count_) ? &items_[i] : nullptr;
}

void NotifCenter::push(NotifKind k, const char* title, const char* body) {
  if (count_ >= NOTIF_MAX) {
    for (int i = NOTIF_MAX - 1; i > 0; i--) items_[i] = items_[i - 1];
  } else {
    for (int i = count_; i > 0; i--) items_[i] = items_[i - 1];
    count_++;
  }
  items_[0].kind = k;
  strncpy(items_[0].title, title ? title : "", sizeof(items_[0].title) - 1);
  strncpy(items_[0].body, body ? body : "", sizeof(items_[0].body) - 1);
  items_[0].stampMs = millis();
  items_[0].read = false;
  save();
}

void NotifCenter::markAllRead() {
  for (int i = 0; i < count_; i++) items_[i].read = true;
  save();
}

void NotifCenter::clear() {
  count_ = 0;
  save();
}

// ---- Alarms / clock ----
bool AlarmClock::load() {
  count_ = 0;
  File f = Storage::fs().open("/alarms.json", FILE_READ);
  if (!f) return true;
  JsonDocument doc;
  if (deserializeJson(doc, f)) {
    f.close();
    return false;
  }
  f.close();
  for (JsonObject o : doc["alarms"].as<JsonArray>()) {
    if (count_ >= ALARMS_MAX) break;
    items_[count_].enabled = o["on"] | true;
    items_[count_].hour = o["h"] | 7;
    items_[count_].minute = o["m"] | 0;
    strncpy(items_[count_].label, o["label"] | "Alarm", sizeof(items_[0].label) - 1);
    items_[count_].firedToday = false;
    count_++;
  }
  return true;
}

bool AlarmClock::save() {
  JsonDocument doc;
  JsonArray arr = doc["alarms"].to<JsonArray>();
  for (int i = 0; i < count_; i++) {
    JsonObject o = arr.add<JsonObject>();
    o["on"] = items_[i].enabled;
    o["h"] = items_[i].hour;
    o["m"] = items_[i].minute;
    o["label"] = items_[i].label;
  }
  File f = Storage::fs().open("/alarms.json", FILE_WRITE);
  if (!f) return false;
  serializeJson(doc, f);
  f.close();
  return true;
}

Alarm* AlarmClock::at(int i) {
  return (i >= 0 && i < count_) ? &items_[i] : nullptr;
}
const Alarm* AlarmClock::at(int i) const {
  return (i >= 0 && i < count_) ? &items_[i] : nullptr;
}

bool AlarmClock::add(uint8_t h, uint8_t m, const char* label) {
  if (count_ >= ALARMS_MAX) return false;
  items_[count_].enabled = true;
  items_[count_].hour = h % 24;
  items_[count_].minute = m % 60;
  strncpy(items_[count_].label, label ? label : "Alarm",
          sizeof(items_[0].label) - 1);
  items_[count_].firedToday = false;
  count_++;
  return save();
}

bool AlarmClock::remove(int i) {
  if (i < 0 || i >= count_) return false;
  if (ringingIndex_ == i) ringingIndex_ = -1;
  else if (ringingIndex_ > i) ringingIndex_--;
  if (snoozeIndex_ == i) {
    snoozeIndex_ = -1;
    snoozeAtMs_ = 0;
  } else if (snoozeIndex_ > i) {
    snoozeIndex_--;
  }
  for (int k = i; k < count_ - 1; k++) items_[k] = items_[k + 1];
  count_--;
  return save();
}

bool AlarmClock::toggle(int i) {
  if (i < 0 || i >= count_) return false;
  items_[i].enabled = !items_[i].enabled;
  items_[i].firedToday = false;
  return save();
}

void AlarmClock::setTime(int y, int mo, int d, int h, int mi, int s) {
  year_ = y;
  month_ = mo;
  day_ = d;
  hour_ = h;
  minute_ = mi;
  second_ = s;
  timeValid_ = true;
  lastTickMs_ = millis();
  for (int i = 0; i < count_; i++) items_[i].firedToday = false;
}

void AlarmClock::getTime(int& h, int& mi, int& s) const {
  h = hour_;
  mi = minute_;
  s = second_;
}

void AlarmClock::getDate(int& y, int& mo, int& d) const {
  y = year_;
  mo = month_;
  d = day_;
}

void AlarmClock::tick() {
  if (!timeValid_) return;
  uint32_t now = millis();
  if (now - lastTickMs_ < 1000) return;
  uint32_t elapsed = (now - lastTickMs_) / 1000;
  lastTickMs_ += elapsed * 1000;
  second_ += (int)elapsed;
  while (second_ >= 60) {
    second_ -= 60;
    minute_++;
  }
  while (minute_ >= 60) {
    minute_ -= 60;
    hour_++;
  }
  if (hour_ >= 24) {
    hour_ = 0;
    day_++;
    for (int i = 0; i < count_; i++) items_[i].firedToday = false;
  }

  for (int i = 0; i < count_; i++) {
    if (!items_[i].enabled || items_[i].firedToday) continue;
    if (items_[i].hour == hour_ && items_[i].minute == minute_ && second_ < 2) {
      items_[i].firedToday = true;
      ringingIndex_ = i;
      g_notifs.push(NOTIF_ALARM, items_[i].label, "Alarm!");
      phonePlayNotify(1000, 700);
    }
  }

  if (snoozeAtMs_ && snoozeIndex_ >= 0 && millis() >= snoozeAtMs_) {
    snoozeAtMs_ = 0;
    ringingIndex_ = snoozeIndex_;
    const char* lab =
        (snoozeIndex_ < count_) ? items_[snoozeIndex_].label : "Alarm";
    g_notifs.push(NOTIF_ALARM, lab, "Snooze!");
    phonePlayNotify(1000, 700);
  }
}

void AlarmClock::snooze(uint8_t minutes) {
  if (ringingIndex_ < 0 && snoozeIndex_ < 0) return;
  if (minutes == 0) minutes = 9;
  int i = ringingIndex_ >= 0 ? ringingIndex_ : snoozeIndex_;
  ringingIndex_ = -1;
  snoozeIndex_ = i;
  snoozeAtMs_ = millis() + (uint32_t)minutes * 60000UL;
}

void AlarmClock::dismissRinging() { ringingIndex_ = -1; }

void AlarmClock::formatNextAlarm(char* buf, size_t len) const {
  if (!buf || !len) return;
  buf[0] = 0;
  if (snoozeAtMs_ && snoozeIndex_ >= 0 && millis() < snoozeAtMs_) {
    unsigned remMin =
        (unsigned)((snoozeAtMs_ - millis() + 59999UL) / 60000UL);
    snprintf(buf, len, "Snooze ~%um", remMin);
    return;
  }
  if (!timeValid_ || count_ == 0) {
    snprintf(buf, len, "No alarm");
    return;
  }
  int now = hour_ * 60 + minute_;
  int bestDelta = 24 * 60 + 1;
  int bestH = 0, bestM = 0;
  for (int i = 0; i < count_; i++) {
    if (!items_[i].enabled) continue;
    int am = items_[i].hour * 60 + items_[i].minute;
    int delta = am - now;
    if (delta < 0 || items_[i].firedToday) delta += 24 * 60;
    if (delta < bestDelta) {
      bestDelta = delta;
      bestH = items_[i].hour;
      bestM = items_[i].minute;
    }
  }
  if (bestDelta > 24 * 60) {
    snprintf(buf, len, "No alarm");
    return;
  }
  snprintf(buf, len, "Next %02d:%02d", bestH, bestM);
}

void AlarmClock::syncFromModem() {
  String r;
  // +CCLK: "yy/MM/dd,hh:mm:ss±zz"
  if (!g_modem.sendAt("AT+CCLK?", "OK", 3000, &r)) return;
  int q = r.indexOf('"');
  if (q < 0) return;
  int q2 = r.indexOf('"', q + 1);
  if (q2 < 0) return;
  String t = r.substring(q + 1, q2);
  // yy/MM/dd,hh:mm:ss
  int yy, mo, dd, hh, mi, ss;
  if (sscanf(t.c_str(), "%d/%d/%d,%d:%d:%d", &yy, &mo, &dd, &hh, &mi, &ss) >= 5) {
    setTime(2000 + yy, mo, dd, hh, mi, ss);
    Serial.printf("[CLK] synced %04d-%02d-%02d %02d:%02d:%02d\n", 2000 + yy, mo,
                  dd, hh, mi, ss);
  }
}

// ---- Calendar ----
bool Calendar::load() {
  count_ = 0;
  File f = Storage::fs().open("/calendar.json", FILE_READ);
  if (!f) return true;
  JsonDocument doc;
  if (deserializeJson(doc, f)) {
    f.close();
    return false;
  }
  f.close();
  for (JsonObject o : doc["events"].as<JsonArray>()) {
    if (count_ >= CAL_MAX) break;
    items_[count_].year = o["y"] | 2026;
    items_[count_].month = o["mo"] | 1;
    items_[count_].day = o["d"] | 1;
    items_[count_].hour = o["h"] | 9;
    items_[count_].minute = o["m"] | 0;
    strncpy(items_[count_].title, o["title"] | "Event",
            sizeof(items_[0].title) - 1);
    items_[count_].reminded = false;
    items_[count_].synced = o["synced"] | false;
    count_++;
  }
  return true;
}

bool Calendar::save() {
  JsonDocument doc;
  JsonArray arr = doc["events"].to<JsonArray>();
  for (int i = 0; i < count_; i++) {
    JsonObject o = arr.add<JsonObject>();
    o["y"] = items_[i].year;
    o["mo"] = items_[i].month;
    o["d"] = items_[i].day;
    o["h"] = items_[i].hour;
    o["m"] = items_[i].minute;
    o["title"] = items_[i].title;
    o["synced"] = items_[i].synced;
  }
  File f = Storage::fs().open("/calendar.json", FILE_WRITE);
  if (!f) return false;
  serializeJson(doc, f);
  f.close();
  return true;
}

const CalEvent* Calendar::at(int i) const {
  return (i >= 0 && i < count_) ? &items_[i] : nullptr;
}

bool Calendar::add(int y, int mo, int d, uint8_t h, uint8_t mi,
                   const char* title, bool synced) {
  if (count_ >= CAL_MAX) return false;
  items_[count_].year = y;
  items_[count_].month = mo;
  items_[count_].day = d;
  items_[count_].hour = h;
  items_[count_].minute = mi;
  strncpy(items_[count_].title, title ? title : "Event",
          sizeof(items_[0].title) - 1);
  items_[count_].reminded = false;
  items_[count_].synced = synced;
  count_++;
  return save();
}

bool Calendar::remove(int i) {
  if (i < 0 || i >= count_) return false;
  for (int k = i; k < count_ - 1; k++) items_[k] = items_[k + 1];
  count_--;
  return save();
}

void Calendar::clearSynced() {
  int w = 0;
  for (int i = 0; i < count_; i++) {
    if (!items_[i].synced) items_[w++] = items_[i];
  }
  count_ = w;
  save();
}

int Calendar::eventsOn(int y, int mo, int d, int* outIdx, int maxOut) const {
  int n = 0;
  for (int i = 0; i < count_ && n < maxOut; i++) {
    if (items_[i].year == y && items_[i].month == mo && items_[i].day == d)
      outIdx[n++] = i;
  }
  return n;
}

void Calendar::tickReminders() {
  if (!g_clock.timeValid()) return;
  int y, mo, d, h, mi, s;
  g_clock.getDate(y, mo, d);
  g_clock.getTime(h, mi, s);
  for (int i = 0; i < count_; i++) {
    if (items_[i].reminded) continue;
    if (items_[i].year == y && items_[i].month == mo && items_[i].day == d &&
        items_[i].hour == h && items_[i].minute == mi && s < 2) {
      items_[i].reminded = true;
      g_notifs.push(NOTIF_INFO, "Calendar", items_[i].title);
      phonePlayNotify(660, 400);
    }
  }
}
