#include <Arduino.h>
#include "Config.h"
#include "shared_state.h"
#include "modem.h"
#include "audio.h"
#include "keyboard.h"
#include "sip.h"
#include "ui.h"
#include "games.h"
#include "storage.h"
#include "sd_assets.h"
#include "media_player.h"
#include "notes_todo.h"
#include "phone_data.h"
#include "phone_tools.h"
#include <string.h>

/*
 * Dual-core layout
 * ----------------
 * Core 0: modem AT, data session, SIP/RTP, call state
 * Core 1: LVGL UI, keyboard (also on Core 1), games
 */

static void modemSipTask(void* arg);
static void uiTask(void* arg);
static int csqToBars(int csq);
static void syncSmsInbox();

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.println("=== ESP32-S3 DIY 4G Phone (VoIP + SMS) ===");
  Serial.println("Audio: ESP32 I2S only | Modem PCM: unused");
  Serial.println("Antenna: required (board does not include 4G antenna)");

#if CONFIG_PLACEHOLDER_WARN
  if (String(SIP_USERNAME) == "YOUR_SIP_USER") {
    Serial.println("[WARN] Set SIP credentials in include/Config.h");
  }
#endif

  g_statusMutex = xSemaphoreCreateMutex();
  memset(&g_status, 0, sizeof(g_status));
  g_status.csq = 99;
  g_status.batteryPercent = 100;
  g_status.callState = CALL_IDLE;

  Storage::begin();
  SdAssets::begin();
  g_settings.load();
  g_contacts.load();
  g_callLog.load();
  g_smsStore.load();
  g_notifs.load();
  g_clock.load();
  g_calendar.load();
  g_games.begin();
  g_media.begin();
  g_notes.load();
  g_todos.load();

  statusLock();
  g_status.airplaneMode = g_settings.get().airplaneMode;
  statusUnlock();
  connectivityApplyFromSettings();

  if (!g_keyboard.begin()) {
    Serial.println("[ERR] Keyboard init failed");
  }
  g_keyboard.startTask();

  if (!g_audio.begin()) {
    Serial.println("[ERR] I2S audio init failed");
  } else {
    Serial.println("[OK] I2S ready — play test tone from Settings");
  }

  if (!g_ui.begin()) {
    Serial.println("[ERR] UI/LVGL init failed");
  }

  xTaskCreatePinnedToCore(modemSipTask, "modem_sip", STACK_MODEM + STACK_SIP,
                          nullptr, PRIO_SIP, nullptr, CORE_MODEM);
  xTaskCreatePinnedToCore(uiTask, "ui", STACK_UI, nullptr, PRIO_UI, nullptr,
                          CORE_UI);

  Serial.println("[OK] Tasks started");
}

void loop() {
  vTaskDelay(pdMS_TO_TICKS(1000));
}

static int csqToBars(int csq) {
  if (csq == 99 || csq < 0) return 0;
  if (csq < 6) return 1;
  if (csq < 12) return 2;
  if (csq < 18) return 3;
  return 4;
}

static void syncSmsInbox() {
  SmsMessage msgs[12];
  int n = g_modem.listSms(msgs, 12);
  for (int i = 0; i < n; i++) {
    // Import unread / recent; skip empty
    if (!msgs[i].text[0]) continue;
    bool unread = (strstr(msgs[i].status, "UNREAD") != nullptr) ||
                  (strstr(msgs[i].status, "REC UNREAD") != nullptr);
    if (!unread && strstr(msgs[i].status, "REC READ") != nullptr) {
      // still import once if thread missing
      if (g_smsStore.findThread(msgs[i].number) >= 0) {
        g_modem.deleteSms(msgs[i].index);
        continue;
      }
    }
    g_smsStore.addInbound(msgs[i].number, msgs[i].text);
    if (unread) {
      char title[40];
      snprintf(title, sizeof(title), "SMS %s",
               g_contacts.nameForNumber(msgs[i].number));
      g_notifs.push(NOTIF_SMS, title, msgs[i].text);
      phonePlayNotify(1200, 120);
    }
    g_modem.deleteSms(msgs[i].index);
  }
}

