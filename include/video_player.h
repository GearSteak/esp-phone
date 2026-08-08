#pragma once

#include "Config.h"
#include <stdint.h>

#ifndef VIDEO_DIR
#define VIDEO_DIR "/videos"
#endif
#ifndef VIDEO_MAX_W
#define VIDEO_MAX_W 320
#endif
#ifndef VIDEO_MAX_H
#define VIDEO_MAX_H 240
#endif
#ifndef VIDEO_FRAME_MS
#define VIDEO_FRAME_MS 90
#endif
#ifndef VIDEO_JPEG_MAX
#define VIDEO_JPEG_MAX (48 * 1024)
#endif

class VideoPlayer {
 public:
  bool open(const char* path);
  void close();
  void pause();
  void resume();
  bool isOpen() const { return open_; }
  bool isPlaying() const { return open_ && !paused_; }
  bool isPaused() const { return paused_; }
  // Decode next frame when due; returns false when stream ends (then loops).
  bool tick();
  const uint16_t* frameRgb565() const { return frame_; }
  int frameW() const { return frameW_; }
  int frameH() const { return frameH_; }
  const char* path() const { return path_; }

 private:
  bool open_ = false;
  bool paused_ = false;
  char path_[MEDIA_PATH_LEN] = {0};
  void* file_ = nullptr;  // File* heap
  uint8_t* jpegBuf_ = nullptr;
  uint16_t* frame_ = nullptr;
  int frameW_ = 0;
  int frameH_ = 0;
  uint32_t nextFrameMs_ = 0;

  bool readNextJpeg(size_t& lenOut);
  bool decodeJpeg(const uint8_t* jpg, size_t len);
};

extern VideoPlayer g_video;
