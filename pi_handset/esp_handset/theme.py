"""Appearance prefs — wallpaper / theme (ESP Phone /ui parity on Pi)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

DATA = Path.home() / ".esp-handset"
UI_DIR = DATA / "ui"
PREFS = DATA / "appearance.json"
WALLPAPER_CANDIDATES = (
    UI_DIR / "wallpaper.jpg",
    UI_DIR / "wallpaper.jpeg",
    UI_DIR / "wallpaper.png",
    UI_DIR / "wallpaper.webp",
)


def ensure_dirs() -> None:
    UI_DIR.mkdir(parents=True, exist_ok=True)
    (UI_DIR / "icons").mkdir(parents=True, exist_ok=True)


def load_prefs() -> Dict[str, Any]:
    ensure_dirs()
    if PREFS.exists():
        try:
            return json.loads(PREFS.read_text())
        except Exception:
            pass
    return {
        "wallpaper": "",
        "status_dim": True,
        "icon_labels": True,
    }


def save_prefs(prefs: Dict[str, Any]) -> None:
    ensure_dirs()
    PREFS.write_text(json.dumps(prefs, indent=2))


def resolve_wallpaper() -> Optional[Path]:
    """Active wallpaper path, or None for default gradient."""
    prefs = load_prefs()
    custom = (prefs.get("wallpaper") or "").strip()
    if custom:
        p = Path(custom).expanduser()
        if p.is_file():
            return p
    for cand in WALLPAPER_CANDIDATES:
        if cand.is_file():
            return cand
    return None


def set_wallpaper_file(src: Path) -> Path:
    """Copy image into ~/.esp-handset/ui/wallpaper.<ext> and record prefs."""
    ensure_dirs()
    src = Path(src).expanduser()
    if not src.is_file():
        raise FileNotFoundError(str(src))
    ext = src.suffix.lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
        ext = ".jpg"
    dest = UI_DIR / f"wallpaper{ext}"
    # Remove other wallpaper.* so resolve is unambiguous
    for old in UI_DIR.glob("wallpaper.*"):
        try:
            old.unlink()
        except OSError:
            pass
    shutil.copy2(src, dest)
    prefs = load_prefs()
    prefs["wallpaper"] = str(dest)
    save_prefs(prefs)
    return dest


def clear_wallpaper() -> None:
    prefs = load_prefs()
    prefs["wallpaper"] = ""
    save_prefs(prefs)
    for old in UI_DIR.glob("wallpaper.*"):
        try:
            old.unlink()
        except OSError:
            pass