static void modemSipTask(void* arg) {
  (void)arg;
  Serial.println("[MODEM] Init...");
  if (!g_modem.begin()) {
    Serial.println("[MODEM] UART AT failed — check wiring GPIO17/18");
  }
  if (!g_modem.waitReady(20000)) {
    Serial.println("[MODEM] Not responding");
  } else {
    Serial.println("[MODEM] AT OK");
  }

  if (g_settings.get().airplaneMode) {
    g_modem.setAirplaneMode(true);
    Serial.println("[MODEM] Airplane mode ON");
  }

  bool sim = g_modem.checkSim();
  statusLock();
  g_status.simReady = sim;
  statusUnlock();
  Serial.printf("[MODEM] SIM: %s\n", sim ? "READY" : "FAIL");

  if (!g_settings.get().airplaneMode) {
    for (int i = 0; i < 60; i++) {
      if (g_modem.checkRegistration()) break;
      vTaskDelay(pdMS_TO_TICKS(2000));
    }
  }
  int csq = 99;
  g_modem.checkSignal(csq);
  statusLock();
  g_status.registered = g_modem.isRegistered();
  g_status.csq = csq;
  g_status.signalBars = csqToBars(csq);
  statusUnlock();
  Serial.printf("[MODEM] Registered=%d CSQ=%d\n", g_modem.isRegistered(), csq);

  g_modem.smsInit();
  g_clock.syncFromModem();
  syncSmsInbox();

  if (!g_settings.get().airplaneMode && g_modem.ensureDataSession()) {
    char ip[32] = {0};
    g_modem.getIpAddress(ip, sizeof(ip));
    statusLock();
    g_status.pdpActive = true;
    strncpy(g_status.ipAddr, ip, sizeof(g_status.ipAddr) - 1);
    statusUnlock();
    Serial.printf("[MODEM] PDP IP=%s\n", ip);

    if (g_sip.begin()) {
      g_sip.onIncoming([](const char* from) { g_ui.notifyIncoming(from); });
      g_sip.onState([](CallState s) {
        if (s == CALL_RINGING || s == CALL_DIALING || s == CALL_IN_CALL)
          g_ui.showScreen(UI_CALL);
      });
      g_sip.registerAccount();
    }
  } else {
    Serial.println("[MODEM] Data session skipped/failed — SMS may still work");
  }

  uint32_t lastNetPoll = 0;
  uint32_t lastSmsPoll = 0;
  for (;;) {
    g_modem.pollUrc();
    if (!g_settings.get().airplaneMode) g_sip.loop();

    if (millis() - lastSmsPoll > 20000) {
      lastSmsPoll = millis();
      if (!g_settings.get().airplaneMode) syncSmsInbox();
    }

    if (millis() - lastNetPoll > 15000) {
      lastNetPoll = millis();
      if (!g_settings.get().airplaneMode) {
        int c = 99;
        if (g_modem.checkSignal(c)) {
          statusLock();
          g_status.csq = c;
          g_status.signalBars = csqToBars(c);
          g_status.registered = g_modem.isRegistered();
          g_status.sipRegistered = g_sip.isRegistered();
          statusUnlock();
        }
      }

      int pct = 0, mv = 0, chg = 0;
      if (g_modem.queryBattery(pct, mv, chg)) {
        statusLock();
        g_status.batteryPercent = pct;
        g_status.batteryMv = mv;
        g_status.chargeStatus = chg;
        if (pct <= 15 && !g_status.lowBatteryWarn) {
          g_status.lowBatteryWarn = true;
          statusUnlock();
          g_notifs.push(NOTIF_INFO, "Battery low", "Charge soon");
          phonePlayNotify(400, 300);
        } else {
          if (pct > 20) g_status.lowBatteryWarn = false;
          statusUnlock();
        }
      }
#if BATTERY_ADC_ENABLE
      else {
        int raw = analogRead(BATTERY_ADC_PIN);
        int adcMv = (int)((raw / 4095.0f) * 3300.0f * 2.0f);
        int adcPct =
            constrain(map(adcMv, BATTERY_EMPTY_MV, BATTERY_FULL_MV, 0, 100), 0,
                      100);
        statusLock();
        g_status.batteryPercent = adcPct;
        g_status.batteryMv = adcMv;
        statusUnlock();
      }
#endif
    }
    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

static void uiTask(void* arg) {
  (void)arg;
  uint32_t lastStatus = 0;
  for (;;) {
    KeyEvent ev;
    while (g_keyboard.popEvent(ev, 0)) {
      if (ev.pressed) g_ui.onKey(ev.code, ev.ascii, ev.shifted);
    }

    if (g_games.isActive()) g_games.tick();

    g_ui.loop();

    if (millis() - lastStatus > 500) {
      lastStatus = millis();
      PhoneStatus snap;
      statusLock();
      snap = g_status;
      statusUnlock();
      g_ui.updateStatusBar(snap);
      if (g_ui.current() == UI_CALL) {
        g_ui.setCallUi(snap.callState, snap.callerId, snap.callSeconds);
      }
      if (g_games.isActive()) {
        g_ui.onKey(KEY_NONE, 0, false);
      }
    }
    vTaskDelay(pdMS_TO_TICKS(5));
  }
}
