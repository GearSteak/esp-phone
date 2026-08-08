#include "keyboard.h"
#include <string.h>

Keyboard g_keyboard;

bool Keyboard::begin() {
  for (int r = 0; r < KB_ROWS; r++) {
    pinMode(KB_ROW_PINS[r], OUTPUT);
    digitalWrite(KB_ROW_PINS[r], HIGH);
  }
  for (int c = 0; c < KB_COLS; c++) {
    pinMode(KB_COL_PINS[c], INPUT_PULLUP);
  }
  memset(rawState_, 0, sizeof(rawState_));
  memset(stableState_, 0, sizeof(stableState_));
  memset(lastChangeMs_, 0, sizeof(lastChangeMs_));
  queue_ = xQueueCreate(32, sizeof(KeyEvent));
  return queue_ != nullptr;
}

void Keyboard::startTask() {
  xTaskCreatePinnedToCore(taskThunk, "kbd", STACK_KEYBOARD, this, PRIO_KEYBOARD,
                          nullptr, CORE_UI);
}

void Keyboard::pauseForCamera() {
  paused_ = true;
  for (int r = 0; r < KB_ROWS; r++) {
    pinMode(KB_ROW_PINS[r], INPUT);
  }
  // Soft keys on I2S pins (audio idle while camera open)
  pinMode(KB_CAM_SNAP_PIN, INPUT_PULLUP);
  pinMode(KB_CAM_BACK_PIN, INPUT_PULLUP);
  camSnapRaw_ = camSnapStable_ = false;
  camBackRaw_ = camBackStable_ = false;
}

void Keyboard::resumeAfterCamera() {
  for (int r = 0; r < KB_ROWS; r++) {
    pinMode(KB_ROW_PINS[r], OUTPUT);
    digitalWrite(KB_ROW_PINS[r], HIGH);
  }
  for (int c = 0; c < KB_COLS; c++) {
    pinMode(KB_COL_PINS[c], INPUT_PULLUP);
  }
  paused_ = false;
}

void Keyboard::taskThunk(void* arg) {
  static_cast<Keyboard*>(arg)->taskLoop();
}

void Keyboard::taskLoop() {
  for (;;) {
    if (paused_)
      scanCameraSoftKeys();
    else
      scanOnce();
    vTaskDelay(pdMS_TO_TICKS(KB_SCAN_PERIOD_MS));
  }
}

char Keyboard::mapAscii(uint16_t code, bool shifted) const {
  if (code >= 'A' && code <= 'Z') {
#if GATEWAY_MODE
    // Real QWERTY: shift = uppercase
    return shifted ? (char)code : (char)(code + 32);
#else
    if (shifted) return KB_SHIFT_MAP[code - 'A'];
    return (char)(code + 32);
#endif
  }
  if (code >= '0' && code <= '9') {
    if (shifted) return KB_DIGIT_SHIFT[code - '0'];
    return (char)code;
  }
  // Punctuation keys on gateway bottom letter row
  switch (code) {
    case ';':
      return shifted ? ':' : ';';
    case ',':
      return shifted ? '<' : ',';
    case '.':
      return shifted ? '>' : '.';
    case '/':
      return shifted ? '?' : '/';
    case ' ':
    case '*':
    case '#':
      return (char)code;
    default:
      break;
  }
  return 0;
}

void Keyboard::scanCameraSoftKeys() {
  uint32_t now = millis();
  bool snap = digitalRead(KB_CAM_SNAP_PIN) == LOW;
  bool back = digitalRead(KB_CAM_BACK_PIN) == LOW;

  auto debounce = [&](bool pressed, bool& raw, bool& stable, uint32_t& t0,
                      uint16_t code) {
    if (pressed != raw) {
      raw = pressed;
      t0 = now;
    }
    if ((now - t0) >= KB_DEBOUNCE_MS && pressed != stable) {
      stable = pressed;
      KeyEvent ev{};
      ev.code = code;
      ev.pressed = pressed;
      ev.shifted = false;
      ev.ascii = 0;
      if (queue_) xQueueSend(queue_, &ev, 0);
    }
  };

  debounce(snap, camSnapRaw_, camSnapStable_, camSnapMs_, '\n');
  debounce(back, camBackRaw_, camBackStable_, camBackMs_, '\b');
}

void Keyboard::scanOnce() {
  uint32_t now = millis();
  for (int r = 0; r < KB_ROWS; r++) {
    for (int i = 0; i < KB_ROWS; i++) {
      digitalWrite(KB_ROW_PINS[i], i == r ? LOW : HIGH);
    }
    delayMicroseconds(5);
    for (int c = 0; c < KB_COLS; c++) {
      bool pressed = digitalRead(KB_COL_PINS[c]) == LOW;
      if (pressed != rawState_[r][c]) {
        rawState_[r][c] = pressed;
        lastChangeMs_[r][c] = now;
      }
      if ((now - lastChangeMs_[r][c]) >= KB_DEBOUNCE_MS &&
          pressed != stableState_[r][c]) {
        stableState_[r][c] = pressed;
        uint16_t code = KB_LAYOUT[r][c];
        if (code == KEY_SHIFT && pressed) shift_ = !shift_;
        KeyEvent ev{};
        ev.code = code;
        ev.pressed = pressed;
        ev.shifted = shift_;
        ev.ascii = pressed ? mapAscii(code, shift_) : 0;
        if (pressed && shift_ && ev.ascii && code != KEY_SHIFT) {
          shift_ = false;
          ev.shifted = true;
        }
        if (queue_) xQueueSend(queue_, &ev, 0);
      }
    }
  }
  for (int i = 0; i < KB_ROWS; i++) digitalWrite(KB_ROW_PINS[i], HIGH);
}

bool Keyboard::popEvent(KeyEvent& ev, uint32_t waitMs) {
  if (!queue_) return false;
  return xQueueReceive(queue_, &ev, pdMS_TO_TICKS(waitMs)) == pdTRUE;
}
