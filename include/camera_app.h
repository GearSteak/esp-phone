#pragma once

#include "Config.h"
#include <stddef.h>
#include <stdint.h>

class CameraApp {
 public:
  bool begin();
  void end();
  bool isActive() const { return active_; }

  // Grab one RGB565 frame into buf (w*h*2 bytes). Returns false on fail.
  bool captureRgb565(uint16_t* buf, int maxW, int maxH, int* outW, int* outH);

  // Save JPEG snapshot to SD under /photos. pathOut optional.
  bool saveJpeg(char* pathOut = nullptr, size_t pathLen = 0);

  // Capture JPEG into heap buffer (caller must free(*outJpg)). For USB transfer.
  bool captureJpeg(uint8_t** outJpg, size_t* outLen);

 private:
  bool active_ = false;
};

extern CameraApp g_camera;
