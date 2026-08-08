#pragma once

#include "Config.h"
#include <stdint.h>

enum GameId : uint8_t {
  GAME_NONE = 0,
  GAME_SNAKE,
  GAME_PONG,
  GAME_TETRIS,
};

class Games {
 public:
  void begin();
  void start(GameId id);
  void stop();
  void tick();  // ~50 Hz from UI task when a game is active
  void onKey(uint16_t code, char ascii);
  GameId active() const { return active_; }
  bool isActive() const { return active_ != GAME_NONE; }
  int highScore(GameId id) const;
  void saveHighScore(GameId id, int score);

  // Framebuffer access for LVGL canvas blit (RGB565)
  static constexpr int FB_W = 240;
  static constexpr int FB_H = 240;
  const uint16_t* framebuffer() const { return fb_; }

 private:
  GameId active_ = GAME_NONE;
  uint16_t fb_[FB_W * FB_H];
  int scores_[4] = {0};
  uint32_t lastTickMs_ = 0;

  // Snake
  struct { int x, y; } snake_[128];
  int snakeLen_ = 0;
  int snakeDir_ = 1;  // 0L 1R 2U 3D
  int foodX_ = 0, foodY_ = 0;
  int snakeScore_ = 0;
  bool snakeDead_ = false;

  // Pong
  float ballX_ = 0, ballY_ = 0, ballVX_ = 0, ballVY_ = 0;
  int paddleY_ = 0, aiY_ = 0;
  int pongScore_ = 0, pongLives_ = 3;

  // Tetris
  uint8_t grid_[20][10] = {};
  int piece_ = 0, rot_ = 0, px_ = 0, py_ = 0;
  int tetrisScore_ = 0;
  int dropMs_ = 500;
  uint32_t lastDropMs_ = 0;
  bool tetrisOver_ = false;

  void clearFb(uint16_t color);
  void putPixel(int x, int y, uint16_t c);
  void fillRect(int x, int y, int w, int h, uint16_t c);
  void drawText5x7(int x, int y, const char* s, uint16_t c);

  void snakeInit();
  void snakeTick();
  void snakeDraw();

  void pongInit();
  void pongTick();
  void pongDraw();

  void tetrisInit();
  void tetrisTick();
  void tetrisDraw();
  void tetrisSpawn();
  bool tetrisCollide(int nx, int ny, int nrot) const;
  void tetrisLock();
  void tetrisClearLines();
};

extern Games g_games;
