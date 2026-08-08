#include "lora_radio.h"
#include "Config.h"
#include <string.h>
#include <stdio.h>
#include <SPI.h>

#if !GATEWAY_MODE
#include "phone_data.h"
#include "gps.h"
#endif

#if LORA_ENABLE
#include <RadioLib.h>

static volatile bool s_loraRxFlag = false;
static void IRAM_ATTR loraRxIsr() { s_loraRxFlag = true; }

#if LORA_RADIO_SX1262
using LoraHw = SX1262;
#else
using LoraHw = SX1276;
#endif
#endif

LoraRadio g_lora;

void LoraRadio::pushLog(bool out, const char* text) {
  if (logN_ >= LORA_LOG_MAX) {
    for (int i = 1; i < LORA_LOG_MAX; i++) log_[i - 1] = log_[i];
    logN_ = LORA_LOG_MAX - 1;
  }
  log_[logN_].outgoing = out;
  strncpy(log_[logN_].text, text ? text : "", sizeof(log_[0].text) - 1);
  log_[logN_].text[sizeof(log_[0].text) - 1] = 0;
  logN_++;
}

const LoraMsg* LoraRadio::logAt(int i) const {
  return (i >= 0 && i < logN_) ? &log_[i] : nullptr;
}

uint32_t LoraRadio::resolveDeviceId() const {
#if GATEWAY_MODE
  uint32_t configured = 0;
#else
  uint32_t configured = g_settings.get().loraDeviceId;
#endif
  if (configured != 0) return configured;

  uint64_t chipid = ESP.getEfuseMac();
  uint64_t macValue = 0;
  for (int i = 0; i < 6; i++) macValue = (macValue << 8) | ((chipid >> (8 * i)) & 0xFF);
  uint64_t phoneNumber = 100000ULL + (macValue % 900000ULL);
  return (uint32_t)(phoneNumber & 0xFFFFFFFFULL);
}

uint32_t LoraRadio::defaultTargetId() const {
#if GATEWAY_MODE
  return LORA_BROADCAST_ID;
#else
  uint32_t target = g_settings.get().loraTargetId;
  return target ? target : LORA_BROADCAST_ID;
#endif
}

bool LoraRadio::ensureRadio() {
#if !LORA_ENABLE
  snprintf(status_, sizeof(status_), "LoRa disabled in Config");
  return false;
#else
  if (ready_ && radio_) return true;

  deviceId_ = resolveDeviceId();

#if HELTEC_WIRELESS_TRACKER
  // TFT owned by NotifyDisplay — leave CS/BL alone here
#else
  pinMode(DISP_CS, OUTPUT);
  digitalWrite(DISP_CS, HIGH);
#endif

  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, -1);

#if LORA_RADIO_SX1262
  Module* mod = new Module(LORA_CS, LORA_DIO1, LORA_RST, LORA_BUSY, SPI);
  LoraHw* radio = new LoraHw(mod);
  radio_ = radio;
  int st = radio->begin(LORA_FREQ_MHZ, LORA_BW_KHZ, LORA_SF, LORA_CR,
                        LORA_SYNC_WORD, LORA_TX_POWER_DBM, LORA_PREAMBLE);
#else
  Module* mod = new Module(LORA_CS, LORA_DIO0, LORA_RST, RADIOLIB_NC, SPI);
  LoraHw* radio = new LoraHw(mod);
  radio_ = radio;
  int st = radio->begin(LORA_FREQ_MHZ, LORA_BW_KHZ, LORA_SF, LORA_CR,
                        LORA_SYNC_WORD, LORA_TX_POWER_DBM, LORA_PREAMBLE);
#endif
  if (st != RADIOLIB_ERR_NONE) {
    snprintf(status_, sizeof(status_), "Init fail %d — check wiring", st);
    Serial.printf("[LORA] begin failed: %d\n", st);
    delete radio;
    radio_ = nullptr;
    delete mod;
    ready_ = false;
    return false;
  }
  radio->setOutputPower(LORA_TX_POWER_DBM);
  radio->setPacketReceivedAction(loraRxIsr);
  radio->startReceive();
  ready_ = true;
