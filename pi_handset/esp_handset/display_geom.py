"""Digivice panel geometry (Waveshare 2\" ST7789 240×320)."""

from __future__ import annotations

import os

# Override with env if panel orientation is swapped at runtime
W = int(os.environ.get("ESP_HANDSET_W", "240"))
H = int(os.environ.get("ESP_HANDSET_H", "320"))
