#include "modem.h"
#include <ctype.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

Modem g_modem;

bool Modem::begin() {
  serial_.begin(MODEM_UART_BAUD, SERIAL_8N1, MODEM_UART_RX, MODEM_UART_TX);
  delay(200);
  drain();

  if (MODEM_PWRKEY_PIN >= 0) {
    pinMode(MODEM_PWRKEY_PIN, OUTPUT);
    digitalWrite(MODEM_PWRKEY_PIN, LOW);
    delay(100);
    digitalWrite(MODEM_PWRKEY_PIN, HIGH);
    delay(1200);
    digitalWrite(MODEM_PWRKEY_PIN, LOW);
    delay(MODEM_BOOT_DELAY_MS);
  }

  // Disable echo for cleaner parsing
  sendAt("ATE0");
  return sendAt("AT");
}

bool Modem::waitReady(uint32_t timeoutMs) {
  uint32_t start = millis();
  while (millis() - start < timeoutMs) {
    if (sendAt("AT", "OK", 1000)) return true;
    delay(500);
  }
  return false;
}

String Modem::readResponse(uint32_t timeoutMs) {
  String out;
  uint32_t start = millis();
  while (millis() - start < timeoutMs) {
    while (serial_.available()) {
      char c = (char)serial_.read();
      out += c;
    }
    if (out.indexOf("OK") >= 0 || out.indexOf("ERROR") >= 0 ||
        out.indexOf("> ") >= 0) {
      break;
    }
    delay(5);
  }
  return out;
}

void Modem::drain() {
  while (serial_.available()) serial_.read();
}

bool Modem::waitFor(const char* token, uint32_t timeoutMs, String* collected) {
  String buf;
  uint32_t start = millis();
  while (millis() - start < timeoutMs) {
    while (serial_.available()) {
      char c = (char)serial_.read();
      buf += c;
    }
    if (buf.indexOf(token) >= 0) {
      if (collected) *collected = buf;
      return true;
    }
    if (buf.indexOf("ERROR") >= 0) {
      if (collected) *collected = buf;
      return false;
    }
    delay(5);
  }
  if (collected) *collected = buf;
  return false;
}

bool Modem::sendAt(const char* cmd, const char* expect, uint32_t timeoutMs,
                   String* resp) {
  drain();
  serial_.print(cmd);
  serial_.print("\r\n");
  String r = readResponse(timeoutMs);
  if (resp) *resp = r;
  return r.indexOf(expect) >= 0;
}

bool Modem::checkSim() {
  String r;
  if (!sendAt("AT+CPIN?", "OK", MODEM_AT_TIMEOUT_MS, &r)) {
    simReady_ = false;
    return false;
  }
  simReady_ = r.indexOf("READY") >= 0;
  return simReady_;
}

bool Modem::checkRegistration() {
  String r;
  // Prefer CEREG for LTE
  if (sendAt("AT+CEREG?", "OK", MODEM_AT_TIMEOUT_MS, &r)) {
    // +CEREG: n,stat  stat 1=home 5=roaming
    int comma = r.indexOf(',');
    if (comma > 0) {
      int stat = r.substring(comma + 1).toInt();
      registered_ = (stat == 1 || stat == 5);
    }
  }
  sendAt("AT+COPS?", "OK", MODEM_AT_TIMEOUT_MS, &r);
  if (!registered_) {
    if (sendAt("AT+CREG?", "OK", MODEM_AT_TIMEOUT_MS, &r)) {
      int comma = r.indexOf(',');
      if (comma > 0) {
        int stat = r.substring(comma + 1).toInt();
        registered_ = (stat == 1 || stat == 5);
      }
    }
  }
  return registered_;
}

int Modem::parseCsq(const String& s) {
  int idx = s.indexOf("+CSQ:");
  if (idx < 0) return 99;
  return s.substring(idx + 5).toInt();
}

