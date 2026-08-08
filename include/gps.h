#pragma once

#include "Config.h"

struct GpsFix {
  bool valid = false;
  double lat = 0;
  double lon = 0;
  float altitudeM = 0;
  float speedKmh = 0;
  char utcTime[16] = {0};   // HHMMSS
  char utcDate[16] = {0};   // DDMMYY
  uint32_t ageMs = 0;
};

class GpsService {
 public:
  bool begin();             // power on GNSS (needs GNSS antenna on IPEX)
  void end();
  bool isOn() const { return powered_; }
  bool poll();              // query AT+CGPSINFO; returns true if fix valid
  const GpsFix& fix() const { return fix_; }
  void formatLatLon(char* buf, size_t len) const;

 private:
  bool powered_ = false;
  GpsFix fix_;
  uint32_t lastPollMs_ = 0;
  bool parseCgpsInfo(const String& resp);
  static double nmeaToDeg(const char* ddmm, char hemi);
};

extern GpsService g_gps;
