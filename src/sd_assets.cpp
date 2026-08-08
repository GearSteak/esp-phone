#include "sd_assets.h"
#include "storage.h"
#include <string.h>
#include <strings.h>
#include <stdlib.h>
#include <stdio.h>
#include "esp_heap_caps.h"
#include "img_converters.h"
#include "esp_jpg_decode.h"

#if UI_SD_ASSETS

struct LoadedImg {
  char id[32];
  lv_img_dsc_t dsc;
  uint8_t* pixels;
  bool used;
};

static constexpr int MAX_ICONS = 40;
static constexpr int MAX_STATUS = 16;
static LoadedImg icons_[MAX_ICONS];
static LoadedImg status_[MAX_STATUS];
static LoadedImg wallpaper_;
static int iconCount_ = 0;
static int statusCount_ = 0;

struct JpgCtx {
  const uint8_t* input;
  uint8_t* out;
  size_t outCap;
  int width;
  int height;
};

static size_t jpg_read(void* arg, size_t index, uint8_t* buf, size_t len) {
  JpgCtx* j = (JpgCtx*)arg;
  if (buf && j->input) memcpy(buf, j->input + index, len);
  return len;
}

static bool jpg_write(void* arg, uint16_t x, uint16_t y, uint16_t w, uint16_t h,
                      uint8_t* data) {
  JpgCtx* jpeg = (JpgCtx*)arg;
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

static bool loadJpegFile(const char* path, LoadedImg& out, int maxW, int maxH) {
  memset(&out, 0, sizeof(out));
  if (!Storage::sdReady()) return false;
  File f = Storage::fs().open(path, FILE_READ);
  if (!f) return false;
  size_t len = f.size();
  if (len < 32 || len > 400 * 1024) {
    f.close();
    return false;
  }
  uint8_t* jpg = (uint8_t*)heap_caps_malloc(len, MALLOC_CAP_SPIRAM);
  if (!jpg) jpg = (uint8_t*)malloc(len);
  if (!jpg) {
    f.close();
    return false;
  }
  if (f.read(jpg, len) != (int)len) {
    free(jpg);
    f.close();
    return false;
  }
  f.close();

  size_t pixCap = (size_t)maxW * (size_t)maxH * 2;
  uint8_t* pix = (uint8_t*)heap_caps_malloc(pixCap, MALLOC_CAP_SPIRAM);
  if (!pix) pix = (uint8_t*)malloc(pixCap);
  if (!pix) {
    free(jpg);
    return false;
  }

  JpgCtx ctx{jpg, pix, pixCap, 0, 0};
  if (esp_jpg_decode(len, JPG_SCALE_NONE, jpg_read, jpg_write, &ctx) != ESP_OK ||
      ctx.width <= 0 || ctx.height <= 0 || ctx.width > maxW ||
      ctx.height > maxH) {
    free(jpg);
    free(pix);
    return false;
  }
  free(jpg);

  out.pixels = pix;
  out.dsc.header.always_zero = 0;
  out.dsc.header.w = ctx.width;
  out.dsc.header.h = ctx.height;
  out.dsc.header.cf = LV_IMG_CF_TRUE_COLOR;
  out.dsc.data_size = (uint32_t)ctx.width * ctx.height * 2;
  out.dsc.data = pix;
  out.used = true;
  return true;
}

static void loadDirIcons(const char* dir, LoadedImg* tab, int maxN, int& count,
                         int maxW, int maxH) {
  count = 0;
  if (!Storage::sdReady()) return;
  File root = Storage::fs().open(dir);
  if (!root || !root.isDirectory()) return;
  File f = root.openNextFile();
  while (f && count < maxN) {
    if (!f.isDirectory()) {
      const char* name = f.name();
      const char* base = strrchr(name, '/');
      base = base ? base + 1 : name;
      size_t n = strlen(base);
      if (n > 4 && (strcasecmp(base + n - 4, ".jpg") == 0 ||
                    strcasecmp(base + n - 5, ".jpeg") == 0)) {
        char path[96];
        if (name[0] == '/')
          strncpy(path, name, sizeof(path) - 1);
        else
          snprintf(path, sizeof(path), "%s/%s", dir, base);
        path[sizeof(path) - 1] = 0;
        if (loadJpegFile(path, tab[count], maxW, maxH)) {
          // id = filename without extension
          strncpy(tab[count].id, base, sizeof(tab[count].id) - 1);
          char* dot = strrchr(tab[count].id, '.');
          if (dot) *dot = 0;
          Serial.printf("[UI] SD asset %s (%dx%d)\n", path, tab[count].dsc.header.w,
                        tab[count].dsc.header.h);
          count++;
        }
      }
    }
    f = root.openNextFile();
  }
  root.close();
}

static void ensureUiDirs() {
  if (!Storage::sdReady()) return;
  auto mk = [](const char* p) {
    if (!Storage::fs().exists(p)) Storage::fs().mkdir(p);
  };
  mk("/ui");
  mk(UI_ICON_DIR);
  mk(UI_STATUS_DIR);
}

namespace SdAssets {

bool begin() {
#if !UI_SD_ASSETS
  return false;
#else
  ensureUiDirs();
  iconCount_ = statusCount_ = 0;
  memset(&wallpaper_, 0, sizeof(wallpaper_));
  loadDirIcons(UI_ICON_DIR, icons_, MAX_ICONS, iconCount_, 64, 64);
  loadDirIcons(UI_STATUS_DIR, status_, MAX_STATUS, statusCount_, 48, 48);
  if (loadJpegFile(UI_WALLPAPER_PATH, wallpaper_, TFT_WIDTH_PX, TFT_HEIGHT_PX)) {
    Serial.println("[UI] SD wallpaper loaded");
  }
  Serial.printf("[UI] SD assets: %d icons, %d status\n", iconCount_, statusCount_);
  return true;
#endif
}

const lv_img_dsc_t* iconById(const char* id) {
  if (!id) return nullptr;
  for (int i = 0; i < iconCount_; i++) {
    if (icons_[i].used && strcmp(icons_[i].id, id) == 0) return &icons_[i].dsc;
  }
  return nullptr;
}

const lv_img_dsc_t* statusById(const char* id) {
  if (!id) return nullptr;
  for (int i = 0; i < statusCount_; i++) {
    if (status_[i].used && strcmp(status_[i].id, id) == 0)
      return &status_[i].dsc;
  }
  return nullptr;
}

const lv_img_dsc_t* wallpaper() {
  return wallpaper_.used ? &wallpaper_.dsc : nullptr;
}

}  // namespace SdAssets

#else  // !UI_SD_ASSETS

namespace SdAssets {
bool begin() { return false; }
const lv_img_dsc_t* iconById(const char*) { return nullptr; }
const lv_img_dsc_t* statusById(const char*) { return nullptr; }
const lv_img_dsc_t* wallpaper() { return nullptr; }
}  // namespace SdAssets

#endif
