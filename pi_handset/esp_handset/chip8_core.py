"""CHIP-8 interpreter — tiny, always-on, no native core required."""

from __future__ import annotations

import random
from typing import List, Optional, Set

FONT = bytes(
    [
        0xF0, 0x90, 0x90, 0x90, 0xF0,
        0x20, 0x60, 0x20, 0x20, 0x70,
        0xF0, 0x10, 0xF0, 0x80, 0xF0,
        0xF0, 0x10, 0xF0, 0x10, 0xF0,
        0x90, 0x90, 0xF0, 0x10, 0x10,
        0xF0, 0x80, 0xF0, 0x10, 0xF0,
        0xF0, 0x80, 0xF0, 0x90, 0xF0,
        0xF0, 0x10, 0x20, 0x40, 0x40,
        0xF0, 0x90, 0xF0, 0x90, 0xF0,
        0xF0, 0x90, 0xF0, 0x10, 0xF0,
        0xF0, 0x90, 0xF0, 0x90, 0x90,
        0xE0, 0x90, 0xE0, 0x90, 0xE0,
        0xF0, 0x80, 0x80, 0x80, 0xF0,
        0xE0, 0x90, 0x90, 0x90, 0xE0,
        0xF0, 0x80, 0xF0, 0x80, 0xF0,
        0xF0, 0x80, 0xF0, 0x80, 0x80,
    ]
)

# Digivice pad → CHIP-8 hex keypad (common VIP / Pong layout)
BTN_TO_KEY = {
    "left": 0x4,
    "right": 0x6,
    "up": 0x2,
    "down": 0x8,
    "a": 0x5,
    "b": 0x7,
    "start": 0xA,
    "select": 0xB,
}


