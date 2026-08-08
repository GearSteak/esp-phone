#include "voice_recorder.h"
#include "audio.h"
#include "storage.h"
#include "media_player.h"
#include <string.h>
#include <stdio.h>

VoiceRecorder g_recorder;

void VoiceRecorder::writeWavHeader(uint32_t dataLen) {
  // 8 kHz, 16-bit mono PCM
  uint8_t hdr[44];
  memcpy(hdr, "RIFF", 4);
  uint32_t chunk = 36 + dataLen;
  memcpy(hdr + 4, &chunk, 4);
  memcpy(hdr + 8, "WAVEfmt ", 8);
  uint32_t sub1 = 16;
  memcpy(hdr + 16, &sub1, 4);
  uint16_t audioFmt = 1, ch = 1, bits = 16;
  uint32_t rate = 8000;
  uint32_t byteRate = rate * ch * bits / 8;
  uint16_t blockAlign = ch * bits / 8;
  memcpy(hdr + 20, &audioFmt, 2);
  memcpy(hdr + 22, &ch, 2);
  memcpy(hdr + 24, &rate, 4);
  memcpy(hdr + 28, &byteRate, 4);
  memcpy(hdr + 32, &blockAlign, 2);
  memcpy(hdr + 34, &bits, 2);
  memcpy(hdr + 36, "data", 4);
  memcpy(hdr + 40, &dataLen, 4);
  file_.seek(0);
  file_.write(hdr, 44);
}

bool VoiceRecorder::start() {
  if (recording_) stop();
  g_media.stop();
  Storage::fs().mkdir(VOICE_NOTES_DIR);
  snprintf(path_, sizeof(path_), "%s/VN_%lu.wav", VOICE_NOTES_DIR,
           (unsigned long)millis());
  file_ = Storage::fs().open(path_, FILE_WRITE);
  if (!file_) return false;
  uint8_t zeros[44] = {0};
  file_.write(zeros, 44);
  dataBytes_ = 0;
  if (!g_audio.begin(8000)) {
    file_.close();
    return false;
  }
  recording_ = true;
  startMs_ = millis();
  return true;
}

bool VoiceRecorder::pump() {
  if (!recording_) return false;
  int16_t frame[AUDIO_FRAME_SAMPLES];
  size_t n = g_audio.readMic(frame, AUDIO_FRAME_SAMPLES);
  if (n) {
    file_.write((uint8_t*)frame, n * sizeof(int16_t));
    dataBytes_ += n * sizeof(int16_t);
  }
  // Auto-stop at 60s
  if (millis() - startMs_ > 60000) stop();
  return recording_;
}

bool VoiceRecorder::stop() {
  if (!recording_) return false;
  recording_ = false;
  writeWavHeader(dataBytes_);
  file_.close();
  return true;
}

bool VoiceRecorder::playLast() {
  if (!path_[0]) return false;
  File f = Storage::fs().open(path_, FILE_READ);
  if (!f) return false;
  f.seek(44);
  g_media.stop();
  g_audio.begin(8000);
  int16_t frame[AUDIO_FRAME_SAMPLES];
  while (f.available()) {
    size_t got = f.read((uint8_t*)frame, sizeof(frame));
    if (got < 2) break;
    g_audio.writeSpk(frame, got / sizeof(int16_t));
  }
  f.close();
  return true;
}
