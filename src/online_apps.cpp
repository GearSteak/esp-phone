#include "online_apps.h"
#include "phone_data.h"
#include "modem.h"
#include "storage.h"
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <esp_heap_caps.h>
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

EmailApp g_email;
TextBrowser g_browser;

static void trimLine(char* s) {
  size_t n = strlen(s);
  while (n && (s[n - 1] == '\r' || s[n - 1] == '\n' || s[n - 1] == ' '))
    s[--n] = 0;
  char* p = s;
  while (*p == ' ' || *p == '\t') p++;
  if (p != s) memmove(s, p, strlen(p) + 1);
}

static bool readFirstLine(const char* path, char* out, size_t outLen) {
  File f = Storage::fs().open(path, FILE_READ);
  if (!f) return false;
  size_t n = f.readBytesUntil('\n', out, outLen - 1);
  out[n] = 0;
  f.close();
  trimLine(out);
  return out[0] != 0;
}

static bool loadIcsUrl(char* out, size_t outLen) {
  if (readFirstLine("/google_ics.url", out, outLen)) return true;
  if (GOOGLE_CAL_ICS_URL[0]) {
    strncpy(out, GOOGLE_CAL_ICS_URL, outLen - 1);
    out[outLen - 1] = 0;
    return true;
  }
  out[0] = 0;
  return false;
}

static bool loadWifiSta(char* ssid, size_t ssidLen, char* pass, size_t passLen) {
  File f = Storage::fs().open("/wifi_sta.txt", FILE_READ);
  if (f) {
    size_t n = f.readBytesUntil('\n', ssid, ssidLen - 1);
    ssid[n] = 0;
    trimLine(ssid);
    n = f.readBytesUntil('\n', pass, passLen - 1);
    pass[n] = 0;
    trimLine(pass);
    f.close();
    return ssid[0] != 0;
  }
  strncpy(ssid, WIFI_STA_SSID, ssidLen - 1);
  ssid[ssidLen - 1] = 0;
  strncpy(pass, WIFI_STA_PASS, passLen - 1);
  pass[passLen - 1] = 0;
  return ssid[0] != 0;
}

static bool loadImapCreds(char* user, size_t userLen, char* pass, size_t passLen,
                          char* host, size_t hostLen) {
  File f = Storage::fs().open("/email.txt", FILE_READ);
  if (f) {
    size_t n = f.readBytesUntil('\n', user, userLen - 1);
    user[n] = 0;
    trimLine(user);
    n = f.readBytesUntil('\n', pass, passLen - 1);
    pass[n] = 0;
    trimLine(pass);
    if (f.available()) {
      n = f.readBytesUntil('\n', host, hostLen - 1);
      host[n] = 0;
      trimLine(host);
    }
    f.close();
  } else {
    strncpy(user, IMAP_USER, userLen - 1);
    user[userLen - 1] = 0;
    strncpy(pass, IMAP_PASS, passLen - 1);
    pass[passLen - 1] = 0;
  }
  if (!host[0]) {
    strncpy(host, IMAP_HOST, hostLen - 1);
    host[hostLen - 1] = 0;
  }
  return user[0] != 0 && pass[0] != 0;
}

const char* calendarIcsUrl() {
  static char url[200];
  loadIcsUrl(url, sizeof(url));
  return url;
}

static void icsUnescape(char* s) {
  // \\ , \; \, \n
  char* r = s;
  char* w = s;
  while (*r) {
    if (*r == '\\' && r[1]) {
      r++;
      if (*r == 'n' || *r == 'N') *w++ = '\n';
      else *w++ = *r;
      r++;
    } else {
      *w++ = *r++;
    }
  }
  *w = 0;
}

static bool parseDtStart(const char* v, int& y, int& mo, int& d, int& h,
                         int& mi) {
  // Find YYYYMMDD[Thhmmss]
  const char* p = v;
  while (*p && !isdigit((unsigned char)*p)) p++;
  if (strlen(p) < 8) return false;
  char buf[16];
  memcpy(buf, p, 8);
  buf[8] = 0;
  int date = atoi(buf);
  y = date / 10000;
  mo = (date / 100) % 100;
  d = date % 100;
  h = 9;
  mi = 0;
  if (p[8] == 'T' && strlen(p) >= 13) {
    memcpy(buf, p + 9, 2);
    buf[2] = 0;
    h = atoi(buf);
    memcpy(buf, p + 11, 2);
    buf[2] = 0;
    mi = atoi(buf);
  }
  return y >= 2000 && y < 2100 && mo >= 1 && mo <= 12 && d >= 1 && d <= 31;
}

