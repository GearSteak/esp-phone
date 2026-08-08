#include "storage.h"
#include "Config.h"
#include <LittleFS.h>
#include <SD.h>
#include <SPI.h>
#include <SD_MMC.h>
#include <ArduinoJson.h>

namespace Storage {

static bool ready_ = false;
static bool sdReady_ = false;
static const char* backend_ = "none";

bool sdReady() { return sdReady_; }
const char* backendName() { return backend_; }

fs::FS& fs() {
#if USE_ONBOARD_SD_MMC
  if (sdReady_) return SD_MMC;
#endif
#if USE_SD_SPI
  if (sdReady_) return SD;
#endif
  return LittleFS;
}

bool begin() {
  ready_ = false;
  sdReady_ = false;
  backend_ = "none";

#if USE_ONBOARD_SD_MMC
  if (!SD_MMC.setPins(SD_MMC_CLK, SD_MMC_CMD, SD_MMC_DAT0)) {
    Serial.println("[FS] SD_MMC pin set failed");
  } else if (SD_MMC.begin("/sdcard", true)) {
    ready_ = true;
    sdReady_ = true;
    backend_ = "SD_MMC";
    uint64_t mb = SD_MMC.cardSize() / (1024ULL * 1024ULL);
    Serial.printf("[FS] Onboard TF mounted (%llu MB)\n",
                  (unsigned long long)mb);
    seedTemplates();
    return true;
  } else {
    Serial.println("[FS] Onboard TF mount failed — insert FAT32 card");
  }
#endif

#if USE_SD_SPI
  SPI.begin(SD_SPI_SCK, SD_SPI_MISO, SD_SPI_MOSI, SD_SPI_CS);
  pinMode(SD_SPI_CS, OUTPUT);
  digitalWrite(SD_SPI_CS, HIGH);
  if (SD.begin(SD_SPI_CS, SPI, SD_SPI_HZ) && SD.cardType() != CARD_NONE) {
    ready_ = true;
    sdReady_ = true;
    backend_ = "SD";
    Serial.println("[FS] SPI SD mounted");
    seedTemplates();
    return true;
  }
  Serial.println("[FS] SPI SD mount failed");
#endif

  if (!LittleFS.begin(true)) {
    Serial.println("[FS] LittleFS mount failed");
    return false;
  }
  ready_ = true;
  backend_ = "LittleFS";
  Serial.println("[FS] LittleFS mounted (SD unavailable)");
  seedTemplates();
  return true;
}

static void ensureDir(const char* path) {
  if (!fs().exists(path)) fs().mkdir(path);
}

static void writeIfMissing(const char* path, const char* content) {
  if (fs().exists(path)) return;
  File f = fs().open(path, FILE_WRITE);
  if (!f) return;
  f.print(content);
  f.close();
  Serial.printf("[FS] seeded %s\n", path);
}

void seedTemplates() {
  if (!ready_) return;
  ensureDir("/music");
  ensureDir("/photos");
  ensureDir("/voicenotes");
  ensureDir("/books");
  ensureDir("/audiobooks");
  ensureDir("/videos");
  writeIfMissing("/wifi_sta.txt", "YourWifiSSID\nYourWifiPassword\n");
  writeIfMissing("/email.txt",
                 "you@gmail.com\nxxxx-xxxx-xxxx-xxxx\nimap.gmail.com\n");
  writeIfMissing(
      "/google_ics.url",
      "https://calendar.google.com/calendar/ical/REPLACE/private-REPLACE/"
      "basic.ics\n");
}

bool saveContactsJson(const char* json) {
  if (!ready_) return false;
  File f = fs().open("/contacts.json", FILE_WRITE);
  if (!f) return false;
  f.print(json);
  f.close();
  return true;
}

bool loadContactsJson(char* buf, size_t len) {
  if (!ready_ || !buf || len == 0) return false;
  File f = fs().open("/contacts.json", FILE_READ);
  if (!f) {
    buf[0] = 0;
    return false;
  }
  size_t n = f.readBytes(buf, len - 1);
  buf[n] = 0;
  f.close();
  return true;
}

bool appendSmsLog(const char* dir, const char* number, const char* text) {
  if (!ready_) return false;
  File f = fs().open("/sms_log.txt", FILE_APPEND);
  if (!f) f = fs().open("/sms_log.txt", FILE_WRITE);
  if (!f) return false;
  f.printf("%lu|%s|%s|%s\n", (unsigned long)millis(), dir, number, text);
  f.close();
  return true;
}

bool loadHighScores(int out[4]) {
  if (!ready_) return false;
  File f = fs().open("/hiscores.json", FILE_READ);
  if (!f) return false;
  JsonDocument doc;
  if (deserializeJson(doc, f)) {
    f.close();
    return false;
  }
  f.close();
  out[0] = doc["none"] | 0;
  out[1] = doc["snake"] | 0;
  out[2] = doc["pong"] | 0;
  out[3] = doc["tetris"] | 0;
  return true;
}

bool saveHighScores(const int scores[4]) {
  if (!ready_) return false;
  JsonDocument doc;
  doc["none"] = scores[0];
  doc["snake"] = scores[1];
  doc["pong"] = scores[2];
  doc["tetris"] = scores[3];
  File f = fs().open("/hiscores.json", FILE_WRITE);
  if (!f) return false;
  serializeJson(doc, f);
  f.close();
  return true;
}

}  // namespace Storage
