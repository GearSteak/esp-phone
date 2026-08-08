#pragma once

#include "Config.h"
#include <stdint.h>

// Uno vs one AI — pointer to play; Confirm = click
class UnoGame {
 public:
  static constexpr int FB_W = 304;
  static constexpr int FB_H = 400;

  void begin();
  void stop();
  bool isActive() const { return active_; }
  void click(int x, int y);
  void draw();
  void tick();  // AI turns
  const uint16_t* framebuffer() const { return fb_; }
  const char* status() const { return status_; }
  bool gameOver() const { return over_; }

 private:
  bool active_ = false;
  bool over_ = false;
  bool playerTurn_ = true;
  bool waitingColor_ = false;  // after wild
  uint8_t wildColor_ = 0;
  int direction_ = 1;
  uint16_t* fb_ = nullptr;
  char status_[56] = {0};
  uint32_t aiAtMs_ = 0;

  // card: bits0-3 value 0-9,10=skip,11=rev,12=+2,13=wild,14=+4
  // bits4-5 color 0-3 (ignored for wild until chosen)
  static constexpr int HAND_MAX = 30;
  uint8_t deck_[108];
  int deckN_ = 0;
  uint8_t discard_[108];
  int discardN_ = 0;
  uint8_t player_[HAND_MAX];
  int playerN_ = 0;
  uint8_t ai_[HAND_MAX];
  int aiN_ = 0;
  int handScroll_ = 0;

  void allocFb();
  void freeFb();
  void buildDeck();
  void shuffle();
  uint8_t drawCard();
  void deal();
  void clearFb(uint16_t c);
  void putPixel(int x, int y, uint16_t c);
  void fillRect(int x, int y, int w, int h, uint16_t c);
  void drawCardFace(int x, int y, uint8_t c, bool sel);
  uint16_t colorOf(uint8_t c) const;
  uint8_t valueOf(uint8_t c) const { return c & 0x0F; }
  uint8_t suitOf(uint8_t c) const { return (c >> 4) & 3; }
  bool playable(uint8_t c) const;
  uint8_t topDiscard() const;
  void playCard(uint8_t c, bool fromPlayer);
  void applyEffect(uint8_t c, bool fromPlayer);
  void aiPlay();
  void updateStatus();
  void checkWin();
};

extern UnoGame g_uno;