bool Modem::checkSignal(int& csqOut) {
  String r;
  if (!sendAt("AT+CSQ", "OK", MODEM_AT_TIMEOUT_MS, &r)) return false;
  csq_ = parseCsq(r);
  csqOut = csq_;
  return true;
}

bool Modem::configureApn(const char* apn) {
  char cmd[96];
  snprintf(cmd, sizeof(cmd), "AT+CGDCONT=1,\"IP\",\"%s\"", apn);
  return sendAt(cmd);
}

bool Modem::activatePdp() {
  if (!sendAt("AT+CGACT=1,1", "OK", 30000)) {
    // already active is fine on some firmwares
    String r;
    sendAt("AT+CGACT?", "OK", 3000, &r);
  }
  pdpActive_ = true;
  return true;
}

bool Modem::parseIp(const String& s, char* out, size_t len) {
  int idx = s.indexOf("+CGPADDR:");
  if (idx < 0) idx = s.indexOf("+CGPADDR");
  if (idx < 0) return false;
  int quote = s.indexOf('"', idx);
  if (quote < 0) {
    // +CGPADDR: 1,10.x.x.x
    int comma = s.indexOf(',', idx);
    if (comma < 0) return false;
    int end = comma + 1;
    while (end < (int)s.length() &&
           (isdigit(s[end]) || s[end] == '.'))
      end++;
    String ip = s.substring(comma + 1, end);
    ip.trim();
    strncpy(out, ip.c_str(), len - 1);
    out[len - 1] = 0;
    return ip.length() > 0;
  }
  int quote2 = s.indexOf('"', quote + 1);
  if (quote2 < 0) return false;
  String ip = s.substring(quote + 1, quote2);
  strncpy(out, ip.c_str(), len - 1);
  out[len - 1] = 0;
  return true;
}

bool Modem::getIpAddress(char* buf, size_t len) {
  String r;
  if (!sendAt("AT+CGPADDR=1", "OK", MODEM_AT_TIMEOUT_MS, &r)) return false;
  if (!parseIp(r, buf, len)) return false;
  strncpy(ip_, buf, sizeof(ip_) - 1);
  return true;
}

bool Modem::ensureDataSession() {
  if (!simReady_ && !checkSim()) return false;
  if (!registered_ && !checkRegistration()) return false;
  if (!configureApn()) return false;
  if (!activatePdp()) return false;
  char ip[32];
  if (!getIpAddress(ip, sizeof(ip))) return false;
  return netOpen();
}

bool Modem::smsInit() {
  // Text mode, SMS over CS (or IMS if operator routes it)
  if (!sendAt("AT+CMGF=1")) return false;
  sendAt("AT+CSCS=\"GSM\"");
  sendAt("AT+CNMI=2,1,0,0,0");  // URC for new SMS
  return true;
}

bool Modem::sendSms(const char* number, const char* text) {
  drain();
  serial_.print("AT+CMGS=\"");
  serial_.print(number);
  serial_.print("\"\r");
  if (!waitFor(">", 5000)) return false;
  serial_.print(text);
  serial_.write(0x1A);
  String r;
  return waitFor("OK", 30000, &r);
}

