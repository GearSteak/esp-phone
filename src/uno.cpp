#include "uno.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "esp_heap_caps.h"

UnoGame g_uno;

static uint8_t mkUno(int color, int val) {
  return (uint8_t)((val & 0x0F) | ((color & 3) << 4));
}

void UnoGame::allocFb() {
  if (fb_) return;
  fb_ = (uint16_t*)heap_caps_malloc(FB_W * FB_H * 2, MALLOC_CAP_SPIRAM);
  if (!fb_) fb_ = (uint16_t*)malloc(FB_W * FB_H * 2);
}

void UnoGame::freeFb() {
  if (fb_) {
    free(fb_);
    fb_ = nullptr;
  }
}

void UnoGame::clearFb(uint16_t c) {
  if (!fb_) return;
  for (int i = 0; i < FB_W * FB_H; i++) fb_[i] = c;
}

void UnoGame::putPixel(int x, int y, uint16_t c) {
  if (!fb_ || (unsigned)x >= FB_W || (unsigned)y >= FB_H) return;
  fb_[y * FB_W + x] = c;
}

void UnoGame::fillRect(int x, int y, int w, int h, uint16_t c) {
  for (int yy = y; yy < y + h; yy++)
    for (int xx = x; xx < x + w; xx++) putPixel(xx, yy, c);
}

uint16_t UnoGame::colorOf(uint8_t c) const {
  static const uint16_t cols[4] = {0xF800, 0x07E0, 0x001F, 0xFFE0};  // R G B Y
  uint8_t v = valueOf(c);
  if (v >= 13) return 0xFFFF;  // wild face
  return cols[suitOf(c)];
}

void UnoGame::drawCardFace(int x, int y, uint8_t c, bool sel) {
  uint16_t bg = colorOf(c);
  if (sel) fillRect(x - 1, y - 1, 36, 50, 0xFFFF);
  fillRect(x, y, 34, 48, bg);
  fillRect(x + 2, y + 2, 30, 44, 0xFFFF);
  uint8_t v = valueOf(c);
  uint16_t ink = (v >= 13) ? 0x0000 : colorOf(c);
  fillRect(x + 8, y + 16, 18, 16, ink);
  // value hint bar height encodes type
  if (v <= 9)
    fillRect(x + 10, y + 6, 4 + v, 6, ink);
  else if (v == 10)
    fillRect(x + 10, y + 6, 14, 6, 0xF800);  // skip
  else if (v == 11)
    fillRect(x + 10, y + 6, 14, 6, 0x07FF);  // rev
  else if (v == 12)
    fillRect(x + 10, y + 6, 14, 6, 0xFD20);  // +2
  else if (v == 13)
    fillRect(x + 8, y + 6, 18, 6, 0x0000);  // wild
  else
    fillRect(x + 8, y + 6, 18, 6, 0xF800);  // +4
}

void UnoGame::buildDeck() {
  deckN_ = 0;
  for (int col = 0; col < 4; col++) {
    deck_[deckN_++] = mkUno(col, 0);
    for (int n = 1; n <= 9; n++) {
      deck_[deckN_++] = mkUno(col, n);
      deck_[deckN_++] = mkUno(col, n);
    }
    for (int i = 0; i < 2; i++) {
      deck_[deckN_++] = mkUno(col, 10);  // skip
      deck_[deckN_++] = mkUno(col, 11);  // reverse
      deck_[deckN_++] = mkUno(col, 12);  // +2
    }
  }
  for (int i = 0; i < 4; i++) {
    deck_[deckN_++] = mkUno(0, 13);  // wild
    deck_[deckN_++] = mkUno(0, 14);  // +4
  }
}

void UnoGame::shuffle() {
  for (int i = deckN_ - 1; i > 0; i--) {
    int j = rand() % (i + 1);
    uint8_t t = deck_[i];
    deck_[i] = deck_[j];
    deck_[j] = t;
  }
}

uint8_t UnoGame::drawCard() {
  if (deckN_ == 0) {
    // recycle discard except top
    if (discardN_ <= 1) return 0xFF;
    uint8_t top = discard_[discardN_ - 1];
    for (int i = 0; i < discardN_ - 1; i++) deck_[deckN_++] = discard_[i];
    discardN_ = 0;
    discard_[discardN_++] = top;
    shuffle();
  }
  return deck_[--deckN_];
}