#if LORA_RADIO_SX1262
  snprintf(status_, sizeof(status_), "SX1262 %.3f MHz OK", LORA_FREQ_MHZ);
#else
  snprintf(status_, sizeof(status_), "SX1276 %.3f MHz OK", LORA_FREQ_MHZ);
#endif
  Serial.printf("[LORA] mesh ready id=%lu freq=%.3f\n",
                (unsigned long)deviceId_, LORA_FREQ_MHZ);
  return true;
#endif
}

bool LoraRadio::begin() {
  logN_ = 0;
  msgId_ = (uint32_t)millis();
  return ensureRadio();
}

void LoraRadio::end() {
#if LORA_ENABLE
  if (radio_) {
    delete (LoraHw*)radio_;
    radio_ = nullptr;
  }
#endif
  ready_ = false;
  snprintf(status_, sizeof(status_), "LoRa off");
}

bool LoraRadio::sendPacket(uint32_t targetId, uint8_t type, uint32_t messageId,
                           const uint8_t* body, uint16_t bodyLen) {
#if !LORA_ENABLE
  (void)targetId;
  (void)type;
  (void)messageId;
  (void)body;
  (void)bodyLen;
  return false;
#else
  if (!ensureRadio()) return false;

  uint8_t packet[256];
  uint16_t packetLen = 0;

  if (type == kPktDelivered) {
    packetLen = 9;
    packet[0] = (deviceId_ >> 24) & 0xFF;
    packet[1] = (deviceId_ >> 16) & 0xFF;
    packet[2] = (deviceId_ >> 8) & 0xFF;
    packet[3] = deviceId_ & 0xFF;
    packet[4] = (targetId >> 24) & 0xFF;
    packet[5] = (targetId >> 16) & 0xFF;
    packet[6] = (targetId >> 8) & 0xFF;
    packet[7] = targetId & 0xFF;
    packet[8] = kPktDelivered;
  } else {
    packetLen = (uint16_t)(15 + bodyLen);
    if (packetLen > 255 || bodyLen > LORA_MAX_PAYLOAD) return false;

    packet[0] = (deviceId_ >> 24) & 0xFF;
    packet[1] = (deviceId_ >> 16) & 0xFF;
    packet[2] = (deviceId_ >> 8) & 0xFF;
    packet[3] = deviceId_ & 0xFF;
    packet[4] = (targetId >> 24) & 0xFF;
    packet[5] = (targetId >> 16) & 0xFF;
    packet[6] = (targetId >> 8) & 0xFF;
    packet[7] = targetId & 0xFF;
    packet[8] = kPktMessage;
    packet[9] = (messageId >> 24) & 0xFF;
    packet[10] = (messageId >> 16) & 0xFF;
    packet[11] = (messageId >> 8) & 0xFF;
    packet[12] = messageId & 0xFF;
    packet[13] = (bodyLen >> 8) & 0xFF;
    packet[14] = bodyLen & 0xFF;
    if (bodyLen) memcpy(&packet[15], body, bodyLen);
  }

#if !HELTEC_WIRELESS_TRACKER
  digitalWrite(DISP_CS, HIGH);
#endif
  int st = ((LoraHw*)radio_)->transmit(packet, packetLen);
  ((LoraHw*)radio_)->startReceive();
  if (st != RADIOLIB_ERR_NONE) {
    snprintf(status_, sizeof(status_), "TX fail %d", st);
    return false;
  }
  return true;
#endif
}

bool LoraRadio::sendDelivered(uint32_t recipientId) {
  return sendPacket(recipientId, kPktDelivered, 0, nullptr, 0);
}

