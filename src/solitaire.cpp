#include "solitaire.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "esp_heap_caps.h"

Solitaire g_solitaire;

static uint8_t mkCard(int suit, int rank, bool up) {
  return (uint8_t)((rank & 0xF) | ((suit & 3) << 4) | (up ? 0x40 : 0));
}
static int rankOf(uint8_t c) { return c & 0xF; }
static int suitOf(uint8_t c) { return (c >> 4) & 3; }
static bool isUp(uint8_t c) { return (c & 0x40) != 0; }
static uint8_t faceUp(uint8_t c) { return (uint8_t)(c | 0x40); }
static int colorOf(uint8_t c) { return suitOf(c) & 1; }  // 0 red (hearts/diamonds), 1 black

void Solitaire::allocFb() {
  if (fb_) return;
  fb_ = (uint16_t*)heap_caps_malloc(FB_W * FB_H * 2, MALLOC_CAP_SPIRAM);
  if (!fb_) fb_ = (uint16_t*)malloc(FB_W * FB_H * 2);
}

void Solitaire::freeFb() {
  if (fb_) {
    free(fb_);
    fb_ = nullptr;
  }
}

void Solitaire::clearFb(uint16_t c) {
  if (!fb_) return;
  for (int i = 0; i < FB_W * FB_H; i++) fb_[i] = c;
}

void Solitaire::putPixel(int x, int y, uint16_t c) {
  if (!fb_ || (unsigned)x >= FB_W || (unsigned)y >= FB_H) return;
  fb_[y * FB_W + x] = c;
}

void Solitaire::fillRect(int x, int y, int w, int h, uint16_t c) {
  for (int yy = y; yy < y + h; yy++)
    for (int xx = x; xx < x + w; xx++) putPixel(xx, yy, c);
}

void Solitaire::drawBack(int x, int y) {
  fillRect(x, y, 34, 48, 0x001F);
  fillRect(x + 2, y + 2, 30, 44, 0x0010);
  fillRect(x + 6, y + 8, 22, 32, 0x7BEF);
}

void Solitaire::drawCard(int x, int y, uint8_t card, bool selected) {
  if (!isUp(card)) {
    drawBack(x, y);
    if (selected) {
      // outline
      for (int i = 0; i < 34; i++) {
        putPixel(x + i, y, 0xFFE0);
        putPixel(x + i, y + 47, 0xFFE0);
      }
      for (int i = 0; i < 48; i++) {
        putPixel(x, y + i, 0xFFE0);
        putPixel(x + 33, y + i, 0xFFE0);
      }
    }
    return;
  }
  uint16_t bg = selected ? 0xFFE0 : 0xFFFF;
  fillRect(x, y, 34, 48, bg);
  fillRect(x + 1, y + 1, 32, 46, 0xFFFF);
  uint16_t col = colorOf(card) == 0 ? 0xF800 : 0x0000;
  static const char* ranks = "A23456789TJQK";
  char r = ranks[rankOf(card) - 1];
  static const char* suits = "CDHS";
  char s = suits[suitOf(card)];
  // tiny glyph: two chars as blocks
  auto plotCh = [&](int px, int py, char ch) {
    // 3x5-ish bars for A/2-9/T/J/Q/K and suit letter
    fillRect(px, py, 6, 8, col);
    (void)ch;
  };
  plotCh(x + 3, y + 3, r);
  plotCh(x + 3, y + 14, s);
  plotCh(x + 22, y + 34, r);
}

void Solitaire::begin() {
  allocFb();
  if (!fb_) return;
  active_ = true;
  won_ = false;
  selFrom_ = -1;
  shuffleDeal();
  updateStatus();
  draw();
}

void Solitaire::stop() {
  active_ = false;
  freeFb();
}

void Solitaire::shuffleDeal() {
  uint8_t deck[52];
  int n = 0;
  for (int s = 0; s < 4; s++)
    for (int r = 1; r <= 13; r++) deck[n++] = mkCard(s, r, false);
  for (int i = 51; i > 0; i--) {
    int j = rand() % (i + 1);
    uint8_t t = deck[i];
    deck[i] = deck[j];
    deck[j] = t;
  }
  stockN_ = wasteN_ = 0;
  for (int i = 0; i < 4; i++) foundationN_[i] = 0;
  for (int i = 0; i < 7; i++) tableauN_[i] = 0;
  int di = 0;
  for (int col = 0; col < 7; col++) {
    for (int row = 0; row <= col; row++) {
      uint8_t c = deck[di++];
      if (row == col) c = faceUp(c);
      tableau_[col][tableauN_[col]++] = c;
    }
  }
  while (di < 52) stock_[stockN_++] = deck[di++];
}

