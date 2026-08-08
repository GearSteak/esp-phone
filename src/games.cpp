#include "games.h"
#include "storage.h"
#include <string.h>
#include <stdlib.h>
#include <math.h>

Games g_games;

// Tiny 5x7 font (digits + few letters) — packed columns
static const uint8_t FONT5x7[][5] = {
    {0x3E, 0x51, 0x49, 0x45, 0x3E},  // 0
    {0x00, 0x42, 0x7F, 0x40, 0x00},  // 1
    {0x42, 0x61, 0x51, 0x49, 0x46},  // 2
    {0x21, 0x41, 0x45, 0x4B, 0x31},  // 3
    {0x18, 0x14, 0x12, 0x7F, 0x10},  // 4
    {0x27, 0x45, 0x45, 0x45, 0x39},  // 5
    {0x3C, 0x4A, 0x49, 0x49, 0x30},  // 6
    {0x01, 0x71, 0x09, 0x05, 0x03},  // 7
    {0x36, 0x49, 0x49, 0x49, 0x36},  // 8
    {0x06, 0x49, 0x49, 0x29, 0x1E},  // 9
};

void Games::begin() {
  int hs[4] = {0};
  if (Storage::loadHighScores(hs)) {
    memcpy(scores_, hs, sizeof(scores_));
  }
  clearFb(0x0000);
}

void Games::clearFb(uint16_t color) {
  for (int i = 0; i < FB_W * FB_H; i++) fb_[i] = color;
}

void Games::putPixel(int x, int y, uint16_t c) {
  if ((unsigned)x >= FB_W || (unsigned)y >= FB_H) return;
  fb_[y * FB_W + x] = c;
}

void Games::fillRect(int x, int y, int w, int h, uint16_t c) {
  for (int yy = y; yy < y + h; yy++)
    for (int xx = x; xx < x + w; xx++) putPixel(xx, yy, c);
}

void Games::drawText5x7(int x, int y, const char* s, uint16_t c) {
  while (*s) {
    char ch = *s++;
    if (ch >= '0' && ch <= '9') {
      const uint8_t* g = FONT5x7[ch - '0'];
      for (int col = 0; col < 5; col++) {
        for (int row = 0; row < 7; row++) {
          if (g[col] & (1 << row)) putPixel(x + col, y + row, c);
        }
      }
    }
    x += 6;
  }
}

int Games::highScore(GameId id) const { return scores_[(int)id]; }

void Games::saveHighScore(GameId id, int score) {
  if (score > scores_[(int)id]) {
    scores_[(int)id] = score;
    Storage::saveHighScores(scores_);
  }
}

void Games::start(GameId id) {
  active_ = id;
  lastTickMs_ = millis();
  switch (id) {
    case GAME_SNAKE: snakeInit(); break;
    case GAME_PONG: pongInit(); break;
    case GAME_TETRIS: tetrisInit(); break;
    default: break;
  }
}

void Games::stop() { active_ = GAME_NONE; }

void Games::tick() {
  if (active_ == GAME_NONE) return;
  uint32_t now = millis();
  if (now - lastTickMs_ < 50) return;
  lastTickMs_ = now;
  switch (active_) {
    case GAME_SNAKE: snakeTick(); snakeDraw(); break;
    case GAME_PONG: pongTick(); pongDraw(); break;
    case GAME_TETRIS: tetrisTick(); tetrisDraw(); break;
    default: break;
  }
}

void Games::onKey(uint16_t code, char ascii) {
  (void)ascii;
  if (active_ == GAME_SNAKE) {
    if (code == KEY_LEFT && snakeDir_ != 1) snakeDir_ = 0;
    if (code == KEY_RIGHT && snakeDir_ != 0) snakeDir_ = 1;
    if (code == KEY_UP && snakeDir_ != 3) snakeDir_ = 2;
    if (code == KEY_DOWN && snakeDir_ != 2) snakeDir_ = 3;
    if (code == '\n' && snakeDead_) snakeInit();
  } else if (active_ == GAME_PONG) {
    if (code == KEY_UP) paddleY_ -= 12;
    if (code == KEY_DOWN) paddleY_ += 12;
    if (paddleY_ < 0) paddleY_ = 0;
    if (paddleY_ > FB_H - 40) paddleY_ = FB_H - 40;
  } else if (active_ == GAME_TETRIS) {
    if (code == KEY_LEFT && !tetrisCollide(px_ - 1, py_, rot_)) px_--;
    if (code == KEY_RIGHT && !tetrisCollide(px_ + 1, py_, rot_)) px_++;
    if (code == KEY_DOWN && !tetrisCollide(px_, py_ + 1, rot_)) py_++;
    if (code == KEY_UP || code == '\n') {
      int nr = (rot_ + 1) & 3;
      if (!tetrisCollide(px_, py_, nr)) rot_ = nr;
    }
    if (code == '\n' && tetrisOver_) tetrisInit();
  }
}

