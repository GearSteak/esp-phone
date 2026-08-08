#include "cardkb.h"
#include "Config.h"

#if !GATEWAY_MODE || !CARDKB_ENABLE

namespace CardKb {
bool begin() { return false; }
void poll(void (*)(char)) {}
}

#else

#include <Arduino.h>
#include <Wire.h>

namespace CardKb {

bool begin() {
  Wire.begin(CARDKB_SDA, CARDKB_SCL);
  Wire.setClock(100000);
  // Probe
  Wire.beginTransmission(CARDKB_ADDR);
  uint8_t err = Wire.endTransmission();
  if (err != 0) {
    Serial.printf("[CardKB] not found at 0x%02X (err=%u) — plug in when ready\n",
                  CARDKB_ADDR, (unsigned)err);
  } else {
    Serial.printf("[CardKB] OK I2C 0x%02X SDA=%d SCL=%d\n", CARDKB_ADDR,
                  CARDKB_SDA, CARDKB_SCL);
  }
  return true;  // allow hotplug; keep polling
}

void poll(void (*emitAscii)(char ch)) {
  if (!emitAscii) return;
  Wire.requestFrom((int)CARDKB_ADDR, 1);
  if (!Wire.available()) return;
  char c = (char)Wire.read();
  if (c == 0) return;
  emitAscii(c);
}

}  // namespace CardKb

#endif
