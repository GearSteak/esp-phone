#include "step_tilt.h"
#include "Config.h"

#if !GATEWAY_MODE || !STEP_TILT_ENABLE

namespace StepTilt {
bool begin() { return false; }
void poll() {}
uint32_t count() { return 0; }
void reset() {}
bool takeDirty(uint32_t*) { return false; }
}

#else

#include <Arduino.h>

namespace StepTilt {

static bool s_raw = false;
static bool s_stable = false;
static uint32_t s_edgeMs = 0;
static uint32_t s_lastStepMs = 0;
static uint32_t s_count = 0;
static bool s_dirty = false;

bool begin() {
  pinMode(STEP_TILT_PIN, INPUT_PULLUP);
  delay(5);
  s_raw = digitalRead(STEP_TILT_PIN) == LOW;
  s_stable = s_raw;
  s_edgeMs = millis();
  s_lastStepMs = 0;
  s_count = 0;
  s_dirty = false;
  Serial.printf("[StepTilt] SW-520D on GPIO %d (pull-up, other leg GND)\n",
                STEP_TILT_PIN);
  return true;
}

void poll() {
  uint32_t now = millis();
  bool closed = digitalRead(STEP_TILT_PIN) == LOW;  // ball bridges to GND
  if (closed != s_raw) {
    s_raw = closed;
    s_edgeMs = now;
  }
  if ((now - s_edgeMs) < STEP_TILT_DEBOUNCE_MS) return;
  if (closed == s_stable) return;
  s_stable = closed;

  // Count a step on each settled transition (walk bounce flips the ball).
  if (s_lastStepMs != 0 && (now - s_lastStepMs) < STEP_TILT_MIN_MS) return;
  s_lastStepMs = now;
  s_count++;
  s_dirty = true;
}

uint32_t count() { return s_count; }

void reset() {
  s_count = 0;
  s_dirty = true;
}

bool takeDirty(uint32_t* outCount) {
  if (!s_dirty) return false;
  s_dirty = false;
  if (outCount) *outCount = s_count;
  return true;
}

}  // namespace StepTilt

#endif
