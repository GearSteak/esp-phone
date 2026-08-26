"""Download emulator box art from libretro thumbnails CDN.

Saves into ~/.esp-handset/roms/<folder>/covers/<rom-stem>.png so RomShelf
find_cover() picks them up. Names follow RetroArch Named_Boxarts rules.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

# Digivice system key / ROM ext → libretro thumbnail system folder name(s)
_LIBRETRO_SYSTEMS = {
    "gb": ("Nintendo - Game Boy", "Nintendo - Game Boy Color"),
    "nes": ("Nintendo - Nintendo Entertainment System",),
    "smsgg": ("Sega - Master System - Mark III", "Sega - Game Gear"),
    "gba": ("Nintendo - Game Boy Advance",),
    "snes": ("Nintendo - Super Nintendo Entertainment System",),
    "genesis": ("Sega - Mega Drive - Genesis",),
    "ps1": ("Sony - PlayStation",),
}

_EXT_SYSTEM = {
    ".gb": ("Nintendo - Game Boy",),
    ".gbc": ("Nintendo - Game Boy Color", "Nintendo - Game Boy"),
    ".sgb": ("Nintendo - Game Boy",),
    ".nes": ("Nintendo - Nintendo Entertainment System",),
    ".fds": ("Nintendo - Nintendo Entertainment System",),
    ".sms": ("Sega - Master System - Mark III",),
    ".gg": ("Sega - Game Gear",),
    ".sg": ("Sega - Master System - Mark III",),
    ".gba": ("Nintendo - Game Boy Advance",),
    ".sfc": ("Nintendo - Super Nintendo Entertainment System",),
    ".smc": ("Nintendo - Super Nintendo Entertainment System",),
    ".md": ("Sega - Mega Drive - Genesis",),
    ".gen": ("Sega - Mega Drive - Genesis",),
    ".smd": ("Sega - Mega Drive - Genesis",),
    ".bin": ("Sega - Mega Drive - Genesis", "Sony - PlayStation"),
    ".cue": ("Sony - PlayStation",),
    ".pbp": ("Sony - PlayStation",),
    ".chd": ("Sony - PlayStation",),
}

_BASE = "https://thumbnails.libretro.com"
_UA = "DigiviceCoverSync/1.0 (esp-handset; +https://github.com/GearSteak/esp-phone)"
# RetroArch: replace these with underscore in Named_* filenames
_BAD = re.compile(r'[&*/:<>?\\|"]')


def libretro_name(stem: str) -> str:
    """ROM stem → Named_Boxarts filename (no .png)."""
    return _BAD.sub("_", stem or "").strip() or stem


def _name_candidates(stem: str) -> List[str]:
    """Exact stem first, then without region/dump tags, then common region variants."""
    out: List[str] = []
    seen = set()

    def add(s: str) -> None:
        n = libretro_name(s)
        if n and n not in seen:
            seen.add(n)
            out.append(n)

    add(stem)
    # Strip (...) and [...] regions / dump tags
    stripped = re.sub(r"\s*[\(\[].*?[\)\]]", "", stem)
    stripped = re.sub(r"\s+", " ", stripped).strip(" -_")
    if stripped:
        add(stripped)
        for region in ("World", "USA", "Europe", "Japan", "En", "UE"):
            add(f"{stripped} ({region})")
    return out


def systems_for(rom: Path, system_key: str) -> Tuple[str, ...]:
    ext = rom.suffix.lower()
    by_ext = _EXT_SYSTEM.get(ext)
    if by_ext:
        return by_ext
    return _LIBRETRO_SYSTEMS.get(system_key, ())


def cover_url(system: str, name: str, kind: str = "Named_Boxarts") -> str:
    # Path segments: encode but keep spaces as %20 (not +)
    sys_enc = urllib.parse.quote(system, safe="")
    name_enc = urllib.parse.quote(f"{name}.png", safe="")
    return f"{_BASE}/{sys_enc}/{kind}/{name_enc}"


def _http_get(url: str, timeout: float = 12.0) -> Optional[bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) >= 400:
                return None
            data = resp.read()
            if not data or len(data) < 64:
                return None
            # PNG or JPEG magic
            if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:2] == b"\xff\xd8":
                return data
            return None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None


def covers_dir(data_root: Path, folder: str) -> Path:
    d = data_root / "roms" / folder / "covers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def existing_cover(rom: Path, folder: str, data_root: Path) -> Optional[Path]:
    from esp_handset.rom_shelf import find_cover

    return find_cover(rom, folder, data_root)


def fetch_one(
    rom: Path,
    *,
    system_key: str,
    folder: str,
    data_root: Path,
    overwrite: bool = False,
) -> Tuple[bool, str]:
    """Download box art for one ROM. Returns (ok, message)."""
    if not rom.is_file():
        return False, "missing"
    if not overwrite and existing_cover(rom, folder, data_root):
        return True, "have"
    systems = systems_for(rom, system_key)
    if not systems:
        return False, "no system map"
    names = _name_candidates(rom.stem)
    kinds = ("Named_Boxarts", "Named_Titles")
    for sys_name in systems:
        for kind in kinds:
            for name in names:
                url = cover_url(sys_name, name, kind)
                blob = _http_get(url)
                if not blob:
                    continue
                dest = covers_dir(data_root, folder) / f"{rom.stem}.png"
                try:
                    dest.write_bytes(blob)
                except OSError as e:
                    return False, str(e)[:40]
                return True, "ok"
    return False, "not found"


ProgressCb = Callable[[int, int, str], None]


def sync_covers(
    roms: Sequence[Path],
    *,
    system_key: str,
    folder: str,
    data_root: Path,
    overwrite: bool = False,
    on_progress: Optional[ProgressCb] = None,
) -> Tuple[int, int, int]:
    """
    Sync covers for a ROM list.
    Returns (downloaded, already_had, failed).
    """
    local = [p for p in roms if p.is_file()]
    n = len(local)
    got = had = fail = 0
    for i, rom in enumerate(local):
        if on_progress:
            try:
                on_progress(i + 1, n, rom.name)
            except Exception:
                pass
        ok, reason = fetch_one(
            rom,
            system_key=system_key,
            folder=folder,
            data_root=data_root,
            overwrite=overwrite,
        )
        if ok and reason == "have":
            had += 1
        elif ok:
            got += 1
        else:
            fail += 1
    return got, had, fail
