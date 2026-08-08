#pragma once

#include "Config.h"
#include <stdint.h>

// Heltec-compatible mesh messenger (SX1276 external or SX1262 on Wireless Tracker).

static constexpr int LORA_LOG_MAX = 24;
static constexpr int LORA_MSG_LEN = 160;

struct LoraMsg {
  bool outgoing;
  char text[LORA_MSG_LEN];
};

class LoraRadio {
 public:
  bool begin();
  void end();
  bool isReady() const { return ready_; }
  const char* status() const { return status_; }
  uint32_t deviceId() const { return deviceId_; }

  bool sendText(const char* body, uint32_t targetId = LORA_BROADCAST_ID);
  bool sendSos();
  void poll();

  int logCount() const { return logN_; }
  const LoraMsg* logAt(int i) const;

 private:
  static constexpr uint8_t kPktMessage = 0;
  static constexpr uint8_t kPktDelivered = 1;

  bool ready_ = false;
  uint32_t deviceId_ = 0;
  uint32_t msgId_ = 0;
  char status_[48] = {0};
  LoraMsg log_[LORA_LOG_MAX];
  int logN_ = 0;
  void* radio_ = nullptr;  // SX1276* or SX1262*

  void pushLog(bool out, const char* text);
  bool ensureRadio();
  uint32_t resolveDeviceId() const;
  uint32_t defaultTargetId() const;
  bool sendPacket(uint32_t targetId, uint8_t type, uint32_t messageId,
                  const uint8_t* body, uint16_t bodyLen);
  bool sendDelivered(uint32_t recipientId);
  void handleRxPacket(const uint8_t* packet, size_t packetLen);
};

extern LoraRadio g_lora;
