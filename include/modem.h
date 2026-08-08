#pragma once

#include "Config.h"
#include <Arduino.h>

struct SmsMessage {
  int index;
  char status[16];
  char number[32];
  char timestamp[32];
  char text[160];
};

class Modem {
 public:
  bool begin();
  bool waitReady(uint32_t timeoutMs = 15000);
  bool checkSim();
  bool checkRegistration();
  bool checkSignal(int& csqOut);
  bool configureApn(const char* apn = APN_NAME);
  bool activatePdp();
  bool getIpAddress(char* buf, size_t len);
  bool ensureDataSession();

  // SMS (native AT)
  bool smsInit();
  bool sendSms(const char* number, const char* text);
  int listSms(SmsMessage* out, int maxCount);
  bool readSms(int index, SmsMessage& out);
  bool deleteSms(int index);

  // Battery / radio
  bool queryBattery(int& percentOut, int& mvOut, int& chargeStatusOut);
  bool setAirplaneMode(bool on);  // AT+CFUN=0 / 1

  // HTTP GET (modem IP stack; URL may be http or https)
  bool httpGet(const char* url, char* out, size_t outLen, int* statusOut = nullptr);

  // UDP via modem IP stack (for SIP/RTP without PPP)
  bool netOpen();
  bool netClose();
  bool udpOpen(int linkId, const char* host, uint16_t port, uint16_t localPort);
  bool udpClose(int linkId);
  bool udpSend(int linkId, const uint8_t* data, size_t len);
  int udpAvailable(int linkId);
  int udpRead(int linkId, uint8_t* buf, size_t maxLen);

  bool sendAt(const char* cmd, const char* expect = "OK",
              uint32_t timeoutMs = MODEM_AT_TIMEOUT_MS, String* resp = nullptr);
  void pollUrc();
  bool isRegistered() const { return registered_; }
  bool isPdpActive() const { return pdpActive_; }
  int lastCsq() const { return csq_; }

 private:
  HardwareSerial serial_{MODEM_UART_NUM};
  bool simReady_ = false;
  bool registered_ = false;
  bool pdpActive_ = false;
  bool netOpen_ = false;
  int csq_ = 99;
  char ip_[32] = {0};

  // Simple RX ring for URC / UDP payloads
  static constexpr size_t RX_BUF = 1280;
  uint8_t rxBuf_[RX_BUF];
  size_t rxHead_ = 0;
  size_t rxTail_ = 0;

  String readResponse(uint32_t timeoutMs);
  bool waitFor(const char* token, uint32_t timeoutMs, String* collected = nullptr);
  void drain();
  int parseCsq(const String& s);
  bool parseIp(const String& s, char* out, size_t len);
};

extern Modem g_modem;
