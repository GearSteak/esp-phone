#pragma once

#include "Config.h"
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

struct KeyEvent {
  uint16_t code;
  bool pressed;
  bool shifted;
  char ascii;
};

class Keyboard {
 public:
  bool begin();
  void startTask();
  bool popEvent(KeyEvent& ev, uint32_t waitMs = 0);
  bool shiftActive() const { return shift_; }
  QueueHandle_t queue() const { return queue_; }

  // Camera owns DVP pins — pause matrix, use Snap/Back GPIOs instead
  void pauseForCamera();
  void resumeAfterCamera();
  bool isPaused() const { return paused_; }

 private:
  QueueHandle_t queue_ = nullptr;
  bool shift_ = false;
  bool paused_ = false;
  bool rawState_[KB_ROWS][KB_COLS] = {};
  bool stableState_[KB_ROWS][KB_COLS] = {};
  uint32_t lastChangeMs_[KB_ROWS][KB_COLS] = {};
  bool camSnapRaw_ = false, camSnapStable_ = false;
  bool camBackRaw_ = false, camBackStable_ = false;
  uint32_t camSnapMs_ = 0, camBackMs_ = 0;

  void scanOnce();
  void scanCameraSoftKeys();
  char mapAscii(uint16_t code, bool shifted) const;
  static void taskThunk(void* arg);
  void taskLoop();
};

extern Keyboard g_keyboard;
