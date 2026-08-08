#pragma once

#include <stdint.h>

// M5Stack Unit CardKB — I2C @ 0x5F (Grove). Polled by gateway; emits KEY lines.

namespace CardKb {

bool begin();
/** Poll I2C; call emitKey(ascii) for each new key (0 = none). */
void poll(void (*emitAscii)(char ch));

}  // namespace CardKb