void UnoGame::deal() {
  playerN_ = aiN_ = discardN_ = 0;
  for (int i = 0; i < 7; i++) {
    player_[playerN_++] = drawCard();
    ai_[aiN_++] = drawCard();
  }
  uint8_t start;
  do {
    start = drawCard();
  } while (valueOf(start) >= 13);
  discard_[discardN_++] = start;
  wildColor_ = suitOf(start);
  playerTurn_ = true;
  waitingColor_ = false;
  direction_ = 1;
  over_ = false;
  handScroll_ = 0;
}

void UnoGame::begin() {
  allocFb();
  if (!fb_) return;
  active_ = true;
  buildDeck();
  shuffle();
  deal();
  updateStatus();
  draw();
}

void UnoGame::stop() {
  active_ = false;
  freeFb();
}

uint8_t UnoGame::topDiscard() const {
  return discardN_ ? discard_[discardN_ - 1] : 0;
}

bool UnoGame::playable(uint8_t c) const {
  uint8_t top = topDiscard();
  uint8_t v = valueOf(c);
  if (v == 13 || v == 14) return true;
  uint8_t topV = valueOf(top);
  uint8_t topCol = (topV >= 13) ? wildColor_ : suitOf(top);
  if (suitOf(c) == topCol) return true;
  if (v == topV && topV < 13) return true;
  return false;
}

void UnoGame::applyEffect(uint8_t c, bool fromPlayer) {
  uint8_t v = valueOf(c);
  int opponentDraws = 0;
  bool skip = false;
  if (v == 10) skip = true;           // skip
  if (v == 11) direction_ = -direction_;  // reverse (=skip in 2p)
  if (v == 11) skip = true;
  if (v == 12) opponentDraws = 2;
  if (v == 14) opponentDraws = 4;
  if (v == 13 || v == 14) {
    if (fromPlayer) {
      waitingColor_ = true;
      updateStatus();
      return;
    }
    // AI picks most common color in hand
    int cnt[4] = {};
    for (int i = 0; i < aiN_; i++)
      if (valueOf(ai_[i]) < 13) cnt[suitOf(ai_[i])]++;
    int best = 0;
    for (int i = 1; i < 4; i++)
      if (cnt[i] > cnt[best]) best = i;
    wildColor_ = (uint8_t)best;
  }
  if (opponentDraws) {
    if (fromPlayer) {
      for (int i = 0; i < opponentDraws; i++) {
        uint8_t d = drawCard();
        if (d != 0xFF && aiN_ < HAND_MAX) ai_[aiN_++] = d;
      }
    } else {
      for (int i = 0; i < opponentDraws; i++) {
        uint8_t d = drawCard();
        if (d != 0xFF && playerN_ < HAND_MAX) player_[playerN_++] = d;
      }
    }
    skip = true;
  }
  if (skip)
    playerTurn_ = fromPlayer;  // same player again? No: skip means opponent loses turn, so current player keeps? 
  // Standard: after you play skip, opponent is skipped so it's your turn again in 2P.
  // After normal play, turn passes.
  // So: if skip, playerTurn_ stays with fromPlayer; else flips.
  if (!skip) playerTurn_ = !fromPlayer;
  else playerTurn_ = fromPlayer;

  if (!playerTurn_) aiAtMs_ = millis() + 600;
}

void UnoGame::playCard(uint8_t c, bool fromPlayer) {
  discard_[discardN_++] = c;
  if (valueOf(c) < 13) wildColor_ = suitOf(c);
  applyEffect(c, fromPlayer);
  checkWin();
}

void UnoGame::checkWin() {
  if (playerN_ == 0) {
    over_ = true;
    snprintf(status_, sizeof(status_), "YOU WIN! Click=new");
  } else if (aiN_ == 0) {
    over_ = true;
    snprintf(status_, sizeof(status_), "AI wins. Click=new");
  }
}

void UnoGame::updateStatus() {
  if (over_) return;
  if (waitingColor_) {
    snprintf(status_, sizeof(status_), "Pick color: R G B Y tops");
    return;
  }
  static const char* cn = "RGBY";
  snprintf(status_, sizeof(status_), "%s | AI:%d You:%d | %c",
           playerTurn_ ? "Your turn" : "AI turn", aiN_, playerN_,
           cn[wildColor_ & 3]);
}

