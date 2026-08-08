#include "gps.h"
#include "modem.h"
#include <stdlib.h>
#include <string.h>

GpsService g_gps;

double GpsService::nmeaToDeg(const char* ddmm, char hemi) {
  if (!ddmm || !ddmm[0] || ddmm[0] == ',') return 0;
  double v = atof(ddmm);
  int deg = (int)(v / 100.0);
  double minutes = v - deg * 100.0;
  double dec = deg + minutes / 60.0;
  if (hemi == 'S' || hemi == 'W') dec = -dec;
  return dec;
}

bool GpsService::begin() {
  if (powered_) return true;
  String r;
  // Power GNSS — may take several seconds for READY
  if (!g_modem.sendAt("AT+CGNSSPWR=1", "OK", 15000, &r)) {
    // Some firmware returns READY asynchronously
    if (r.indexOf("READY") < 0 && r.indexOf("OK") < 0) {
      Serial.println("[GPS] CGNSSPWR failed — is GNSS antenna connected?");
      return false;
    }
  }
  delay(500);
  g_modem.sendAt("AT+CGNSSPORTSWITCH=0,1", "OK", 5000);  // NMEA/info on UART
  powered_ = true;
  Serial.println("[GPS] GNSS on — wait outdoors for fix (AT+CGPSINFO)");
  return true;
}

void GpsService::end() {
  if (!powered_) return;
  g_modem.sendAt("AT+CGNSSPWR=0", "OK", 5000);
  powered_ = false;
  fix_ = GpsFix{};
}

bool GpsService::parseCgpsInfo(const String& resp) {
  // +CGPSINFO: lat,N/S,lon,E/W,date,time,alt,speed,course
  int idx = resp.indexOf("+CGPSINFO:");
  if (idx < 0) return false;
  String payload = resp.substring(idx + 10);
  payload.trim();
  // Empty fields => no fix: +CGPSINFO:,,,,,,,,
  if (payload.startsWith(",,") || payload.length() < 8) {
    fix_.valid = false;
    return false;
  }

  char buf[160];
  strncpy(buf, payload.c_str(), sizeof(buf) - 1);
  buf[sizeof(buf) - 1] = 0;

  char* parts[10] = {};
  int n = 0;
  char* p = buf;
  parts[n++] = p;
  while (*p && n < 10) {
    if (*p == ',') {
      *p = 0;
      parts[n++] = p + 1;
    }
    p++;
  }

  if (!parts[0] || !parts[0][0]) {
    fix_.valid = false;
    return false;
  }

  char ns = parts[1] && parts[1][0] ? parts[1][0] : 'N';
  char ew = parts[3] && parts[3][0] ? parts[3][0] : 'E';
  fix_.lat = nmeaToDeg(parts[0], ns);
  fix_.lon = nmeaToDeg(parts[2], ew);
  if (parts[4]) strncpy(fix_.utcDate, parts[4], sizeof(fix_.utcDate) - 1);
  if (parts[5]) strncpy(fix_.utcTime, parts[5], sizeof(fix_.utcTime) - 1);
  fix_.altitudeM = parts[6] ? atof(parts[6]) : 0;
  fix_.speedKmh = parts[7] ? (float)(atof(parts[7]) * 1.852) : 0;  // knots→km/h often
  fix_.valid = (fix_.lat != 0.0 || fix_.lon != 0.0);
  fix_.ageMs = 0;
  return fix_.valid;
}

bool GpsService::poll() {
  if (!powered_) return false;
  if (millis() - lastPollMs_ < 2000) return fix_.valid;
  lastPollMs_ = millis();

  String r;
  if (!g_modem.sendAt("AT+CGPSINFO", "OK", 5000, &r)) return fix_.valid;
  bool ok = parseCgpsInfo(r);
  if (!ok) fix_.valid = false;
  return fix_.valid;
}

void GpsService::formatLatLon(char* buf, size_t len) const {
  if (!fix_.valid) {
    snprintf(buf, len, "No fix");
    return;
  }
  snprintf(buf, len, "%.5f, %.5f", fix_.lat, fix_.lon);
}
