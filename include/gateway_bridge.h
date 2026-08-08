#pragma once

#include <stdint.h>
#include <stddef.h>

// USB-CDC bridge for Pi handset: LoRa + notification panel.
// Digivice UI is on the Pi LCD HAT; ESP ST7735 shows alerts only.
//
// ESP→Pi: KEY …, LORA RX …, READY, STATUS, ACK/ERR, PONG
// Pi→ESP: PING, STATUS, LORA SEND/SOS, NOTIF kind|title|body, CLEAR

namespace GatewayBridge {

bool begin();
void loop();

void emitStatus();
void emitLine(const char* line);

}  // namespace GatewayBridge
