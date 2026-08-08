#pragma once

#include <stdint.h>

// SW-520D ball tilt → crude step counter (Heltec GPIO).
namespace StepTilt {
bool begin();
void poll();
uint32_t count();
void reset();
/** True if count changed since last takeNewCount (for CDC emit). */
bool takeDirty(uint32_t* outCount);
}