int Modem::listSms(SmsMessage* out, int maxCount) {
  String r;
  if (!sendAt("AT+CMGL=\"ALL\"", "OK", 15000, &r)) return 0;
  int count = 0;
  int pos = 0;
  while (count < maxCount) {
    int hdr = r.indexOf("+CMGL:", pos);
    if (hdr < 0) break;
    // +CMGL: idx,"STAT","NUM",,"TS"
    int idxEnd = r.indexOf(',', hdr);
    int index = r.substring(hdr + 6, idxEnd).toInt();
    int q1 = r.indexOf('"', idxEnd);
    int q2 = r.indexOf('"', q1 + 1);
    int q3 = r.indexOf('"', q2 + 1);
    int q4 = r.indexOf('"', q3 + 1);
    String body;
    int lineEnd = r.indexOf('\n', q4 > 0 ? q4 : idxEnd);
    int next = r.indexOf("+CMGL:", lineEnd);
    int okAt = r.indexOf("\nOK", lineEnd);
    int endBody = next >= 0 ? next : (okAt >= 0 ? okAt : r.length());
    body = r.substring(lineEnd + 1, endBody);
    body.trim();

    out[count].index = index;
    strncpy(out[count].status,
            (q1 >= 0 && q2 > q1) ? r.substring(q1 + 1, q2).c_str() : "",
            sizeof(out[count].status) - 1);
    strncpy(out[count].number,
            (q3 >= 0 && q4 > q3) ? r.substring(q3 + 1, q4).c_str() : "",
            sizeof(out[count].number) - 1);
    out[count].timestamp[0] = 0;
    strncpy(out[count].text, body.c_str(), sizeof(out[count].text) - 1);
    count++;
    pos = endBody;
  }
  return count;
}

bool Modem::readSms(int index, SmsMessage& out) {
  char cmd[32];
  snprintf(cmd, sizeof(cmd), "AT+CMGR=%d", index);
  String r;
  if (!sendAt(cmd, "OK", 10000, &r)) return false;
  out.index = index;
  int q1 = r.indexOf('"');
  int q2 = r.indexOf('"', q1 + 1);
  int q3 = r.indexOf('"', q2 + 1);
  int q4 = r.indexOf('"', q3 + 1);
  strncpy(out.status,
          (q1 >= 0 && q2 > q1) ? r.substring(q1 + 1, q2).c_str() : "",
          sizeof(out.status) - 1);
  strncpy(out.number,
          (q3 >= 0 && q4 > q3) ? r.substring(q3 + 1, q4).c_str() : "",
          sizeof(out.number) - 1);
  int nl = r.indexOf('\n', q4 > 0 ? q4 : 0);
  int okAt = r.lastIndexOf("OK");
  String body = r.substring(nl + 1, okAt >= 0 ? okAt : r.length());
  body.trim();
  strncpy(out.text, body.c_str(), sizeof(out.text) - 1);
  return true;
}

bool Modem::deleteSms(int index) {
  char cmd[32];
  snprintf(cmd, sizeof(cmd), "AT+CMGD=%d", index);
  return sendAt(cmd);
}

bool Modem::queryBattery(int& percentOut, int& mvOut, int& chargeStatusOut) {
  // +CBC: <bcs>,<bcl>,<voltage>  bcs: 0=not charging,1=charging,2=charged
  String r;
  if (!sendAt("AT+CBC", "OK", 3000, &r)) return false;
  int a = r.indexOf("+CBC:");
  if (a < 0) return false;
  int bcs = 0, bcl = 0, mv = 0;
  if (sscanf(r.c_str() + a, "+CBC: %d,%d,%d", &bcs, &bcl, &mv) < 2) return false;
  chargeStatusOut = bcs;
  percentOut = constrain(bcl, 0, 100);
  mvOut = mv;
  return true;
}

bool Modem::setAirplaneMode(bool on) {
  // CFUN=0 minimum functionality (RF off); CFUN=1 full
  if (on) {
    if (!sendAt("AT+CFUN=0", "OK", 15000)) return false;
    registered_ = false;
    pdpActive_ = false;
    netOpen_ = false;
    return true;
  }
  if (!sendAt("AT+CFUN=1", "OK", 15000)) return false;
  return true;
}

