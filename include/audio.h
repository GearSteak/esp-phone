#pragma once

#include "Config.h"
#include <stddef.h>
#include <stdint.h>

class AudioPipeline {
 public:
  bool begin(int sampleRate = I2S_SAMPLE_RATE);
  void end();
  bool setSampleRate(int sampleRate);

  void startCallAudio();
  void stopCallAudio();
  bool isRunning() const { return running_; }
  int sampleRate() const { return sampleRate_; }

  size_t readMic(int16_t* pcm, size_t samples);
  size_t writeSpk(const int16_t* pcm, size_t samples);
  void playTestTone(uint32_t durationMs = 1000);
  void playTone(uint16_t freqHz, uint32_t durationMs, float amplitude = 8000.0f);

  static uint8_t linearToUlaw(int16_t sample);
  static int16_t ulawToLinear(uint8_t ulaw);
  static void encodePcmu(const int16_t* pcm, uint8_t* out, size_t n);
  static void decodePcmu(const uint8_t* in, int16_t* pcm, size_t n);

 private:
  bool running_ = false;
  bool installed_ = false;
  int sampleRate_ = I2S_SAMPLE_RATE;
};

extern AudioPipeline g_audio;
