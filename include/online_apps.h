#pragma once

#include "Config.h"
#include <stdint.h>

// Compact online apps: Google ICS, IMAP inbox, text browser

static constexpr int EMAIL_LIST_MAX = 6;
struct EmailItem {
  int msgNum;  // 1-based IMAP sequence
  char from[36];
  char subject[56];
  char date[24];
};

class EmailApp {
 public:
  bool connectWifiSta();
  void disconnectWifiSta();
  bool wifiReady() const { return wifiOk_; }
  bool refreshInbox();
  bool openMessage(int listIndex);
  int count() const { return count_; }
  const EmailItem* at(int i) const;
  const char* body() const { return body_; }
  const char* status() const { return status_; }

 private:
  EmailItem items_[EMAIL_LIST_MAX];
  int count_ = 0;
  char body_[480] = {0};
  char status_[48] = {0};
  bool wifiOk_ = false;
  bool imapFetch(const char* cmd, char* out, size_t outLen, uint32_t timeoutMs);
};

class TextBrowser {
 public:
  bool load(const char* url);
  void nextPage();
  void prevPage();
  const char* url() const { return url_; }
  const char* pageSlice() const { return slice_; }
  int page() const { return page_; }
  int pageCount() const;
  const char* status() const { return status_; }

 private:
  char url_[128] = {0};
  char* html_ = nullptr;   // PSRAM
  char* text_ = nullptr;   // PSRAM
  size_t textLen_ = 0;
  int page_ = 0;
  char slice_[420] = {0};
  char status_[40] = {0};
  void rebuildSlice();
  static void htmlToText(const char* html, char* out, size_t outLen);
};

// Fetch Google Calendar secret ICS URL and merge into local calendar
// Returns number of events imported, or -1 on error.
int calendarSyncGoogleIcs();
const char* calendarIcsUrl();  // from SD /google_ics.url or Config.h

extern EmailApp g_email;
extern TextBrowser g_browser;