bool Modem::httpGet(const char* url, char* out, size_t outLen, int* statusOut) {
  if (!url || !out || outLen < 8) return false;
  out[0] = 0;
  if (!ensureDataSession()) return false;

  sendAt("AT+HTTPTERM", "OK", 3000);  // ignore fail
  if (!sendAt("AT+HTTPINIT", "OK", 5000)) return false;

  bool ssl = (strncmp(url, "https://", 8) == 0);
  if (ssl) sendAt("AT+HTTPSSL=1", "OK", 3000);

  char para[400];
  snprintf(para, sizeof(para), "AT+HTTPPARA=\"URL\",\"%s\"", url);
  if (!sendAt(para, "OK", 5000)) {
    sendAt("AT+HTTPTERM", "OK", 3000);
    return false;
  }
  sendAt("AT+HTTPPARA=\"CONTENT\",\"application/json\"", "OK", 3000);

  String r;
  if (!sendAt("AT+HTTPACTION=0", "OK", 5000, &r)) {
    // some firmwares only OK after URC
  }
  // Wait for +HTTPACTION: 0,status,len
  uint32_t start = millis();
  int httpStatus = 0;
  int dataLen = 0;
  bool got = false;
  while (millis() - start < 45000) {
    pollUrc();
    String chunk = readResponse(500);
    r += chunk;
    int p = r.indexOf("+HTTPACTION:");
    if (p >= 0) {
      if (sscanf(r.c_str() + p, "+HTTPACTION: %*d,%d,%d", &httpStatus, &dataLen) >=
          2) {
        got = true;
        break;
      }
    }
    vTaskDelay(pdMS_TO_TICKS(100));
  }
  if (statusOut) *statusOut = httpStatus;
  if (!got || httpStatus < 200 || httpStatus >= 300) {
    sendAt("AT+HTTPTERM", "OK", 3000);
    return false;
  }

  char cmd[48];
  int toRead = dataLen;
  if (toRead > (int)outLen - 1) toRead = (int)outLen - 1;
  snprintf(cmd, sizeof(cmd), "AT+HTTPREAD=0,%d", toRead);
  String body;
  if (!sendAt(cmd, "OK", 15000, &body)) {
    sendAt("AT+HTTPTERM", "OK", 3000);
    return false;
  }
  // Body after +HTTPREAD: ...
  int hdr = body.indexOf("+HTTPREAD:");
  int nl = body.indexOf('\n', hdr >= 0 ? hdr : 0);
  int okAt = body.lastIndexOf("\nOK");
  String payload =
      body.substring(nl >= 0 ? nl + 1 : 0, okAt >= 0 ? okAt : body.length());
  payload.trim();
  strncpy(out, payload.c_str(), outLen - 1);
  out[outLen - 1] = 0;
  sendAt("AT+HTTPTERM", "OK", 3000);
  return out[0] != 0;
}

bool Modem::netOpen() {
  if (netOpen_) return true;
  String r;
  sendAt("AT+NETOPEN?", "OK", 3000, &r);
  if (r.indexOf("+NETOPEN: 1") >= 0 || r.indexOf(",1") >= 0) {
    netOpen_ = true;
    return true;
  }
  // Some firmware returns +NETOPEN: 0 on success asynchronously
  if (!sendAt("AT+NETOPEN", "OK", 60000, &r)) {
    if (r.indexOf("+NETOPEN: 0") < 0 && r.indexOf("already") < 0) return false;
  }
  netOpen_ = true;
  return true;
}

bool Modem::netClose() {
  sendAt("AT+NETCLOSE", "OK", 10000);
  netOpen_ = false;
  return true;
}

bool Modem::udpOpen(int linkId, const char* host, uint16_t port,
                    uint16_t localPort) {
  if (!netOpen()) return false;
  char cmd[128];
  // AT+CIPOPEN=<link>,"UDP",<host>,<remotePort>,<localPort>
  snprintf(cmd, sizeof(cmd), "AT+CIPOPEN=%d,\"UDP\",\"%s\",%u,%u", linkId, host,
           (unsigned)port, (unsigned)localPort);
  String r;
  if (!sendAt(cmd, "OK", 15000, &r)) {
    // already open?
    if (r.indexOf("+CIPOPEN:") < 0 && r.indexOf("ERROR") >= 0) return false;
  }
  return true;
}

