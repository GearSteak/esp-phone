#pragma once

#include "Config.h"

enum MediaMode : uint8_t {
  MEDIA_IDLE = 0,
  MEDIA_MUSIC,
  MEDIA_AUDIOBOOK,
};

class MediaPlayer {
 public:
  bool begin();
  void loop();  // call from UI/media task

  int listFiles(const char* dir, char out[][MEDIA_PATH_LEN], int maxFiles,
                const char* ext /* e.g. ".mp3" */);

  bool play(const char* path, MediaMode mode);
  void pause();
  void resume();
  void stop();
  bool isPlaying() const { return playing_ && !paused_; }
  bool isPaused() const { return paused_; }
  MediaMode mode() const { return mode_; }
  const char* currentPath() const { return currentPath_; }

  // Audiobook progress (seconds) — stored under /audiobooks/.progress/
  bool loadBookmark(const char* path, uint32_t& secondsOut);
  bool saveBookmark(const char* path, uint32_t seconds);

  uint32_t positionSec() const { return positionSec_; }

 private:
  MediaMode mode_ = MEDIA_IDLE;
  bool playing_ = false;
  bool paused_ = false;
  char currentPath_[MEDIA_PATH_LEN] = {0};
  uint32_t positionSec_ = 0;
  uint32_t lastTickMs_ = 0;
  void* decoder_ = nullptr;  // AudioGeneratorMP3*
  void* file_ = nullptr;     // AudioFileSource*
  void* out_ = nullptr;      // AudioOutputI2S*

  void teardownDecoder();
};

extern MediaPlayer g_media;
