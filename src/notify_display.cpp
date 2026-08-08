#include "notify_display.h"
#include "Config.h"

#if !GATEWAY_MODE || !HELTEC_WIRELESS_TRACKER

namespace NotifyDisplay {
bool begin() { return false; }
void loop() {}
void show(const char*, const char*, const char*) {}
void clear() {}
void setIdleStatus(const char*) {}
}

#else

#include <Arduino.h>
#include <SPI.h>
#include <TFT_eSPI.h>
#include <string.h>
#include <stdio.h>

namespace NotifyDisplay {

static TFT_eSPI s_tft;
static bool s_ok = false;
static uint32_t s_clearAt = 0;
static char s_idle[48] = "Digivice notify";
static bool s_showing = false;

static uint16_t kindColor(const char* kind) {
  if (!kind) return TFT_CYAN;
  if (!strcasecmp(kind, "sms")) return TFT_GREEN;
  if (!strcasecmp(kind, "lora")) return TFT_ORANGE;
  if (!strcasecmp(kind, "alarm") || !strcasecmp(kind, "sos")) return TFT_RED;
  if (!strcasecmp(kind, "call")) return TFT_YELLOW;
  return TFT_CYAN;
}

static void drawIdle() {
  if (!s_ok) return;
  s_tft.fillScreen(TFT_BLACK);
  s_tft.setTextDatum(MC_DATUM);
  s_tft.setTextColor(TFT_DARKGREY, TFT_BLACK);
  s_tft.drawString("ESP notify", 80, 28, 2);
  s_tft.setTextColor(TFT_LIGHTGREY, TFT_BLACK);
  s_tft.drawString(s_idle, 80, 52, 1);
  s_showing = false;
}

bool begin() {
  pinMode(TFT_VEXT_PIN, OUTPUT);
  digitalWrite(TFT_VEXT_PIN, HIGH);
  delay(50);
  pinMode(TFT_BL_PIN, OUTPUT);
  digitalWrite(TFT_BL_PIN, HIGH);

  s_tft.init();
  s_tft.setRotation(1);  // landscape 160×80
  s_tft.fillScreen(TFT_BLACK);
  s_ok = true;
  drawIdle();
  Serial.println("[NOTIFY] ST7735 ready 160x80");
  return true;
}

void setIdleStatus(const char* line) {
  if (!line) return;
  strncpy(s_idle, line, sizeof(s_idle) - 1);
  s_idle[sizeof(s_idle) - 1] = 0;
  if (!s_showing) drawIdle();
}

void clear() {
  s_clearAt = 0;
  drawIdle();
}

void show(const char* title, const char* body, const char* kind) {
  if (!s_ok) return;
  char t[28];
  char b[64];
  strncpy(t, title ? title : "Alert", sizeof(t) - 1);
  t[sizeof(t) - 1] = 0;
  strncpy(b, body ? body : "", sizeof(b) - 1);
  b[sizeof(b) - 1] = 0;

  uint16_t col = kindColor(kind);
  s_tft.fillScreen(TFT_BLACK);
  s_tft.fillRect(0, 0, 160, 14, col);
  s_tft.setTextDatum(TL_DATUM);
  s_tft.setTextColor(TFT_BLACK, col);
  s_tft.drawString(t, 2, 2, 1);

  s_tft.setTextColor(TFT_WHITE, TFT_BLACK);
  // wrap body roughly
  int y = 20;
  const char* p = b;
  while (*p && y < 72) {
    char line[22];
    size_t i = 0;
    while (*p && i + 1 < sizeof(line)) {
      if (*p == '\n') {
        p++;
        break;
      }
      line[i++] = *p++;
      if (i >= 20) break;
    }
    line[i] = 0;
    s_tft.drawString(line, 2, y, 1);
    y += 12;
  }
  s_showing = true;
  s_clearAt = millis() + 12000;  // auto-clear 12s
}

void loop() {
  if (!s_ok) return;
  if (s_showing && s_clearAt && (int32_t)(millis() - s_clearAt) >= 0) {
    clear();
  }
}

}  // namespace NotifyDisplay

#endif