bool Solitaire::canStackTableau(uint8_t moving, uint8_t onto) const {
  if (!isUp(moving) || !isUp(onto)) return false;
  if (colorOf(moving) == colorOf(onto)) return false;
  return rankOf(moving) + 1 == rankOf(onto);
}

bool Solitaire::canStackFoundation(uint8_t moving, int f) const {
  if (!isUp(moving)) return false;
  if (foundationN_[f] == 0) return rankOf(moving) == 1;
  uint8_t top = foundation_[f][foundationN_[f] - 1];
  return suitOf(moving) == suitOf(top) && rankOf(moving) == rankOf(top) + 1;
}

bool Solitaire::moveToFoundation(uint8_t c, int f) {
  if (!canStackFoundation(c, f)) return false;
  foundation_[f][foundationN_[f]++] = c;
  return true;
}

void Solitaire::checkWin() {
  won_ = true;
  for (int i = 0; i < 4; i++)
    if (foundationN_[i] != 13) won_ = false;
  if (won_) snprintf(status_, sizeof(status_), "YOU WIN! Confirm=new");
}

void Solitaire::updateStatus() {
  if (won_) return;
  snprintf(status_, sizeof(status_), "Stock:%d  Click piles", stockN_);
}

int Solitaire::hitTest(int x, int y, int& outIdx) const {
  outIdx = 0;
  // stock
  if (x >= 8 && x < 42 && y >= 8 && y < 56) return 100;
  // waste
  if (x >= 50 && x < 84 && y >= 8 && y < 56) return 7;
  // foundations
  for (int f = 0; f < 4; f++) {
    int fx = 140 + f * 40;
    if (x >= fx && x < fx + 34 && y >= 8 && y < 56) return 8 + f;
  }
  // tableau
  for (int col = 0; col < 7; col++) {
    int tx = 8 + col * 42;
    int n = tableauN_[col];
    if (n == 0) {
      if (x >= tx && x < tx + 34 && y >= 70 && y < 118) {
        outIdx = 0;
        return col;
      }
      continue;
    }
    for (int i = 0; i < n; i++) {
      int ty = 70 + i * 14;
      int h = (i == n - 1) ? 48 : 14;
      if (x >= tx && x < tx + 34 && y >= ty && y < ty + h) {
        outIdx = i;
        return col;
      }
    }
  }
  // new deal button area
  if (y >= FB_H - 28) return 200;
  return -1;
}

