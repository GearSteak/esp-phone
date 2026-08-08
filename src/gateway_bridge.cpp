#include "gateway_bridge.h"
#include "Config.h"

#if !GATEWAY_MODE

namespace GatewayBridge {
bool begin() { return false; }
void loop() {}
void emitStatus() {}
void emitLine(const char*) {}
}

#else

#include "keyboard.h"
#include "lora_radio.h"
#include "notify_display.h"
#include "cardkb.h"
#include "step_tilt.h"
#include <Arduino.h>
#include <string.h>
#include <stdio.h>
#include <stdarg.h>
#include <ctype.h>
#include <stdlib.h>

namespace GatewayBridge {

static char s_line[256];
static size_t s_lineLen = 0;
static uint32_t s_lastStatusMs = 0;
static bool s_volRaw[3] = {false, false, false};
static bool s_volStable[3] = {false, false, false};
static uint32_t s_volMs[3] = {0, 0, 0};

static const int kVolPins[3] = {VOL_UP_PIN, VOL_DOWN_PIN, VOL_MUTE_PIN};
static const char* kVolNames[3] = {"VOL_UP", "VOL_DOWN", "MUTE"};

void emitLine(const char* line) {
  if (!line) return;
  Serial.println(line);
}

static void emitf(const char* fmt, ...) {
  char buf[200];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  emitLine(buf);
}

static const char* keyName(uint16_t code) {
  switch (code) {
    case KEY_UP: return "UP";
    case KEY_DOWN: return "DOWN";
    case KEY_LEFT: return "LEFT";
    case KEY_RIGHT: return "RIGHT";
    case KEY_CALL: return "CALL";
    case KEY_END: return "END";
    case KEY_SHIFT: return "SHIFT";
    case '\b': return "BKSP";
    case '\n': return "ENTER";
    case ' ': return "SPACE";
    default: return nullptr;
  }
}

static void emitKey(const KeyEvent& ev) {
  const char* name = keyName(ev.code);
  if (name) {
    emitf("KEY %s %s", ev.pressed ? "DOWN" : "UP", name);
    return;
  }
  char ch = 0;
  if (ev.pressed && ev.ascii)
    ch = ev.ascii;
  else if (!ev.pressed) {
    if (ev.code >= 'A' && ev.code <= 'Z')
      ch = (char)(ev.code + 32);
    else if (ev.code >= 32 && ev.code < 127)
      ch = (char)ev.code;
  }
  if (ch >= 32 && ch < 127) {
    emitf("KEY %s %c", ev.pressed ? "DOWN" : "UP", ch);
    return;
  }
  if (ev.pressed)
    emitf("KEY DOWN 0x%02X", (unsigned)(uint8_t)ev.code);
  else
    emitf("KEY UP 0x%04X", (unsigned)ev.code);
}

void emitStatus() {
#if CARDKB_ENABLE
  emitf("STATUS role=cardkb+lora+notify+steps lora=%d id=%lu steps=%lu %s",
        g_lora.isReady() ? 1 : 0, (unsigned long)g_lora.deviceId(),
        (unsigned long)StepTilt::count(), g_lora.status());
#else
  emitf("STATUS role=keyboard+lora+notify+steps lora=%d id=%lu steps=%lu %s",
        g_lora.isReady() ? 1 : 0, (unsigned long)g_lora.deviceId(),
        (unsigned long)StepTilt::count(), g_lora.status());
#endif
}

static void handleNotifCmd(char* body) {
  // NOTIF kind|title|body   or   NOTIF title|body
  char* p1 = strchr(body, '|');
  if (!p1) {
    NotifyDisplay::show("Alert", body, "info");
    emitLine("ACK NOTIF");
    return;
  }
  *p1 = 0;
  char* p2 = strchr(p1 + 1, '|');
  if (!p2) {
    NotifyDisplay::show(body, p1 + 1, "info");
  } else {
    *p2 = 0;
    NotifyDisplay::show(p1 + 1, p2 + 1, body);
  }
  emitLine("ACK NOTIF");
}

static void handleCommand(char* line) {
  while (*line && isspace((unsigned char)*line)) line++;
  size_t n = strlen(line);
  while (n && isspace((unsigned char)line[n - 1])) line[--n] = 0;
  if (!n) return;

  if (!strcasecmp(line, "PING")) {
    emitLine("PONG");
    return;
  }
  if (!strcasecmp(line, "STATUS")) {
    emitStatus();
    return;
  }
  if (!strcasecmp(line, "CLEAR") || !strcasecmp(line, "NOTIF CLEAR")) {
    NotifyDisplay::clear();
    emitLine("ACK CLEAR");
    return;
  }
  if (!strncasecmp(line, "NOTIF ", 6)) {
    handleNotifCmd(line + 6);
    return;
  }
  if (!strncasecmp(line, "LORA SEND ", 10)) {
    char* body = line + 10;
    char* sp = strchr(body, ' ');
    uint32_t target = 0;
    const char* text = body;
    if (sp && isdigit((unsigned char)body[0])) {
      *sp = 0;
      target = (uint32_t)strtoul(body, nullptr, 10);
      text = sp + 1;
    }
    if (g_lora.sendText(text, target))
      emitLine("ACK LORA SENT");
    else
      emitLine("ERR LORA send failed");
    return;
  }
  if (!strcasecmp(line, "LORA SOS")) {
    if (g_lora.sendSos())
      emitLine("ACK LORA SOS");
    else
      emitLine("ERR LORA SOS failed");
    return;
  }
  if (!strcasecmp(line, "STEPS") || !strcasecmp(line, "STEPS?")) {
    emitf("STEPS %lu", (unsigned long)StepTilt::count());
    return;
  }
  if (!strcasecmp(line, "STEPS RESET")) {
    StepTilt::reset();
    emitf("STEPS %lu", (unsigned long)StepTilt::count());
    return;
  }
  emitf("ERR unknown cmd: %s", line);
}

static void pollSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      s_line[s_lineLen] = 0;
      if (s_lineLen) handleCommand(s_line);
      s_lineLen = 0;
      continue;
    }
    if (s_lineLen + 1 < sizeof(s_line)) s_line[s_lineLen++] = c;
  }
}