bool LoraRadio::sendText(const char* body, uint32_t targetId) {
  if (!body || !body[0]) return false;
  if (targetId == 0) targetId = defaultTargetId();

  uint16_t len = (uint16_t)strlen(body);
  if (len > LORA_MAX_PAYLOAD) len = LORA_MAX_PAYLOAD;

  uint32_t id = ++msgId_;
  if (!sendPacket(targetId, kPktMessage, id, (const uint8_t*)body, len))
    return false;

  char line[LORA_MSG_LEN];
  if (targetId == LORA_BROADCAST_ID)
    snprintf(line, sizeof(line), "[bc] %s", body);
  else
    snprintf(line, sizeof(line), ">%lu %s", (unsigned long)targetId, body);
  pushLog(true, line);
  snprintf(status_, sizeof(status_), "Sent");
  return true;
}

bool LoraRadio::sendSos() {
  char body[120];
#if GATEWAY_MODE
  snprintf(body, sizeof(body), "SOS NEED HELP");
#else
  char loc[48] = {0};
  if (g_gps.fix().valid) {
    g_gps.formatLatLon(loc, sizeof(loc));
    snprintf(body, sizeof(body), "SOS %s", loc);
  } else {
    snprintf(body, sizeof(body), "SOS NEED HELP");
  }
#endif
  return sendText(body, LORA_BROADCAST_ID);
}

void LoraRadio::handleRxPacket(const uint8_t* packet, size_t packetLen) {
  if (packetLen < 9) return;

  uint32_t rxDeviceId = ((uint32_t)packet[0] << 24) | ((uint32_t)packet[1] << 16) |
                        ((uint32_t)packet[2] << 8) | packet[3];
  uint32_t rxTargetId = ((uint32_t)packet[4] << 24) | ((uint32_t)packet[5] << 16) |
                        ((uint32_t)packet[6] << 8) | packet[7];
  uint8_t packetType = packet[8];

  if (packetType == kPktDelivered) {
    if (packetLen >= 9 && rxTargetId == deviceId_) {
      char line[LORA_MSG_LEN];
      snprintf(line, sizeof(line), "delivered by %lu",
               (unsigned long)rxDeviceId);
      pushLog(false, line);
    }
    return;
  }

  if (packetType != kPktMessage || packetLen < 15) return;

  uint32_t rxMessageId = ((uint32_t)packet[9] << 24) | ((uint32_t)packet[10] << 16) |
                         ((uint32_t)packet[11] << 8) | packet[12];
  uint16_t msgLen = ((uint16_t)packet[13] << 8) | packet[14];
  if (msgLen == 0 || msgLen >= LORA_MAX_PAYLOAD || (15 + msgLen) > packetLen)
    return;

  if (rxTargetId != LORA_BROADCAST_ID && rxTargetId != deviceId_) return;

  char body[LORA_MAX_PAYLOAD + 1];
  memcpy(body, &packet[15], msgLen);
  body[msgLen] = 0;

  char line[LORA_MSG_LEN];
  snprintf(line, sizeof(line), "<%lu %s", (unsigned long)rxDeviceId, body);
  pushLog(false, line);
  snprintf(status_, sizeof(status_), "RX %uB", (unsigned)msgLen);
#if !GATEWAY_MODE
  phonePlayNotify(900, 120);
#endif

  if (rxTargetId == deviceId_) sendDelivered(rxDeviceId);
  (void)rxMessageId;
}

void LoraRadio::poll() {
  if (!ready_ || !radio_) return;
#if LORA_ENABLE
  if (!s_loraRxFlag) return;
  s_loraRxFlag = false;
#if !HELTEC_WIRELESS_TRACKER
  digitalWrite(DISP_CS, HIGH);
#endif

  LoraHw* radio = (LoraHw*)radio_;
  size_t packetLen = radio->getPacketLength();
  if (packetLen == 0 || packetLen > 256) {
    radio->startReceive();
    return;
  }

  uint8_t packet[256];
  int st = radio->readData(packet, packetLen);
  radio->startReceive();
  if (st == RADIOLIB_ERR_NONE && packetLen > 0)
    handleRxPacket(packet, packetLen);
#endif
}
