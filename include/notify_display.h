#pragma once

// Heltec Tracker ST7735 — notification panel for Digivice (Pi owns main UI).

namespace NotifyDisplay {

bool begin();
void loop();  // idle clock / auto-clear

/** Show alert; title/body truncated to fit 160×80. */
void show(const char* title, const char* body, const char* kind = "info");

void clear();
void setIdleStatus(const char* line);  // bottom status when idle

}  // namespace NotifyDisplay