static int importIcsBody(const char* ics) {
  g_calendar.clearSynced();
  int imported = 0;
  const char* p = ics;
  bool inEvent = false;
  char summary[80] = {0};
  char dtstart[64] = {0};

  while (*p) {
    // Read one logical line (handle unfolding)
    char line[240];
    size_t li = 0;
    while (*p && *p != '\n' && li + 1 < sizeof(line)) {
      if (*p != '\r') line[li++] = *p;
      p++;
    }
    if (*p == '\n') p++;
    while (*p == ' ' || *p == '\t') {
      while (*p && *p != '\n' && li + 1 < sizeof(line)) {
        if (*p != '\r') line[li++] = *p;
        p++;
      }
      if (*p == '\n') p++;
    }
    line[li] = 0;

    if (!strcmp(line, "BEGIN:VEVENT")) {
      inEvent = true;
      summary[0] = dtstart[0] = 0;
      continue;
    }
    if (!strcmp(line, "END:VEVENT")) {
      if (inEvent && summary[0] && dtstart[0]) {
        int y, mo, d, h, mi;
        if (parseDtStart(dtstart, y, mo, d, h, mi)) {
          icsUnescape(summary);
          char title[48];
          snprintf(title, sizeof(title), "%.46s", summary);
          if (g_calendar.add(y, mo, d, (uint8_t)h, (uint8_t)mi, title, true))
            imported++;
        }
      }
      inEvent = false;
      continue;
    }
    if (!inEvent) continue;
    if (!strncmp(line, "SUMMARY", 7)) {
      const char* colon = strchr(line, ':');
      if (colon) strncpy(summary, colon + 1, sizeof(summary) - 1);
    } else if (!strncmp(line, "DTSTART", 7)) {
      const char* colon = strchr(line, ':');
      if (colon) strncpy(dtstart, colon + 1, sizeof(dtstart) - 1);
    }
  }
  return imported;
}

int calendarSyncGoogleIcs() {
  char icsUrl[200];
  if (!loadIcsUrl(icsUrl, sizeof(icsUrl))) {
    Serial.println("[CAL] No ICS URL — set GOOGLE_CAL_ICS_URL or /google_ics.url");
    return -1;
  }
  const size_t CAP = 24 * 1024;
  char* body = (char*)heap_caps_malloc(CAP, MALLOC_CAP_SPIRAM);
  if (!body) body = (char*)malloc(CAP);
  if (!body) return -1;
  body[0] = 0;
  int status = 0;
  bool ok = g_modem.httpGet(icsUrl, body, CAP, &status);
  int n = -1;
  if (ok && body[0]) {
    n = importIcsBody(body);
    Serial.printf("[CAL] ICS HTTP %d imported %d events\n", status, n);
  } else {
    Serial.printf("[CAL] ICS fetch failed status=%d\n", status);
  }
  free(body);
  return n;
}

// ---- Email (IMAP over WiFi STA) ----
bool EmailApp::connectWifiSta() {
  status_[0] = 0;
  char ssid[33] = {0};
  char pass[65] = {0};
  if (!loadWifiSta(ssid, sizeof(ssid), pass, sizeof(pass))) {
    strncpy(status_, "No WiFi SSID", sizeof(status_) - 1);
    wifiOk_ = false;
    return false;
  }
  wifi_mode_t mode = WiFi.getMode();
  if (mode == WIFI_AP || mode == WIFI_AP_STA)
    WiFi.mode(WIFI_AP_STA);
  else
    WiFi.mode(WIFI_STA);

  WiFi.begin(ssid, pass);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(250);
  }
  wifiOk_ = (WiFi.status() == WL_CONNECTED);
  if (wifiOk_)
    snprintf(status_, sizeof(status_), "WiFi %s", WiFi.localIP().toString().c_str());
  else
    strncpy(status_, "WiFi fail", sizeof(status_) - 1);
  return wifiOk_;
}