class Chip8:
    def __init__(self, rom: bytes):
        self.mem = bytearray(4096)
        self.mem[0x50 : 0x50 + len(FONT)] = FONT
        blob = rom[: 4096 - 0x200]
        self.mem[0x200 : 0x200 + len(blob)] = blob
        self.v = [0] * 16
        self.i = 0
        self.pc = 0x200
        self.sp = 0
        self.stack: List[int] = [0] * 16
        self.dt = 0
        self.st = 0
        self.fb = [0] * (64 * 32)
        self.draw = True
        self.wait_key: Optional[int] = None
        self.alive = True
        self._prev_keys: Set[int] = set()

    def tick_timers(self) -> None:
        if self.dt > 0:
            self.dt -= 1
        if self.st > 0:
            self.st -= 1

    def step(self, held: Set[str], n: int = 10) -> None:
        keys = {BTN_TO_KEY[b] for b in held if b in BTN_TO_KEY}
        if self.wait_key is not None:
            pressed = keys - self._prev_keys
            if pressed:
                self.v[self.wait_key] = next(iter(pressed)) & 0xFF
                self.wait_key = None
            self._prev_keys = keys
            return
        self._prev_keys = keys
        for _ in range(max(1, n)):
            if self.wait_key is not None or not self.alive:
                return
            self._opcode(keys)

    def rgb888(self):
        try:
            import numpy as np
        except ImportError:
            return None
        on = np.array([200, 220, 160], dtype=np.uint8)
        off = np.array([12, 18, 12], dtype=np.uint8)
        bits = np.frombuffer(bytes(self.fb), dtype=np.uint8).reshape(32, 64)
        return np.where(bits[:, :, None] > 0, on, off)

    def _opcode(self, keys: Set[int]) -> None:
        pc = self.pc
        if pc + 1 >= 4096:
            self.alive = False
            return
        op = (self.mem[pc] << 8) | self.mem[pc + 1]
        self.pc = (pc + 2) & 0xFFF
        nnn = op & 0x0FFF
        n = op & 0x000F
        x = (op >> 8) & 0x0F
        y = (op >> 4) & 0x0F
        kk = op & 0x00FF
        v = self.v
        hi = op & 0xF000

        if op == 0x00E0:
            self.fb = [0] * (64 * 32)
            self.draw = True
        elif op == 0x00EE:
            if self.sp <= 0:
                self.alive = False
                return
            self.sp -= 1
            self.pc = self.stack[self.sp]
        elif hi == 0x1000:
            self.pc = nnn
        elif hi == 0x2000:
            if self.sp >= 16:
                self.alive = False
                return
            self.stack[self.sp] = self.pc
            self.sp += 1
            self.pc = nnn
        elif hi == 0x3000:
            if v[x] == kk:
                self.pc = (self.pc + 2) & 0xFFF
        elif hi == 0x4000:
            if v[x] != kk:
                self.pc = (self.pc + 2) & 0xFFF
        elif hi == 0x5000 and n == 0:
            if v[x] == v[y]:
                self.pc = (self.pc + 2) & 0xFFF
        elif hi == 0x6000:
            v[x] = kk
        elif hi == 0x7000:
            v[x] = (v[x] + kk) & 0xFF
        elif hi == 0x8000:
            self._alu(x, y, n)
        elif hi == 0x9000 and n == 0:
            if v[x] != v[y]:
                self.pc = (self.pc + 2) & 0xFFF
        elif hi == 0xA000:
            self.i = nnn
        elif hi == 0xB000:
            self.pc = (nnn + v[0]) & 0xFFF
        elif hi == 0xC000:
            v[x] = random.randint(0, 255) & kk
        elif hi == 0xD000:
            self._draw(x, y, n)
        elif hi == 0xE000 and kk == 0x9E:
            if v[x] in keys:
                self.pc = (self.pc + 2) & 0xFFF
        elif hi == 0xE000 and kk == 0xA1:
            if v[x] not in keys:
                self.pc = (self.pc + 2) & 0xFFF
        elif hi == 0xF000:
            self._fx(x, kk, keys)

    def _alu(self, x: int, y: int, n: int) -> None:
        v = self.v
        if n == 0:
            v[x] = v[y]
        elif n == 1:
            v[x] |= v[y]
        elif n == 2:
            v[x] &= v[y]
        elif n == 3:
            v[x] ^= v[y]
        elif n == 4:
            s = v[x] + v[y]
            v[0xF] = 1 if s > 255 else 0
            v[x] = s & 0xFF
        elif n == 5:
            v[0xF] = 1 if v[x] >= v[y] else 0
            v[x] = (v[x] - v[y]) & 0xFF
        elif n == 6:
            v[0xF] = v[x] & 1
            v[x] >>= 1
        elif n == 7:
            v[0xF] = 1 if v[y] >= v[x] else 0
            v[x] = (v[y] - v[x]) & 0xFF
        elif n == 0xE:
            v[0xF] = (v[x] >> 7) & 1
            v[x] = (v[x] << 1) & 0xFF

    def _fx(self, x: int, kk: int, keys: Set[int]) -> None:
        v = self.v
        if kk == 0x07:
            v[x] = self.dt
        elif kk == 0x0A:
            self.wait_key = x
        elif kk == 0x15:
            self.dt = v[x]
        elif kk == 0x18:
            self.st = v[x]
        elif kk == 0x1E:
            self.i = (self.i + v[x]) & 0xFFF
        elif kk == 0x29:
            self.i = 0x50 + (v[x] & 0xF) * 5
        elif kk == 0x33:
            n = v[x]
            i = self.i
            if i + 2 < 4096:
                self.mem[i] = n // 100
                self.mem[i + 1] = (n // 10) % 10
                self.mem[i + 2] = n % 10
        elif kk == 0x55:
            i = self.i
            for r in range(x + 1):
                if i + r < 4096:
                    self.mem[i + r] = v[r]
        elif kk == 0x65:
            i = self.i
            for r in range(x + 1):
                v[r] = self.mem[i + r] if i + r < 4096 else 0

    def _draw(self, x: int, y: int, n: int) -> None:
        vx = self.v[x] % 64
        vy = self.v[y] % 32
        self.v[0xF] = 0
        for row in range(n):
            if vy + row >= 32:
                break
            bits = self.mem[(self.i + row) & 0xFFF]
            for col in range(8):
                if not (bits & (0x80 >> col)):
                    continue
                px = vx + col
                if px >= 64:
                    continue
                idx = (vy + row) * 64 + px
                if self.fb[idx]:
                    self.v[0xF] = 1
                    self.fb[idx] = 0
                else:
                    self.fb[idx] = 1
        self.draw = True
