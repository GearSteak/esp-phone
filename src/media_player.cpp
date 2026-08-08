#include "media_player.h"
#include "audio.h"
#include "storage.h"
#include <AudioFileSourceFS.h>
#include <AudioGeneratorMP3.h>
#include <AudioOutputI2S.h>
#include <string.h>
#include <ctype.h>

MediaPlayer g_media;

static bool endsWithCI(const char* name, const char* ext) {
  size_t n = strlen(name), e = strlen(ext);
  if (n < e) return false;
  for (size_t i = 0; i < e; i++) {
    if (tolower((unsigned char)name[n - e + i]) !=
        tolower((unsigned char)ext[i]))
      return false;
  }
  return true;
}

bool MediaPlayer::begin() { return true; }

int MediaPlayer::listFiles(const char* dir, char out[][MEDIA_PATH_LEN],
                           int maxFiles, const char* ext) {
  int count = 0;
  if (!Storage::sdReady()) return 0;
  File root = Storage::fs().open(dir);
  if (!root || !root.isDirectory()) return 0;
  File f = root.openNextFile();
  while (f && count < maxFiles) {
    if (!f.isDirectory()) {
      const char* name = f.name();
      const char* base = strrchr(name, '/');
      base = base ? base + 1 : name;
      if (endsWithCI(base, ext)) {
        if (name[0] == '/')
          strncpy(out[count], name, MEDIA_PATH_LEN - 1);
        else
          snprintf(out[count], MEDIA_PATH_LEN, "%s/%s", dir, base);
        out[count][MEDIA_PATH_LEN - 1] = 0;
        count++;
      }
    }
    f = root.openNextFile();
  }
  root.close();
  return count;
}

void MediaPlayer::teardownDecoder() {
  if (decoder_) {
    auto* g = (AudioGeneratorMP3*)decoder_;
    if (g->isRunning()) g->stop();
    delete g;
    decoder_ = nullptr;
  }
  if (file_) {
    delete (AudioFileSource*)file_;
    file_ = nullptr;
  }
  if (out_) {
    delete (AudioOutputI2S*)out_;
    out_ = nullptr;
  }
  playing_ = false;
  paused_ = false;
  g_audio.begin(I2S_SAMPLE_RATE);
}

bool MediaPlayer::play(const char* path, MediaMode mode) {
  if (!path || !path[0] || !Storage::sdReady()) return false;
  stop();

  g_audio.end();

  auto* i2s = new AudioOutputI2S(I2S_PORT_NUM, AudioOutputI2S::EXTERNAL_I2S);
  i2s->SetPinout(I2S_BCLK, I2S_LRCK, I2S_DOUT);
  i2s->SetGain(0.5f);

  auto* src = new AudioFileSourceFS(Storage::fs(), path);
  auto* mp3 = new AudioGeneratorMP3();

  if (!mp3->begin(src, i2s)) {
    delete mp3;
    delete src;
    delete i2s;
    g_audio.begin(I2S_SAMPLE_RATE);
    Serial.println("[MEDIA] MP3 begin failed");
    return false;
  }

  decoder_ = mp3;
  file_ = src;
  out_ = i2s;
  mode_ = mode;
  playing_ = true;
  paused_ = false;
  positionSec_ = 0;
  lastTickMs_ = millis();
  strncpy(currentPath_, path, sizeof(currentPath_) - 1);

  if (mode == MEDIA_AUDIOBOOK) {
    uint32_t bookmark = 0;
    if (loadBookmark(path, bookmark) && bookmark > 0) {
      Serial.printf("[MEDIA] bookmark %u s\n", (unsigned)bookmark);
      positionSec_ = bookmark;
    }
  }
  Serial.printf("[MEDIA] playing %s\n", path);
  return true;
}

void MediaPlayer::pause() {
  if (playing_) paused_ = true;
}

void MediaPlayer::resume() {
  if (playing_) paused_ = false;
}

void MediaPlayer::stop() {
  if (mode_ == MEDIA_AUDIOBOOK && currentPath_[0]) {
    saveBookmark(currentPath_, positionSec_);
  }
  teardownDecoder();
  mode_ = MEDIA_IDLE;
  currentPath_[0] = 0;
  positionSec_ = 0;
}

void MediaPlayer::loop() {
  if (!playing_ || paused_ || !decoder_) return;
  auto* g = (AudioGeneratorMP3*)decoder_;
  if (!g->loop()) {
    if (mode_ == MEDIA_AUDIOBOOK && currentPath_[0]) {
      saveBookmark(currentPath_, 0);
    }
    teardownDecoder();
    mode_ = MEDIA_IDLE;
    currentPath_[0] = 0;
    return;
  }
  uint32_t now = millis();
  if (now - lastTickMs_ >= 1000) {
    positionSec_ += (now - lastTickMs_) / 1000;
    lastTickMs_ = now;
    if (mode_ == MEDIA_AUDIOBOOK && (positionSec_ % 15 == 0)) {
      saveBookmark(currentPath_, positionSec_);
    }
  }
}

bool MediaPlayer::loadBookmark(const char* path, uint32_t& secondsOut) {
  secondsOut = 0;
  if (!Storage::sdReady() || !path) return false;
  uint32_t h = 2166136261u;
  for (const char* p = path; *p; p++) {
    h ^= (uint8_t)*p;
    h *= 16777619u;
  }
  char key[64];
  snprintf(key, sizeof(key), "%s/.progress/%08x.txt", AUDIOBOOK_DIR,
           (unsigned)h);
  File f = Storage::fs().open(key, FILE_READ);
  if (!f) return false;
  String s = f.readString();
  f.close();
  secondsOut = (uint32_t)s.toInt();
  return true;
}

bool MediaPlayer::saveBookmark(const char* path, uint32_t seconds) {
  if (!Storage::sdReady() || !path) return false;
  char dir[48];
  snprintf(dir, sizeof(dir), "%s/.progress", AUDIOBOOK_DIR);
  Storage::fs().mkdir(AUDIOBOOK_DIR);
  Storage::fs().mkdir(dir);
  uint32_t h = 2166136261u;
  for (const char* p = path; *p; p++) {
    h ^= (uint8_t)*p;
    h *= 16777619u;
  }
  char key[64];
  snprintf(key, sizeof(key), "%s/%08x.txt", dir, (unsigned)h);
  File f = Storage::fs().open(key, FILE_WRITE);
  if (!f) return false;
  f.printf("%u\n", (unsigned)seconds);
  f.close();
  return true;
}
