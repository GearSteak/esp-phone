#include <Arduino.h>
#include "Config.h"
#include "gateway_bridge.h"
#include "notify_display.h"

#if !GATEWAY_MODE
#error "gateway_main.cpp requires -DGATEWAY_MODE=1"
#endif

void setup() {
  Serial.begin(115200);
  delay(400);
  Serial.println();
#if HELTEC_WIRELESS_TRACKER
  Serial.println("=== Heltec Tracker gateway + notify TFT ===");
  Serial.println("DigiUART 9600 on GPIO43/44 → Pi soft-UART (battery; no USB power)");
  Serial.println("Keys/LoRa CDC; ST7735 shows Pi alerts");
  NotifyDisplay::begin();
#else
  Serial.println("=== ESP Handset Bridge (keys + LoRa) ===");
#endif
  Serial.println("CDC: KEY / LORA / NOTIF / CLEAR / PING / STATUS / BATTERY");
  Serial.println("Cellular is on Pi SIM7600 HAT");
  GatewayBridge::begin();
}

void loop() {
  GatewayBridge::loop();
  NotifyDisplay::loop();
  delay(2);
}
