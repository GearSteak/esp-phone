#include "camera_app.h"
#include "storage.h"
#include "keyboard.h"
#include "audio.h"
#include <esp_camera.h>
#include <string.h>
#include <stdlib.h>

CameraApp g_camera;

bool CameraApp::begin() {
  if (active_) return true;

  g_keyboard.pauseForCamera();
  g_audio.end();

  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = CAM_Y2;
  config.pin_d1 = CAM_Y3;
  config.pin_d2 = CAM_Y4;
  config.pin_d3 = CAM_Y5;
  config.pin_d4 = CAM_Y6;
  config.pin_d5 = CAM_Y7;
  config.pin_d6 = CAM_Y8;
  config.pin_d7 = CAM_Y9;
  config.pin_xclk = CAM_XCLK;
  config.pin_pclk = CAM_PCLK;
  config.pin_vsync = CAM_VSYNC;
  config.pin_href = CAM_HREF;
  config.pin_sccb_sda = CAM_SIOD;
  config.pin_sccb_scl = CAM_SIOC;
  config.pin_pwdn = CAM_PWDN;
  config.pin_reset = CAM_RESET;
  config.xclk_freq_hz = CAM_XCLK_FREQ_HZ;
  config.frame_size = FRAMESIZE_QVGA;
  config.pixel_format = PIXFORMAT_RGB565;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = CAM_JPEG_QUALITY;
  config.fb_count = 2;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAM] init failed: 0x%x (CAM DIP + OV2640 FPC)\n",
                  (unsigned)err);
    g_keyboard.resumeAfterCamera();
    g_audio.begin(I2S_SAMPLE_RATE);
    return false;
  }
  sensor_t* s = esp_camera_sensor_get();
  if (s) {
    s->set_framesize(s, FRAMESIZE_QVGA);
    s->set_vflip(s, 1);
  }
  active_ = true;
  Serial.println("[CAM] ready — Snap=GPIO1 Back=GPIO42");
  return true;
}

void CameraApp::end() {
  if (!active_) return;
  esp_camera_deinit();
  active_ = false;
  g_keyboard.resumeAfterCamera();
  g_audio.begin(I2S_SAMPLE_RATE);
  Serial.println("[CAM] released");
}

bool CameraApp::captureRgb565(uint16_t* buf, int maxW, int maxH, int* outW,
                              int* outH) {
  if (!active_ || !buf) return false;
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) return false;

  int w = fb->width;
  int h = fb->height;
  if (w > maxW) w = maxW;
  if (h > maxH) h = maxH;

  if (fb->format == PIXFORMAT_RGB565) {
    const uint16_t* src = (const uint16_t*)fb->buf;
    for (int y = 0; y < h; y++) {
      memcpy(buf + y * maxW, src + y * fb->width, w * sizeof(uint16_t));
    }
  } else {
    esp_camera_fb_return(fb);
    return false;
  }
  if (outW) *outW = w;
  if (outH) *outH = h;
  esp_camera_fb_return(fb);
  return true;
}

bool CameraApp::saveJpeg(char* pathOut, size_t pathLen) {
  if (!active_) return false;
  if (!Storage::sdReady()) return false;

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) return false;

  uint8_t* jpg = nullptr;
  size_t jpgLen = 0;
  bool ok = false;

  if (fb->format == PIXFORMAT_JPEG) {
    jpg = fb->buf;
    jpgLen = fb->len;
    ok = true;
  } else {
    ok = frame2jpg(fb, CAM_JPEG_QUALITY, &jpg, &jpgLen);
  }

  if (!ok || !jpg) {
    esp_camera_fb_return(fb);
    return false;
  }

  Storage::fs().mkdir(CAM_PHOTOS_DIR);
  char path[64];
  snprintf(path, sizeof(path), "%s/IMG_%lu.jpg", CAM_PHOTOS_DIR,
           (unsigned long)millis());
  File f = Storage::fs().open(path, FILE_WRITE);
  if (!f) {
    if (fb->format != PIXFORMAT_JPEG) free(jpg);
    esp_camera_fb_return(fb);
    return false;
  }
  f.write(jpg, jpgLen);
  f.close();
  Serial.printf("[CAM] saved %s\n", path);

  if (pathOut && pathLen) {
    strncpy(pathOut, path, pathLen - 1);
    pathOut[pathLen - 1] = 0;
  }

  if (fb->format != PIXFORMAT_JPEG) free(jpg);
  esp_camera_fb_return(fb);
  return true;
}

bool CameraApp::captureJpeg(uint8_t** outJpg, size_t* outLen) {
  if (!active_ || !outJpg || !outLen) return false;
  *outJpg = nullptr;
  *outLen = 0;

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) return false;

  uint8_t* jpg = nullptr;
  size_t jpgLen = 0;
  bool ok = false;

  if (fb->format == PIXFORMAT_JPEG) {
    jpg = (uint8_t*)malloc(fb->len);
    if (jpg) {
      memcpy(jpg, fb->buf, fb->len);
      jpgLen = fb->len;
      ok = true;
    }
  } else {
    ok = frame2jpg(fb, CAM_JPEG_QUALITY, &jpg, &jpgLen);
  }
  esp_camera_fb_return(fb);
  if (!ok || !jpg) return false;
  *outJpg = jpg;
  *outLen = jpgLen;
  return true;
}
