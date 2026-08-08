#include "ebook.h"
#include "storage.h"
#include <string.h>
#include <ctype.h>

EbookReader g_ebook;

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

int EbookReader::listBooks(char out[][MEDIA_PATH_LEN], int maxFiles) {
  int count = 0;
  if (!Storage::sdReady()) return 0;
  File root = Storage::fs().open(EBOOK_DIR);
  if (!root || !root.isDirectory()) return 0;
  File f = root.openNextFile();
  while (f && count < maxFiles) {
    if (!f.isDirectory()) {
      const char* name = f.name();
      const char* base = strrchr(name, '/');
      base = base ? base + 1 : name;
      if (endsWithCI(base, ".txt")) {
        if (name[0] == '/')
          strncpy(out[count], name, MEDIA_PATH_LEN - 1);
        else
          snprintf(out[count], MEDIA_PATH_LEN, "%s/%s", EBOOK_DIR, base);
        out[count][MEDIA_PATH_LEN - 1] = 0;
        count++;
      }
    }
    f = root.openNextFile();
  }
  root.close();
  return count;
}

bool EbookReader::open(const char* path) {
  close();
  if (!Storage::sdReady() || !path) return false;
  File f = Storage::fs().open(path, FILE_READ);
  if (!f) return false;
  fileSize_ = f.size();
  f.close();
  strncpy(path_, path, sizeof(path_) - 1);
  pages_ = (int)((fileSize_ + EBOOK_PAGE_CHARS - 1) / EBOOK_PAGE_CHARS);
  if (pages_ < 1) pages_ = 1;
  page_ = 0;
  open_ = true;
  return true;
}

void EbookReader::close() {
  open_ = false;
  path_[0] = 0;
  page_ = 0;
  pages_ = 0;
  fileSize_ = 0;
}

bool EbookReader::pageText(char* buf, size_t buflen) {
  if (!open_ || !buf || buflen < 2) return false;
  File f = Storage::fs().open(path_, FILE_READ);
  if (!f) return false;
  size_t offset = (size_t)page_ * EBOOK_PAGE_CHARS;
  if (!f.seek(offset)) {
    f.close();
    return false;
  }
  size_t n = f.readBytes(buf, buflen - 1);
  buf[n] = 0;
  f.close();
  return true;
}

bool EbookReader::nextPage() {
  if (!open_ || page_ + 1 >= pages_) return false;
  page_++;
  return true;
}

bool EbookReader::prevPage() {
  if (!open_ || page_ <= 0) return false;
  page_--;
  return true;
}