void EmailApp::disconnectWifiSta() {
  // Leave SoftAP alone
  if (WiFi.getMode() == WIFI_AP_STA) {
    WiFi.disconnect(false);
  } else {
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
  }
  wifiOk_ = false;
}

const EmailItem* EmailApp::at(int i) const {
  return (i >= 0 && i < count_) ? &items_[i] : nullptr;
}

static bool imapWaitTagged(WiFiClientSecure& c, const char* tag, char* out,
                           size_t outLen, uint32_t timeoutMs) {
  if (out && outLen) out[0] = 0;
  uint32_t start = millis();
  size_t oi = 0;
  char line[256];
  size_t li = 0;
  while (millis() - start < timeoutMs) {
    while (c.available()) {
      char ch = (char)c.read();
      if (out && oi + 1 < outLen) out[oi++] = ch;
      if (ch == '\n') {
        line[li] = 0;
        if (!strncmp(line, tag, strlen(tag))) {
          if (out) out[oi] = 0;
          return strstr(line, "OK") != nullptr;
        }
        li = 0;
      } else if (ch != '\r' && li + 1 < sizeof(line)) {
        line[li++] = ch;
      }
    }
    delay(5);
  }
  if (out) out[oi] = 0;
  return false;
}

bool EmailApp::refreshInbox() {
  count_ = 0;
  body_[0] = 0;
  char user[64] = {0}, pass[64] = {0}, host[48] = {0};
  if (!loadImapCreds(user, sizeof(user), pass, sizeof(pass), host, sizeof(host))) {
    strncpy(status_, "Set /email.txt", sizeof(status_) - 1);
    return false;
  }
  if (!wifiOk_ && !connectWifiSta()) return false;

  WiFiClientSecure client;
  client.setInsecure();
  client.setTimeout(20);
  if (!client.connect(host, IMAP_PORT)) {
    strncpy(status_, "IMAP connect fail", sizeof(status_) - 1);
    return false;
  }

  char resp[2048];
  uint32_t t0 = millis();
  while (!client.available() && millis() - t0 < 5000) delay(10);
  while (client.available()) client.read();

  char cmd[160];
  snprintf(cmd, sizeof(cmd), "a01 LOGIN \"%s\" \"%s\"\r\n", user, pass);
  client.print(cmd);
  if (!imapWaitTagged(client, "a01", resp, sizeof(resp), 15000)) {
    strncpy(status_, "LOGIN fail", sizeof(status_) - 1);
    client.stop();
    return false;
  }

  client.print("a02 SELECT INBOX\r\n");
  if (!imapWaitTagged(client, "a02", resp, sizeof(resp), 10000)) {
    strncpy(status_, "SELECT fail", sizeof(status_) - 1);
    client.stop();
    return false;
  }

  int exists = 0;
  const char* ex = strstr(resp, "EXISTS");
  if (ex) {
    const char* q = ex;
    while (q > resp && (isdigit((unsigned char)q[-1]) || q[-1] == ' ')) q--;
    exists = atoi(q);
  }
  if (exists <= 0) {
    strncpy(status_, "Inbox empty", sizeof(status_) - 1);
    client.print("a99 LOGOUT\r\n");
    client.stop();
    return true;
  }

  int from = exists - EMAIL_LIST_MAX + 1;
  if (from < 1) from = 1;
  snprintf(cmd, sizeof(cmd),
           "a03 FETCH %d:%d (BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])\r\n",
           from, exists);
  client.print(cmd);
  if (!imapWaitTagged(client, "a03", resp, sizeof(resp), 20000)) {
    strncpy(status_, "FETCH fail", sizeof(status_) - 1);
    client.stop();
    return false;
  }

  const char* p = resp;
  while (count_ < EMAIL_LIST_MAX && (p = strstr(p, "FETCH")) != nullptr) {
    const char* nump = p;
    while (nump > resp && nump[-1] != '*') nump--;
    int msgNum = atoi(nump);
    EmailItem& it = items_[count_];
    memset(&it, 0, sizeof(it));
    it.msgNum = msgNum > 0 ? msgNum : (from + count_);

    const char* blockEnd = strstr(p, "\r\n)");
    if (!blockEnd) blockEnd = p + strlen(p);
    auto grab = [&](const char* key, char* dest, size_t destLen) {
      const char* f = strstr(p, key);
      if (!f || f > blockEnd) return;
      f += strlen(key);
      while (*f == ' ') f++;
      size_t i = 0;
      while (f[i] && f[i] != '\r' && f[i] != '\n' && i + 1 < destLen) {
        dest[i] = f[i];
        i++;
      }
      dest[i] = 0;
    };
    grab("From:", it.from, sizeof(it.from));
    grab("Subject:", it.subject, sizeof(it.subject));
    grab("Date:", it.date, sizeof(it.date));
    if (!it.subject[0]) strncpy(it.subject, "(no subject)", sizeof(it.subject) - 1);
    count_++;
    p = blockEnd + 1;
  }

  for (int i = 0; i < count_ / 2; i++) {
    EmailItem tmp = items_[i];
    items_[i] = items_[count_ - 1 - i];
    items_[count_ - 1 - i] = tmp;
  }

  snprintf(status_, sizeof(status_), "%d msgs", count_);
  client.print("a99 LOGOUT\r\n");
  client.stop();
  return true;
}

