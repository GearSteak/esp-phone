#pragma once

#include "Config.h"

class EbookReader {
 public:
  int listBooks(char out[][MEDIA_PATH_LEN], int maxFiles);
  bool open(const char* path);
  void close();
  bool isOpen() const { return open_; }
  const char* path() const { return path_; }

  // Fill buf with current page text (null-terminated).
  bool pageText(char* buf, size_t buflen);
  bool nextPage();
  bool prevPage();
  int pageIndex() const { return page_; }
  int pageCount() const { return pages_; }

 private:
  bool open_ = false;
  char path_[MEDIA_PATH_LEN] = {0};
  int page_ = 0;
  int pages_ = 0;
  size_t fileSize_ = 0;
};

extern EbookReader g_ebook;