bool Modem::udpClose(int linkId) {
  char cmd[32];
  snprintf(cmd, sizeof(cmd), "AT+CIPCLOSE=%d", linkId);
  return sendAt(cmd, "OK", 5000);
}

bool Modem::udpSend(int linkId, const uint8_t* data, size_t len) {
  char cmd[48];
  snprintf(cmd, sizeof(cmd), "AT+CIPSEND=%d,%u", linkId, (unsigned)len);
  drain();
  serial_.print(cmd);
  serial_.print("\r\n");
  if (!waitFor(">", 3000)) return false;
  serial_.write(data, len);
  return waitFor("OK", 5000);
}

int Modem::udpAvailable(int linkId) {
  (void)linkId;
  pollUrc();
  size_t used = (rxHead_ >= rxTail_) ? (rxHead_ - rxTail_)
                                     : (RX_BUF - rxTail_ + rxHead_);
  return (int)used;
}

int Modem::udpRead(int linkId, uint8_t* buf, size_t maxLen) {
  (void)linkId;
  pollUrc();
  size_t n = 0;
  while (n < maxLen && rxTail_ != rxHead_) {
    buf[n++] = rxBuf_[rxTail_];
    rxTail_ = (rxTail_ + 1) % RX_BUF;
  }
  return (int)n;
}

void Modem::pollUrc() {
  // Parse +IPD / +RECEIVE style UDP payloads into ring buffer.
  // SIM7670 variants differ; support:
  //   +IPD<len>:<data>
  //   +RECEIVE,<link>,<len>\r\n<data>
  while (serial_.available()) {
    String line;
    // Prefer line-oriented URC detection, then binary payload
    char peekBuf[8];
    int got = 0;
    while (serial_.available() && got < 7) {
      peekBuf[got++] = (char)serial_.peek();
      // don't consume yet for multi-byte match — read into line
      break;
    }
    char c = (char)serial_.read();
    if (c == '+') {
      String hdr = "+";
      uint32_t t0 = millis();
      while (millis() - t0 < 50) {
        while (serial_.available()) {
          char ch = (char)serial_.read();
          hdr += ch;
          if (ch == ':' || ch == '\n') goto hdr_done;
        }
        delay(1);
      }
    hdr_done:
      int len = 0;
      int link = 0;
      if (hdr.startsWith("+IPD")) {
        // +IPD123: or +IPD,0,123:
        int p = 4;
        while (p < (int)hdr.length() && !isdigit(hdr[p])) p++;
        len = hdr.substring(p).toInt();
      } else if (hdr.startsWith("+RECEIVE")) {
        // +RECEIVE,<link>,<len>
        int c1 = hdr.indexOf(',');
        int c2 = hdr.indexOf(',', c1 + 1);
        if (c1 > 0 && c2 > c1) {
          link = hdr.substring(c1 + 1, c2).toInt();
          len = hdr.substring(c2 + 1).toInt();
        }
        (void)link;
      } else {
        continue;
      }
      if (len <= 0 || len > 1500) continue;
      // skip until payload start
      if (hdr.indexOf(':') < 0) {
        // consume CR LF before payload
        uint32_t t1 = millis();
        while (millis() - t1 < 100 && serial_.available() < len) delay(1);
      }
      for (int i = 0; i < len; i++) {
        uint32_t t2 = millis();
        while (!serial_.available()) {
          if (millis() - t2 > 200) break;
          delay(1);
        }
        if (!serial_.available()) break;
        uint8_t b = (uint8_t)serial_.read();
        size_t next = (rxHead_ + 1) % RX_BUF;
        if (next != rxTail_) {
          rxBuf_[rxHead_] = b;
          rxHead_ = next;
        }
      }
    }
    // discard other chars (URCs like +CMTI etc. can be extended later)
  }
}