bool EmailApp::openMessage(int listIndex) {
  body_[0] = 0;
  if (listIndex < 0 || listIndex >= count_) return false;
  char user[64] = {0}, pass[64] = {0}, host[48] = {0};
  if (!loadImapCreds(user, sizeof(user), pass, sizeof(pass), host, sizeof(host)))
    return false;
  if (!wifiOk_ && !connectWifiSta()) return false;

  WiFiClientSecure client;
  client.setInsecure();
  client.setTimeout(20);
  if (!client.connect(host, IMAP_PORT)) {
    strncpy(status_, "IMAP fail", sizeof(status_) - 1);
    return false;
  }
  char resp[2800];
  uint32_t t0 = millis();
  while (!client.available() && millis() - t0 < 5000) delay(10);
  while (client.available()) client.read();

  char cmd[160];
  snprintf(cmd, sizeof(cmd), "b01 LOGIN \"%s\" \"%s\"\r\n", user, pass);
  client.print(cmd);
  if (!imapWaitTagged(client, "b01", resp, sizeof(resp), 15000)) {
    client.stop();
    return false;
  }
  client.print("b02 SELECT INBOX\r\n");
  imapWaitTagged(client, "b02", resp, sizeof(resp), 10000);

  snprintf(cmd, sizeof(cmd), "b03 FETCH %d (BODY.PEEK[TEXT]<0.700>)\r\n",
           items_[listIndex].msgNum);
  client.print(cmd);
  if (!imapWaitTagged(client, "b03", resp, sizeof(resp), 20000)) {
    strncpy(status_, "body fail", sizeof(status_) - 1);
    client.stop();
    return false;
  }

  const char* brace = strchr(resp, '{');
  const char* start = brace ? strchr(brace, '\n') : nullptr;
  if (start) {
    start++;
    size_t i = 0;
    while (start[i] && i + 1 < sizeof(body_)) {
      if (start[i] == '\r' && start[i + 1] == '\n' && start[i + 2] == ')')
        break;
      body_[i] = start[i];
      i++;
    }
    body_[i] = 0;
  } else {
    strncpy(body_, "(could not parse body)", sizeof(body_) - 1);
  }
  client.print("b99 LOGOUT\r\n");
  client.stop();
  strncpy(status_, "opened", sizeof(status_) - 1);
  return true;
}

