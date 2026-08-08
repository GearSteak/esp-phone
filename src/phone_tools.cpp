#include "phone_tools.h"
#include "phone_data.h"
#include "modem.h"
#include "gps.h"
#include <ArduinoJson.h>
#include <WiFi.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <stdio.h>

static bool s_btOn = false;
static bool s_hsOn = false;

void connectivitySetHotspot(bool on) {
  if (on) {
    WiFi.mode(WIFI_AP);
    WiFi.softAP(g_settings.get().hotspotSsid, g_settings.get().hotspotPass);
    s_hsOn = true;
  } else {
    WiFi.softAPdisconnect(true);
    WiFi.mode(WIFI_OFF);
    s_hsOn = false;
  }
  g_settings.get().hotspotEnabled = on;
  g_settings.save();
}

void connectivitySetBluetooth(bool on) {
  // ESP32-S3 has BLE only — Classic SPP (BluetoothSerial) is not available.
  // Keep the preference for a future BLE headset stack.
  s_btOn = on;
  g_settings.get().btEnabled = on;
  g_settings.save();
  Serial.println(on ? "[BT] Pref ON (Classic BT unsupported on S3; BLE later)"
                    : "[BT] Pref OFF");
}

void connectivityApplyFromSettings() {
  if (g_settings.get().hotspotEnabled) connectivitySetHotspot(true);
  s_btOn = g_settings.get().btEnabled;
}

bool connectivityHotspotOn() { return s_hsOn; }
bool connectivityBluetoothOn() { return s_btOn; }

bool calcEval(const char* expr, double& out) {
  if (!expr || !expr[0]) return false;
  // Two-pass: left-associative + - * / with * / precedence
  char buf[96];
  strncpy(buf, expr, sizeof(buf) - 1);
  buf[sizeof(buf) - 1] = 0;
  // Strip spaces
  char* w = buf;
  for (char* r = buf; *r; r++)
    if (!isspace((unsigned char)*r)) *w++ = *r;
  *w = 0;

  double nums[16];
  char ops[16];
  int nc = 0, oc = 0;
  const char* p = buf;
  while (*p) {
    if (*p == '+' || *p == '-' || *p == '*' || *p == '/') {
      if (nc == 0 && (*p == '+' || *p == '-')) {
        // unary
        char* end = nullptr;
        nums[nc++] = strtod(p, &end);
        if (end == p) return false;
        p = end;
        continue;
      }
      if (oc >= 15 || nc == 0) return false;
      ops[oc++] = *p++;
      continue;
    }
    if (nc >= 16) return false;
    char* end = nullptr;
    nums[nc++] = strtod(p, &end);
    if (end == p) return false;
    p = end;
  }
  if (nc != oc + 1) return false;

  // First * /
  for (int i = 0; i < oc;) {
    if (ops[i] == '*' || ops[i] == '/') {
      if (ops[i] == '/' && fabs(nums[i + 1]) < 1e-15) return false;
      double v = (ops[i] == '*') ? nums[i] * nums[i + 1] : nums[i] / nums[i + 1];
      nums[i] = v;
      for (int j = i + 1; j < nc - 1; j++) nums[j] = nums[j + 1];
      for (int j = i; j < oc - 1; j++) ops[j] = ops[j + 1];
      nc--;
      oc--;
    } else {
      i++;
    }
  }
  double acc = nums[0];
  for (int i = 0; i < oc; i++) {
    if (ops[i] == '+') acc += nums[i + 1];
    else if (ops[i] == '-') acc -= nums[i + 1];
    else return false;
  }
  out = acc;
  return true;
}

static const char* kLen[] = {"m", "km", "mi", "ft", "in"};
static const double kLenToM[] = {1.0, 1000.0, 1609.344, 0.3048, 0.0254};
static const char* kMass[] = {"kg", "g", "lb", "oz"};
static const double kMassToKg[] = {1.0, 0.001, 0.45359237, 0.028349523125};
static const char* kTemp[] = {"C", "F", "K"};
// currency ~approx USD multipliers (offline tables; update as needed)
static const char* kCur[] = {"USD", "CAD", "EUR", "GBP", "JPY"};
static const double kCurToUsd[] = {1.0, 0.74, 1.08, 1.27, 0.0067};

int converterCategoryCount() { return 4; }

const char* converterCategoryName(int cat) {
  switch (cat) {
    case 0: return "Length";
    case 1: return "Mass";
    case 2: return "Temp";
    case 3: return "Currency";
    default: return "?";
  }
}

int converterUnitCount(int cat) {
  switch (cat) {
    case 0: return 5;
    case 1: return 4;
    case 2: return 3;
    case 3: return 5;
    default: return 0;
  }
}

const char* converterUnitName(int cat, int unit) {
  switch (cat) {
    case 0: return (unit >= 0 && unit < 5) ? kLen[unit] : "?";
    case 1: return (unit >= 0 && unit < 4) ? kMass[unit] : "?";
    case 2: return (unit >= 0 && unit < 3) ? kTemp[unit] : "?";
    case 3: return (unit >= 0 && unit < 5) ? kCur[unit] : "?";
    default: return "?";
  }
}

bool converterConvert(int cat, int from, int to, double value, double& out) {
  if (from < 0 || to < 0 || from >= converterUnitCount(cat) ||
      to >= converterUnitCount(cat))
    return false;
  if (cat == 0) {
    double m = value * kLenToM[from];
    out = m / kLenToM[to];
    return true;
  }
  if (cat == 1) {
    double kg = value * kMassToKg[from];
    out = kg / kMassToKg[to];
    return true;
  }
  if (cat == 2) {
    double c = value;
    if (from == 1) c = (value - 32.0) * 5.0 / 9.0;
    else if (from == 2) c = value - 273.15;
    if (to == 0) out = c;
    else if (to == 1) out = c * 9.0 / 5.0 + 32.0;
    else out = c + 273.15;
    return true;
  }
  if (cat == 3) {
    double usd = value * kCurToUsd[from];
    out = usd / kCurToUsd[to];
    return true;
  }
  return false;
}

const char* weatherCodeText(int code) {
  if (code == 0) return "Clear";
  if (code <= 3) return "Cloudy";
  if (code <= 48) return "Fog";
  if (code <= 57) return "Drizzle";
  if (code <= 67) return "Rain";
  if (code <= 77) return "Snow";
  if (code <= 82) return "Showers";
  if (code <= 86) return "Snow show.";
  if (code <= 99) return "Thunder";
  return "Unknown";
}

bool weatherFetchOpenMeteo(double lat, double lon) {
  char url[220];
  snprintf(url, sizeof(url),
           "https://api.open-meteo.com/v1/forecast?latitude=%.4f&longitude=%.4f"
           "&current=temperature_2m,weather_code",
           lat, lon);
  char body[768];
  int status = 0;
  if (!g_modem.httpGet(url, body, sizeof(body), &status)) {
    strncpy(g_weather.summary, "Fetch failed", sizeof(g_weather.summary) - 1);
    g_weather.valid = false;
    return false;
  }
  JsonDocument doc;
  if (deserializeJson(doc, body)) {
    strncpy(g_weather.summary, "Bad JSON", sizeof(g_weather.summary) - 1);
    return false;
  }
  JsonObject cur = doc["current"];
  g_weather.tempC = cur["temperature_2m"] | 0.0f;
  g_weather.code = cur["weather_code"] | 0;
  snprintf(g_weather.summary, sizeof(g_weather.summary), "%.1f C  %s",
           g_weather.tempC, weatherCodeText(g_weather.code));
  g_weather.valid = true;
  g_weather.fetchedMs = millis();
  return true;
}
