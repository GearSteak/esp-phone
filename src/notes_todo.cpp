#include "notes_todo.h"
#include "storage.h"
#include <ArduinoJson.h>
#include <string.h>

NotesApp g_notes;
TodoApp g_todos;

bool NotesApp::load() {
  count_ = 0;
  File f = Storage::fs().open("/notes.json", FILE_READ);
  if (!f) return true;  // empty OK
  JsonDocument doc;
  if (deserializeJson(doc, f)) {
    f.close();
    return false;
  }
  f.close();
  JsonArray arr = doc["notes"].as<JsonArray>();
  for (JsonObject o : arr) {
    if (count_ >= NOTES_MAX) break;
    strncpy(items_[count_].title, o["title"] | "Untitled", NOTE_TITLE_LEN - 1);
    strncpy(items_[count_].body, o["body"] | "", NOTE_BODY_LEN - 1);
    count_++;
  }
  return true;
}

bool NotesApp::save() {
  JsonDocument doc;
  JsonArray arr = doc["notes"].to<JsonArray>();
  for (int i = 0; i < count_; i++) {
    JsonObject o = arr.add<JsonObject>();
    o["title"] = items_[i].title;
    o["body"] = items_[i].body;
  }
  File f = Storage::fs().open("/notes.json", FILE_WRITE);
  if (!f) return false;
  serializeJson(doc, f);
  f.close();
  return true;
}

bool NotesApp::add(const char* title, const char* body) {
  if (count_ >= NOTES_MAX) return false;
  strncpy(items_[count_].title, title && title[0] ? title : "Untitled",
          NOTE_TITLE_LEN - 1);
  strncpy(items_[count_].body, body ? body : "", NOTE_BODY_LEN - 1);
  count_++;
  return save();
}

bool NotesApp::remove(int index) {
  if (index < 0 || index >= count_) return false;
  for (int i = index; i < count_ - 1; i++) items_[i] = items_[i + 1];
  count_--;
  return save();
}

bool NotesApp::update(int index, const char* title, const char* body) {
  if (index < 0 || index >= count_) return false;
  if (title) strncpy(items_[index].title, title, NOTE_TITLE_LEN - 1);
  if (body) strncpy(items_[index].body, body, NOTE_BODY_LEN - 1);
  return save();
}

bool TodoApp::load() {
  count_ = 0;
  File f = Storage::fs().open("/todos.json", FILE_READ);
  if (!f) return true;
  JsonDocument doc;
  if (deserializeJson(doc, f)) {
    f.close();
    return false;
  }
  f.close();
  JsonArray arr = doc["todos"].as<JsonArray>();
  for (JsonObject o : arr) {
    if (count_ >= TODOS_MAX) break;
    strncpy(items_[count_].text, o["text"] | "", TODO_TEXT_LEN - 1);
    items_[count_].done = o["done"] | false;
    count_++;
  }
  return true;
}

bool TodoApp::save() {
  JsonDocument doc;
  JsonArray arr = doc["todos"].to<JsonArray>();
  for (int i = 0; i < count_; i++) {
    JsonObject o = arr.add<JsonObject>();
    o["text"] = items_[i].text;
    o["done"] = items_[i].done;
  }
  File f = Storage::fs().open("/todos.json", FILE_WRITE);
  if (!f) return false;
  serializeJson(doc, f);
  f.close();
  return true;
}

bool TodoApp::add(const char* text) {
  if (count_ >= TODOS_MAX || !text || !text[0]) return false;
  strncpy(items_[count_].text, text, TODO_TEXT_LEN - 1);
  items_[count_].done = false;
  count_++;
  return save();
}

bool TodoApp::toggle(int index) {
  if (index < 0 || index >= count_) return false;
  items_[index].done = !items_[index].done;
  return save();
}

bool TodoApp::remove(int index) {
  if (index < 0 || index >= count_) return false;
  for (int i = index; i < count_ - 1; i++) items_[i] = items_[i + 1];
  count_--;
  return save();
}