// ---- Snake ----
void Games::snakeInit() {
  snakeLen_ = 4;
  snakeDir_ = 1;
  snakeScore_ = 0;
  snakeDead_ = false;
  for (int i = 0; i < snakeLen_; i++) {
    snake_[i].x = 10 - i;
    snake_[i].y = 10;
  }
  foodX_ = 15;
  foodY_ = 12;
}

void Games::snakeTick() {
  if (snakeDead_) return;
  static uint32_t acc = 0;
  acc += 50;
  if (acc < 120) return;
  acc = 0;
  int nx = snake_[0].x;
  int ny = snake_[0].y;
  if (snakeDir_ == 0) nx--;
  if (snakeDir_ == 1) nx++;
  if (snakeDir_ == 2) ny--;
  if (snakeDir_ == 3) ny++;
  if (nx < 0 || ny < 0 || nx >= 30 || ny >= 30) {
    snakeDead_ = true;
    saveHighScore(GAME_SNAKE, snakeScore_);
    return;
  }
  for (int i = 0; i < snakeLen_; i++) {
    if (snake_[i].x == nx && snake_[i].y == ny) {
      snakeDead_ = true;
      saveHighScore(GAME_SNAKE, snakeScore_);
      return;
    }
  }
  for (int i = snakeLen_; i > 0; i--) snake_[i] = snake_[i - 1];
  snake_[0].x = nx;
  snake_[0].y = ny;
  if (nx == foodX_ && ny == foodY_) {
    if (snakeLen_ < 127) snakeLen_++;
    snakeScore_ += 10;
    foodX_ = rand() % 30;
    foodY_ = rand() % 30;
  }
}

void Games::snakeDraw() {
  clearFb(0x0220);
  const int cell = 8;
  fillRect(0, 0, 30 * cell, 30 * cell, 0x0100);
  fillRect(foodX_ * cell, foodY_ * cell, cell, cell, 0xF800);
  for (int i = 0; i < snakeLen_; i++) {
    fillRect(snake_[i].x * cell, snake_[i].y * cell, cell - 1, cell - 1,
             i == 0 ? 0x07E0 : 0x04A0);
  }
  char buf[16];
  snprintf(buf, sizeof(buf), "%d", snakeScore_);
  drawText5x7(2, 2, buf, 0xFFFF);
  if (snakeDead_) drawText5x7(80, 110, "0", 0xF800);  // show score already
}

// ---- Pong ----
void Games::pongInit() {
  ballX_ = FB_W / 2.0f;
  ballY_ = FB_H / 2.0f;
  ballVX_ = 2.4f;
  ballVY_ = 1.6f;
  paddleY_ = FB_H / 2 - 20;
  aiY_ = paddleY_;
  pongScore_ = 0;
  pongLives_ = 3;
}

void Games::pongTick() {
  ballX_ += ballVX_;
  ballY_ += ballVY_;
  if (ballY_ < 0 || ballY_ > FB_H - 6) ballVY_ = -ballVY_;
  // player paddle left
  if (ballX_ < 12 && ballY_ > paddleY_ && ballY_ < paddleY_ + 40) {
    ballVX_ = fabsf(ballVX_) + 0.1f;
    ballX_ = 12;
  }
  // AI right
  float target = ballY_ - 20;
  aiY_ += (int)((target - aiY_) * 0.15f);
  if (ballX_ > FB_W - 18 && ballY_ > aiY_ && ballY_ < aiY_ + 40) {
    ballVX_ = -fabsf(ballVX_);
    ballX_ = FB_W - 18;
    pongScore_++;
  }
  if (ballX_ < 0) {
    pongLives_--;
    ballX_ = FB_W / 2;
    ballY_ = FB_H / 2;
    ballVX_ = 2.4f;
    if (pongLives_ <= 0) {
      saveHighScore(GAME_PONG, pongScore_);
      pongInit();
    }
  }
  if (ballX_ > FB_W) {
    ballX_ = FB_W / 2;
    ballVX_ = -2.4f;
  }
}

void Games::pongDraw() {
  clearFb(0x0000);
  fillRect(4, paddleY_, 6, 40, 0x07FF);
  fillRect(FB_W - 10, aiY_, 6, 40, 0xFFE0);
  fillRect((int)ballX_, (int)ballY_, 6, 6, 0xFFFF);
  char buf[16];
  snprintf(buf, sizeof(buf), "%d", pongScore_);
  drawText5x7(FB_W / 2 - 10, 4, buf, 0xFFFF);
}

