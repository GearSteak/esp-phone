#pragma once

#include "Config.h"
#include <stdint.h>

// Klondike solitaire — draw to RGB565 buffer; click via pointer coords
class Solitaire {
 public:
  static constexpr int FB_W = 304;
  static constexpr int FB_H = 400;

  void begin();  // new deal
  void stop();
  bool isActive() const { return active_; }
  void click(int x, int y);  // content-local coords
  void draw();
  const uint16_t* framebuffer() const { return fb_; }
  const char* status() const { return status_; }
  bool won() const { return won_; }

 private:
  bool active_ = false;
  bool won_ = false;
  uint16_t* fb_ = nullptr;
  char status_[48] = {0};

  // card: low 4 bits rank 1-13, next 2 suit 0-3, bit6 face-up
  static constexpr int MAX_PILE = 24;
  uint8_t stock_[52];
  int stockN_ = 0;
  uint8_t waste_[52];
  int wasteN_ = 0;
  uint8_t foundation_[4][13];
  int foundationN_[4] = {};
  uint8_t tableau_[7][MAX_PILE];
  int tableauN_[7] = {};

  int selFrom_ = -1;  // -1 none, 0-6 tableau, 7 waste, 8-11 foundation
  int selIdx_ = 0;    // index within tableau pile

  void allocFb();
  void freeFb();
  void shuffleDeal();
  void clearFb(uint16_t c);
  void putPixel(int x, int y, uint16_t c);
  void fillRect(int x, int y, int w, int h, uint16_t c);
  void drawCard(int x, int y, uint8_t card, bool selected);
  void drawBack(int x, int y);
  void updateStatus();
  bool canStackTableau(uint8_t moving, uint8_t onto) const;
  bool canStackFoundation(uint8_t moving, int f) const;
  bool moveToFoundation(uint8_t c, int f);
  void checkWin();
  int hitTest(int x, int y, int& outIdx) const;
};

extern Solitaire g_solitaire;
