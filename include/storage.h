#pragma once

#include <stddef.h>
#include <stdint.h>
#include <FS.h>

namespace Storage {
bool begin();
bool sdReady();
const char* backendName();
fs::FS& fs();
void seedTemplates();  // folders + example wifi/email/ICS if missing

bool saveContactsJson(const char* json);
bool loadContactsJson(char* buf, size_t len);
bool appendSmsLog(const char* dir, const char* number, const char* text);
bool loadHighScores(int out[4]);
bool saveHighScores(const int scores[4]);
}  // namespace Storage
