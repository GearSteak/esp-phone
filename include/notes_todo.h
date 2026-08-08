#pragma once

#include "Config.h"

static constexpr int NOTES_MAX = 16;
static constexpr int TODOS_MAX = 24;
static constexpr int NOTE_TITLE_LEN = 40;
static constexpr int NOTE_BODY_LEN = 320;
static constexpr int TODO_TEXT_LEN = 96;

struct NoteItem {
  char title[NOTE_TITLE_LEN];
  char body[NOTE_BODY_LEN];
};

struct TodoItem {
  char text[TODO_TEXT_LEN];
  bool done;
};

class NotesApp {
 public:
  bool load();
  bool save();
  int count() const { return count_; }
  NoteItem* items() { return items_; }
  const NoteItem* at(int i) const {
    return (i >= 0 && i < count_) ? &items_[i] : nullptr;
  }
  bool add(const char* title, const char* body);
  bool remove(int index);
  bool update(int index, const char* title, const char* body);

 private:
  NoteItem items_[NOTES_MAX];
  int count_ = 0;
};

class TodoApp {
 public:
  bool load();
  bool save();
  int count() const { return count_; }
  TodoItem* items() { return items_; }
  const TodoItem* at(int i) const {
    return (i >= 0 && i < count_) ? &items_[i] : nullptr;
  }
  bool add(const char* text);
  bool toggle(int index);
  bool remove(int index);

 private:
  TodoItem items_[TODOS_MAX];
  int count_ = 0;
};

extern NotesApp g_notes;
extern TodoApp g_todos;