void UnoGame::aiPlay() {
  if (!active_ || over_ || playerTurn_ || waitingColor_) return;
  // find playable
  int pick = -1;
  for (int i = 0; i < aiN_; i++) {
    if (playable(ai_[i])) {
      pick = i;
      // prefer non-wild
      if (valueOf(ai_[i]) < 13) break;
    }
  }
  if (pick < 0) {
    uint8_t d = drawCard();
    if (d != 0xFF && aiN_ < HAND_MAX) {
      ai_[aiN_++] = d;
      if (playable(d)) {
        aiN_--;
        playCard(d, false);
      } else {
        playerTurn_ = true;
      }
    } else {
      playerTurn_ = true;
    }
  } else {
    uint8_t c = ai_[pick];
    for (int i = pick; i < aiN_ - 1; i++) ai_[i] = ai_[i + 1];
    aiN_--;
    playCard(c, false);
  }
  updateStatus();
  draw();
}

void UnoGame::tick() {
  if (!active_ || over_ || playerTurn_ || waitingColor_) return;
  if (millis() >= aiAtMs_) aiPlay();
}

void UnoGame::click(int x, int y) {
  if (!active_) return;
  if (over_) {
    begin();
    return;
  }
  // color picker after wild: four top boxes
  if (waitingColor_) {
    for (int i = 0; i < 4; i++) {
      int bx = 20 + i * 70;
      if (x >= bx && x < bx + 50 && y >= 8 && y < 40) {
        wildColor_ = (uint8_t)i;
        waitingColor_ = false;
        playerTurn_ = false;  // wild was played by player; after color, AI turn unless skip/+4
        // +4/+wild already applied skip logic incorrectly — fix: after wild from player, turn passes unless +4
        uint8_t top = topDiscard();
        if (valueOf(top) == 14) {
          for (int k = 0; k < 4; k++) {
            uint8_t d = drawCard();
            if (d != 0xFF && aiN_ < HAND_MAX) ai_[aiN_++] = d;
          }
          playerTurn_ = true;  // +4 skips AI
        } else {
          playerTurn_ = false;
          aiAtMs_ = millis() + 500;
        }
        updateStatus();
        draw();
        return;
      }
    }
    return;
  }
  if (!playerTurn_) return;

  // draw pile
  if (x >= 120 && x < 154 && y >= 100 && y < 148) {
    uint8_t d = drawCard();
    if (d != 0xFF && playerN_ < HAND_MAX) {
      player_[playerN_++] = d;
      if (!playable(d)) {
        playerTurn_ = false;
        aiAtMs_ = millis() + 500;
      }
      // if playable, player may click it next
    }
    updateStatus();
    draw();
    return;
  }

  // hand cards
  int start = handScroll_;
  for (int i = 0; i < 7 && start + i < playerN_; i++) {
    int cx = 8 + i * 42;
    int cy = 320;
    if (x >= cx && x < cx + 34 && y >= cy && y < cy + 48) {
      int idx = start + i;
      uint8_t c = player_[idx];
      if (!playable(c)) return;
      for (int j = idx; j < playerN_ - 1; j++) player_[j] = player_[j + 1];
      playerN_--;
      if (valueOf(c) >= 13) {
        discard_[discardN_++] = c;
        waitingColor_ = true;
        checkWin();
        updateStatus();
        draw();
        return;
      }
      playCard(c, true);
      updateStatus();
      draw();
      return;
    }
  }
  // scroll arrows
  if (y >= 300 && y < 318) {
    if (x < 40 && handScroll_ > 0) handScroll_--;
    if (x > FB_W - 40 && handScroll_ + 7 < playerN_) handScroll_++;
    draw();
  }
  // new game
  if (y >= FB_H - 24) begin();
}

void UnoGame::draw() {
  if (!fb_) return;
  clearFb(0x10A2);
  // color picker
  if (waitingColor_) {
    static const uint16_t cols[4] = {0xF800, 0x07E0, 0x001F, 0xFFE0};
    for (int i = 0; i < 4; i++) fillRect(20 + i * 70, 8, 50, 32, cols[i]);
  }
  // AI hand backs
  for (int i = 0; i < aiN_ && i < 12; i++) fillRect(8 + i * 18, 50, 16, 24, 0x001F);

  // discard
  if (discardN_) drawCardFace(160, 100, topDiscard(), false);
  // draw pile
  fillRect(120, 100, 34, 48, 0x0010);
  fillRect(124, 110, 26, 28, 0x7BEF);

  // player hand
  int start = handScroll_;
  for (int i = 0; i < 7 && start + i < playerN_; i++) {
    drawCardFace(8 + i * 42, 320, player_[start + i], playable(player_[start + i]));
  }
  fillRect(0, FB_H - 24, FB_W, 24, 0x2104);
}
