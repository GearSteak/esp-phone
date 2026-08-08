#pragma once

#include "Config.h"
#include "storage.h"
#include <stdint.h>

// Simple 8 kHz mono WAV recorder → /voicenotes/
class VoiceRecorder {
 public:
  bool start();              // begin recording to a new file
  bool stop();               // finalize WAV
  bool isRecording() const { return recording_; }
  const char* lastPath() const { return path_; }
  // Call often while recording (~UI loop). Returns false if not recording.
  bool pump();
  bool playLast();           // play back last WAV via speaker (PCM loop)

 private:
  bool recording_ = false;
  File file_;
  char path_[64] = {0};
  uint32_t dataBytes_ = 0;
  uint32_t startMs_ = 0;
  void writeWavHeader(uint32_t dataLen);
};

extern VoiceRecorder g_recorder;
