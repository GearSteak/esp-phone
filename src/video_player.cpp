#include "video_player.h"
#include "storage.h"
#include <FS.h>
#include <string.h>
#include <stdlib.h>
#include "esp_heap_caps.h"
#include "img_converters.h"
#include "esp_jpg_decode.h"

VideoPlayer g_video;

struct JpgDecCtx {
  const uint8_t* input;
  uint8_t* out;
  size_t outCap;
  int width;
  int height;
};

static size_t jpg_read_cb(void* arg, size_t index, uint8_t* buf, size_t len) {
  JpgDecCtx* jpeg = (JpgDecCtx*)arg;
  if (buf && jpeg->input) memcpy(buf, jpeg->input + index, len);
  return len;
}

static bool jpg_write_cb(void* arg, uint16_t x, uint16_t y, uint16_t w,
                         uint16_t h, uint8_t* data) {
  JpgDecCtx* jpeg = (JpgDecCtx*)arg;
  if (!data) {
    if (x == 0 && y == 0) {
      jpeg->width = w;
      jpeg->height = h;
      if ((size_t)w * (size_t)h * 2 > jpeg->outCap) return false;
    }
    return true;
  }
  size_t jw = (size_t)jpeg->width * 3;
  size_t jw2 = (size_t)jpeg->width * 2;
  size_t t = (size_t)y * jw;
  size_t t2 = (size_t)y * jw2;
  size_t b = t + (size_t)h * jw;
  size_t l = (size_t)x * 2;
  uint8_t* out = jpeg->out;
  w = (uint16_t)(w * 3);
  for (size_t iy = t, iy2 = t2; iy < b; iy += jw, iy2 += jw2) {
    uint8_t* o = out + iy2 + l;
    for (size_t ix = 0, ix2 = 0; ix < w; ix += 3, ix2 += 2) {
      uint16_t r = data[ix];
      uint16_t g = data[ix + 1];
      uint16_t bb = data[ix + 2];
      uint16_t c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (bb >> 3);
      o[ix2 + 1] = (uint8_t)(c >> 8);
      o[ix2] = (uint8_t)(c & 0xff);
    }
    data += w;
  }
  return true;
}

bool VideoPlayer::open(const char* path) {
  close();
  if (!path || !path[0] || !Storage::sdReady()) return false;

  File* f = new File(Storage::fs().open(path, FILE_READ));
  if (!f || !*f) {
    delete f;
    return false;
  }

  jpegBuf_ = (uint8_t*)heap_caps_malloc(VIDEO_JPEG_MAX, MALLOC_CAP_SPIRAM);
  if (!jpegBuf_) jpegBuf_ = (uint8_t*)malloc(VIDEO_JPEG_MAX);
  frame_ = (uint16_t*)heap_caps_malloc(VIDEO_MAX_W * VIDEO_MAX_H * sizeof(uint16_t),
                                       MALLOC_CAP_SPIRAM);
  if (!frame_)
    frame_ = (uint16_t*)malloc(VIDEO_MAX_W * VIDEO_MAX_H * sizeof(uint16_t));
  if (!jpegBuf_ || !frame_) {
    close();
    delete f;
    return false;
  }

  file_ = f;
  strncpy(path_, path, sizeof(path_) - 1);
  path_[sizeof(path_) - 1] = 0;
  open_ = true;
  paused_ = false;
  nextFrameMs_ = 0;
  frameW_ = frameH_ = 0;
  return true;
}

void VideoPlayer::close() {
  open_ = false;
  paused_ = false;
  if (file_) {
    ((File*)file_)->close();
    delete (File*)file_;
    file_ = nullptr;
  }
  if (jpegBuf_) {
    free(jpegBuf_);
    jpegBuf_ = nullptr;
  }
  if (frame_) {
    free(frame_);
    frame_ = nullptr;
  }
  frameW_ = frameH_ = 0;
  path_[0] = 0;
}

void VideoPlayer::pause() { paused_ = true; }
void VideoPlayer::resume() {
  paused_ = false;
  nextFrameMs_ = millis();
}

bool VideoPlayer::readNextJpeg(size_t& lenOut) {
  lenOut = 0;
  if (!file_) return false;
  File& f = *(File*)file_;
  int prev = -1;
  int b;
  // Find SOI
  while ((b = f.read()) >= 0) {
    if (prev == 0xFF && b == 0xD8) {
      jpegBuf_[0] = 0xFF;
      jpegBuf_[1] = 0xD8;
      lenOut = 2;
      prev = b;
      break;
    }
    prev = b;
  }
  if (lenOut == 0) return false;
  while ((b = f.read()) >= 0 && lenOut < VIDEO_JPEG_MAX) {
    jpegBuf_[lenOut++] = (uint8_t)b;
    if (prev == 0xFF && b == 0xD9) return true;
    prev = b;
  }
  return false;
}

bool VideoPlayer::decodeJpeg(const uint8_t* jpg, size_t len) {
  JpgDecCtx ctx;
  ctx.input = jpg;
  ctx.out = (uint8_t*)frame_;
  ctx.outCap = VIDEO_MAX_W * VIDEO_MAX_H * 2;
  ctx.width = 0;
  ctx.height = 0;
  jpg_scale_t scale = JPG_SCALE_2X;
  if (esp_jpg_decode(len, scale, jpg_read_cb, jpg_write_cb, &ctx) != ESP_OK) {
    ctx.width = ctx.height = 0;
    if (esp_jpg_decode(len, JPG_SCALE_NONE, jpg_read_cb, jpg_write_cb, &ctx) !=
        ESP_OK)
      return false;
  }
  if (ctx.width <= 0 || ctx.height <= 0) return false;
  if (ctx.width > VIDEO_MAX_W || ctx.height > VIDEO_MAX_H) return false;
  frameW_ = ctx.width;
  frameH_ = ctx.height;
  return true;
}

bool VideoPlayer::tick() {
  if (!open_ || paused_ || !file_) return true;
  uint32_t now = millis();
  if (nextFrameMs_ && now < nextFrameMs_) return true;

  size_t len = 0;
  if (!readNextJpeg(len)) {
    // Loop
    File& f = *(File*)file_;
    f.seek(0);
    if (!readNextJpeg(len)) return false;
  }
  if (!decodeJpeg(jpegBuf_, len)) return true;  // skip bad frame
  nextFrameMs_ = millis() + VIDEO_FRAME_MS;
  return true;
}