// ---- Tetris ----
static const uint16_t PIECE_COLORS[7] = {0x07FF, 0xFFE0, 0xF81F, 0x07E0,
                                         0xF800, 0x001F, 0xFC00};

// 4 rotations x 4 cells for 7 pieces (I,O,T,S,Z,J,L) as 4-bit nibbles in 16-bit
static const uint16_t SHAPES[7][4] = {
    {0x0F00, 0x2222, 0x00F0, 0x4444},  // I
    {0x0660, 0x0660, 0x0660, 0x0660},  // O
    {0x0E40, 0x4C40, 0x4E00, 0x4640},  // T
    {0x06C0, 0x8C40, 0x06C0, 0x8C40},  // S
    {0x0C60, 0x4C80, 0x0C60, 0x4C80},  // Z
    {0x08E0, 0x6440, 0x0E20, 0x44C0},  // J
    {0x02E0, 0x4460, 0x0E80, 0xC440},  // L
};

void Games::tetrisInit() {
  memset(grid_, 0, sizeof(grid_));
  tetrisScore_ = 0;
  dropMs_ = 500;
  tetrisOver_ = false;
  tetrisSpawn();
}

void Games::tetrisSpawn() {
  piece_ = rand() % 7;
  rot_ = 0;
  px_ = 3;
  py_ = 0;
  if (tetrisCollide(px_, py_, rot_)) {
    tetrisOver_ = true;
    saveHighScore(GAME_TETRIS, tetrisScore_);
  }
  lastDropMs_ = millis();
}

bool Games::tetrisCollide(int nx, int ny, int nrot) const {
  uint16_t shape = SHAPES[piece_][nrot & 3];
  for (int i = 0; i < 16; i++) {
    if (!(shape & (0x8000 >> i))) continue;
    int x = nx + (i % 4);
    int y = ny + (i / 4);
    if (x < 0 || x >= 10 || y >= 20) return true;
    if (y >= 0 && grid_[y][x]) return true;
  }
  return false;
}

void Games::tetrisLock() {
  uint16_t shape = SHAPES[piece_][rot_ & 3];
  for (int i = 0; i < 16; i++) {
    if (!(shape & (0x8000 >> i))) continue;
    int x = px_ + (i % 4);
    int y = py_ + (i / 4);
    if (y >= 0 && y < 20 && x >= 0 && x < 10) grid_[y][x] = (uint8_t)(piece_ + 1);
  }
  tetrisClearLines();
  tetrisSpawn();
}

void Games::tetrisClearLines() {
  for (int y = 19; y >= 0; y--) {
    bool full = true;
    for (int x = 0; x < 10; x++)
      if (!grid_[y][x]) full = false;
    if (full) {
      for (int yy = y; yy > 0; yy--)
        memcpy(grid_[yy], grid_[yy - 1], 10);
      memset(grid_[0], 0, 10);
      tetrisScore_ += 100;
      y++;
      if (dropMs_ > 120) dropMs_ -= 10;
    }
  }
}

void Games::tetrisTick() {
  if (tetrisOver_) return;
  if (millis() - lastDropMs_ >= (uint32_t)dropMs_) {
    lastDropMs_ = millis();
    if (!tetrisCollide(px_, py_ + 1, rot_))
      py_++;
    else
      tetrisLock();
  }
}

void Games::tetrisDraw() {
  clearFb(0x10A2);
  const int ox = 20, oy = 10, cs = 11;
  fillRect(ox - 2, oy - 2, 10 * cs + 4, 20 * cs + 4, 0xFFFF);
  fillRect(ox, oy, 10 * cs, 20 * cs, 0x0000);
  for (int y = 0; y < 20; y++) {
    for (int x = 0; x < 10; x++) {
      if (grid_[y][x])
        fillRect(ox + x * cs, oy + y * cs, cs - 1, cs - 1,
                 PIECE_COLORS[grid_[y][x] - 1]);
    }
  }
  uint16_t shape = SHAPES[piece_][rot_ & 3];
  for (int i = 0; i < 16; i++) {
    if (!(shape & (0x8000 >> i))) continue;
    int x = px_ + (i % 4);
    int y = py_ + (i / 4);
    if (y >= 0)
      fillRect(ox + x * cs, oy + y * cs, cs - 1, cs - 1, PIECE_COLORS[piece_]);
  }
  char buf[16];
  snprintf(buf, sizeof(buf), "%d", tetrisScore_);
  drawText5x7(150, 20, buf, 0xFFFF);
}