static void pollVolumeKeys() {
  uint32_t now = millis();
  for (int i = 0; i < 3; i++) {
    bool pressed = digitalRead(kVolPins[i]) == LOW;
    if (pressed != s_volRaw[i]) {
      s_volRaw[i] = pressed;
      s_volMs[i] = now;
    }
    if ((now - s_volMs[i]) >= KB_DEBOUNCE_MS && pressed != s_volStable[i]) {
      s_volStable[i] = pressed;
      emitf("KEY %s %s", pressed ? "DOWN" : "UP", kVolNames[i]);
    }
  }
}

static void emitCardKbChar(char c) {
  // CardKB sends one shot per press — synthesize DOWN/UP for Pi
  if (c == '\r') c = '\n';
  if (c == 0x08 || c == 0x7F) {
    emitf("KEY DOWN BKSP");
    emitf("KEY UP BKSP");
    return;
  }
  if (c == '\n' || c == 0x0D) {
    emitf("KEY DOWN ENTER");
    emitf("KEY UP ENTER");
    return;
  }
  if (c == ' ') {
    emitf("KEY DOWN SPACE");
    emitf("KEY UP SPACE");
    return;
  }
  if (c == 0x1B) {
    emitf("KEY DOWN END");  // treat ESC-ish as End/back
    emitf("KEY UP END");
    return;
  }
  if (c >= 32 && c < 127) {
    emitf("KEY DOWN %c", c);
    emitf("KEY UP %c", c);
  }
}

static void pollCardKb() {
#if CARDKB_ENABLE
  CardKb::poll(emitCardKbChar);
#endif
}

static void pollKeyboard() {
#if !CARDKB_ENABLE
  KeyEvent ev;
  while (g_keyboard.popEvent(ev, 0)) emitKey(ev);
#endif
}

static void pollLora() {
  g_lora.poll();
  static int lastN = 0;
  int n = g_lora.logCount();
  if (n < lastN) lastN = 0;
  for (int i = lastN; i < n; i++) {
    const LoraMsg* m = g_lora.logAt(i);
    if (!m || m->outgoing) continue;
    emitf("LORA RX %s", m->text);
    // Also show locally (works even if Pi is in desktop / offline)
    NotifyDisplay::show("LoRa", m->text, "lora");
  }
  lastN = n;
}

bool begin() {
  pinMode(VOL_UP_PIN, INPUT_PULLUP);
  pinMode(VOL_DOWN_PIN, INPUT_PULLUP);
  pinMode(VOL_MUTE_PIN, INPUT_PULLUP);

#if CARDKB_ENABLE
  CardKb::begin();
#else
  g_keyboard.begin();
  g_keyboard.startTask();
#endif
  StepTilt::begin();
  g_lora.begin();

  char idle[40];
  snprintf(idle, sizeof(idle), "id %lu", (unsigned long)g_lora.deviceId());
  NotifyDisplay::setIdleStatus(idle);

#if CARDKB_ENABLE
  emitLine("READY cardkb+lora+notify+steps");
#else
  emitLine("READY keyboard+lora+notify+steps");
#endif
  emitStatus();
  return true;
}

void loop() {
  pollSerial();
  pollKeyboard();
  pollCardKb();
  pollVolumeKeys();
  pollLora();
  StepTilt::poll();
  uint32_t steps = 0;
  if (StepTilt::takeDirty(&steps)) emitf("STEPS %lu", (unsigned long)steps);

  if (millis() - s_lastStatusMs > 60000) {
    s_lastStatusMs = millis();
    emitStatus();
  }
}

}  // namespace GatewayBridge

#endif