// ---- Text browser ----
void TextBrowser::htmlToText(const char* html, char* out, size_t outLen) {
  if (!html || !out || outLen < 2) return;
  size_t oi = 0;
  bool inTag = false;
  bool inScript = false;
  char tag[16];
  size_t ti = 0;
  auto emit = [&](char c) {
    if (oi + 1 < outLen) out[oi++] = c;
  };
  for (const char* p = html; *p; p++) {
    if (*p == '<') {
      inTag = true;
      ti = 0;
      tag[0] = 0;
      continue;
    }
    if (inTag) {
      if (*p == '>') {
        inTag = false;
        tag[ti] = 0;
        for (char* t = tag; *t; t++) *t = (char)tolower((unsigned char)*t);
        if (!strncmp(tag, "script", 6) || !strncmp(tag, "style", 5))
          inScript = true;
        if (!strncmp(tag, "/script", 7) || !strncmp(tag, "/style", 6))
          inScript = false;
        if (!strncmp(tag, "br", 2) || !strncmp(tag, "/p", 2) ||
            !strncmp(tag, "/div", 4) || !strncmp(tag, "/h", 2) ||
            !strncmp(tag, "p", 1) || !strncmp(tag, "li", 2))
          emit('\n');
        continue;
      }
      if (ti + 1 < sizeof(tag) && (isalnum((unsigned char)*p) || *p == '/'))
        tag[ti++] = *p;
      continue;
    }
    if (inScript) continue;
    if (*p == '&') {
      if (!strncmp(p, "&amp;", 5)) {
        emit('&');
        p += 4;
      } else if (!strncmp(p, "&lt;", 4)) {
        emit('<');
        p += 3;
      } else if (!strncmp(p, "&gt;", 4)) {
        emit('>');
        p += 3;
      } else if (!strncmp(p, "&nbsp;", 6)) {
        emit(' ');
        p += 5;
      } else
        emit(' ');
      continue;
    }
    if (*p == '\r') continue;
    if (*p == '\n' || *p == '\t') {
      emit(' ');
      continue;
    }
    emit(*p);
  }
  out[oi] = 0;
  // collapse spaces
  char* w = out;
  bool sp = false;
  for (char* r = out; *r; r++) {
    if (*r == ' ') {
      if (!sp) *w++ = ' ';
      sp = true;
    } else if (*r == '\n') {
      *w++ = '\n';
      sp = true;
    } else {
      *w++ = *r;
      sp = false;
    }
  }
  *w = 0;
}

void TextBrowser::rebuildSlice() {
  const int PAGE = 380;
  size_t off = (size_t)page_ * PAGE;
  if (off >= textLen_) {
    slice_[0] = 0;
    return;
  }
  size_t n = textLen_ - off;
  if (n > sizeof(slice_) - 1) n = sizeof(slice_) - 1;
  if (n > (size_t)PAGE) n = PAGE;
  memcpy(slice_, text_ + off, n);
  slice_[n] = 0;
}

int TextBrowser::pageCount() const {
  if (!textLen_) return 1;
  return (int)((textLen_ + 379) / 380);
}

void TextBrowser::nextPage() {
  if (page_ + 1 < pageCount()) {
    page_++;
    rebuildSlice();
  }
}
void TextBrowser::prevPage() {
  if (page_ > 0) {
    page_--;
    rebuildSlice();
  }
}

bool TextBrowser::load(const char* url) {
  if (!url || !url[0]) return false;
  strncpy(url_, url, sizeof(url_) - 1);
  page_ = 0;
  strncpy(status_, "Loading...", sizeof(status_) - 1);

  if (html_) {
    free(html_);
    html_ = nullptr;
  }
  if (text_) {
    free(text_);
    text_ = nullptr;
  }
  textLen_ = 0;

  const size_t CAP = 20 * 1024;
  html_ = (char*)heap_caps_malloc(CAP, MALLOC_CAP_SPIRAM);
  if (!html_) html_ = (char*)malloc(CAP);
  text_ = (char*)heap_caps_malloc(CAP, MALLOC_CAP_SPIRAM);
  if (!text_) text_ = (char*)malloc(CAP);
  if (!html_ || !text_) {
    strncpy(status_, "OOM", sizeof(status_) - 1);
    return false;
  }
  html_[0] = text_[0] = 0;

  int status = 0;
  if (!g_modem.httpGet(url_, html_, CAP, &status) || !html_[0]) {
    snprintf(status_, sizeof(status_), "HTTP fail %d", status);
    strncpy(text_, status_, CAP - 1);
    textLen_ = strlen(text_);
    rebuildSlice();
    return false;
  }
  htmlToText(html_, text_, CAP);
  textLen_ = strlen(text_);
  snprintf(status_, sizeof(status_), "OK %d (%u B)", status, (unsigned)textLen_);
  rebuildSlice();
  return true;
}