void Solitaire::click(int x, int y) {
  if (!active_) return;
  if (won_) {
    begin();
    return;
  }
  int idx = 0;
  int hit = hitTest(x, y, idx);
  if (hit == 200) {
    begin();
    return;
  }
  if (hit == 100) {
    // draw from stock
    if (stockN_ > 0) {
      waste_[wasteN_++] = faceUp(stock_[--stockN_]);
    } else if (wasteN_ > 0) {
      while (wasteN_ > 0) {
        uint8_t c = waste_[--wasteN_];
        c = (uint8_t)(c & ~0x40);
        stock_[stockN_++] = c;
      }
    }
    selFrom_ = -1;
    updateStatus();
    draw();
    return;
  }

  auto clearSel = [&]() { selFrom_ = -1; };

  if (selFrom_ < 0) {
    // select
    if (hit == 7 && wasteN_ > 0) {
      selFrom_ = 7;
      selIdx_ = wasteN_ - 1;
    } else if (hit >= 0 && hit < 7 && tableauN_[hit] > 0) {
      // must select face-up run from idx
      if (!isUp(tableau_[hit][idx])) {
        draw();
        return;
      }
      selFrom_ = hit;
      selIdx_ = idx;
    } else if (hit >= 8 && hit <= 11 && foundationN_[hit - 8] > 0) {
      selFrom_ = hit;
      selIdx_ = foundationN_[hit - 8] - 1;
    }
    draw();
    return;
  }

  // try move selection to hit
  uint8_t moving[MAX_PILE];
  int moveN = 0;
  if (selFrom_ == 7) {
    moving[moveN++] = waste_[wasteN_ - 1];
  } else if (selFrom_ >= 8 && selFrom_ <= 11) {
    int f = selFrom_ - 8;
    moving[moveN++] = foundation_[f][foundationN_[f] - 1];
  } else if (selFrom_ >= 0 && selFrom_ < 7) {
    for (int i = selIdx_; i < tableauN_[selFrom_]; i++)
      moving[moveN++] = tableau_[selFrom_][i];
  }

  bool ok = false;
  if (hit >= 8 && hit <= 11 && moveN == 1) {
    ok = moveToFoundation(moving[0], hit - 8);
    if (ok) {
      // remove source
      if (selFrom_ == 7)
        wasteN_--;
      else if (selFrom_ >= 8)
        foundationN_[selFrom_ - 8]--;
      else {
        tableauN_[selFrom_] = selIdx_;
        if (tableauN_[selFrom_] > 0)
          tableau_[selFrom_][tableauN_[selFrom_] - 1] =
              faceUp(tableau_[selFrom_][tableauN_[selFrom_] - 1]);
      }
    }
  } else if (hit >= 0 && hit < 7) {
    uint8_t onto = 0;
    bool empty = tableauN_[hit] == 0;
    if (!empty) onto = tableau_[hit][tableauN_[hit] - 1];
    if (empty) {
      ok = (rankOf(moving[0]) == 13);  // kings only
    } else {
      ok = canStackTableau(moving[0], onto);
    }
    if (ok) {
      for (int i = 0; i < moveN; i++)
        tableau_[hit][tableauN_[hit]++] = moving[i];
      if (selFrom_ == 7)
        wasteN_--;
      else if (selFrom_ >= 8)
        foundationN_[selFrom_ - 8]--;
      else {
        tableauN_[selFrom_] = selIdx_;
        if (tableauN_[selFrom_] > 0)
          tableau_[selFrom_][tableauN_[selFrom_] - 1] =
              faceUp(tableau_[selFrom_][tableauN_[selFrom_] - 1]);
      }
    }
  } else if (hit == selFrom_) {
    clearSel();
    draw();
    return;
  }

  // double-tap waste/tableau top to foundation
  if (!ok && selFrom_ >= 0 && moveN == 1) {
    for (int f = 0; f < 4; f++) {
      if (moveToFoundation(moving[0], f)) {
        ok = true;
        if (selFrom_ == 7)
          wasteN_--;
        else if (selFrom_ >= 8)
          foundationN_[selFrom_ - 8]--;
        else {
          tableauN_[selFrom_] = selIdx_;
          if (tableauN_[selFrom_] > 0)
            tableau_[selFrom_][tableauN_[selFrom_] - 1] =
                faceUp(tableau_[selFrom_][tableauN_[selFrom_] - 1]);
        }
        break;
      }
    }
  }

  clearSel();
  checkWin();
  if (!won_) updateStatus();
  draw();
}

void Solitaire::draw() {
  if (!fb_) return;
  clearFb(0x0460);
  // stock
  if (stockN_ > 0)
    drawBack(8, 8);
  else
    fillRect(8, 8, 34, 48, 0x0320);
  // waste
  if (wasteN_ > 0)
    drawCard(50, 8, waste_[wasteN_ - 1], selFrom_ == 7);
  else
    fillRect(50, 8, 34, 48, 0x0320);
  // foundations
  for (int f = 0; f < 4; f++) {
    int fx = 140 + f * 40;
    if (foundationN_[f] > 0)
      drawCard(fx, 8, foundation_[f][foundationN_[f] - 1], selFrom_ == 8 + f);
    else
      fillRect(fx, 8, 34, 48, 0x0320);
  }
  // tableau
  for (int col = 0; col < 7; col++) {
    int tx = 8 + col * 42;
    if (tableauN_[col] == 0) {
      fillRect(tx, 70, 34, 48, 0x0320);
      continue;
    }
    for (int i = 0; i < tableauN_[col]; i++) {
      bool sel = (selFrom_ == col && i >= selIdx_);
      drawCard(tx, 70 + i * 14, tableau_[col][i], sel);
    }
  }
  // new game strip
  fillRect(0, FB_H - 24, FB_W, 24, 0x2104);
  // status already in label
}
