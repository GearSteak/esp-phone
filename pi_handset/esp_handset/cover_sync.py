"""Download emulator box art from libretro thumbnails CDN.

Saves into ~/.esp-handset/roms/<folder>/covers/<rom-stem>.png so RomShelf
find_cover() picks them up. Uses directory listings for fuzzy name match.
"""

from __future__ import annotations

import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# Digivice system key / ROM ext → libretro thumbnail system folder name(s)
_LIBRETRO_SYSTEMS = {
    "gb": ("Nintendo - Game Boy", "Nintendo - Game Boy Color"),
    "nes": ("Nintendo - Nintendo Entertainment System",),
    "smsgg": ("Sega - Master System - Mark III", "Sega - Game Gear"),
    "gba": ("Nintendo - Game Boy Advance",),
    "snes": ("Nintendo - Super Nintendo Entertainment System",),
    "genesis": ("Sega - Mega Drive - Genesis",),
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
_UA = "DigiviceCoverSync/1.1 (esp-handset; +https://github.com/GearSteak/esp-phone)"
_BAD = re.compile(r'[&*/:<>?\\|"]')
_LISTING_CACHE: Dict[Tuple[str, str], List[str]] = {}
_LAST_ERR = ""


def libretro_name(stem: str) -> str:
    """ROM stem → Named_Boxarts filename (no .png)."""
    return _BAD.sub("_", stem or "").strip() or stem


def _normalize_key(text: str) -> str:
    """Loose match key — strip tags, punctuation, case."""
    s = Path(text).stem if "." in text else text
    s = re.sub(r"\s*[\(\[].*?[\)\]]", " ", s)
    s = re.sub(r"[^a-zA-Z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip().casefold()


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
    stripped = re.sub(r"\s*[\(\[].*?[\)\]]", "", stem)
    stripped = re.sub(r"\s+", " ", stripped).strip(" -_")
    if stripped:
        add(stripped)
        for region in ("World", "USA", "Europe", "Japan", "En", "UE", "USA, Europe"):
            add(f"{stripped} ({region})")
    return out


def systems_for(rom: Path, system_key: str) -> Tuple[str, ...]:
    ext = rom.suffix.lower()
    by_ext = _EXT_SYSTEM.get(ext)
    if by_ext:
        return by_ext
    return _LIBRETRO_SYSTEMS.get(system_key, ())


def cover_url(system: str, name: str, kind: str = "Named_Boxarts") -> str:
    sys_enc = urllib.parse.quote(system, safe="")
    name_enc = urllib.parse.quote(f"{name}.png", safe="")
    return f"{_BASE}/{sys_enc}/{kind}/{name_enc}"


def _ssl_ctx() -> ssl.SSLContext:
    try:
        return ssl.create_default_context()
    except Exception:
        return ssl._create_unverified_context()  # type: ignore[attr-defined]


def _http_read(url: str, timeout: float = 18.0) -> Optional[bytes]:
    global _LAST_ERR
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as resp:
            code = getattr(resp, "status", 200)
            if code >= 400:
                _LAST_ERR = f"HTTP {code}"
                return None
            return resp.read()
    except urllib.error.HTTPError as e:
        _LAST_ERR = f"HTTP {e.code}"
        return None
    except urllib.error.URLError as e:
        _LAST_ERR = str(getattr(e, "reason", e))[:80]
        return None
    except (TimeoutError, OSError) as e:
        _LAST_ERR = str(e)[:80]
        return None


def _http_get(url: str, timeout: float = 18.0) -> Optional[bytes]:
    data = _http_read(url, timeout=timeout)
    if not data:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:2] == b"\xff\xd8":
        return data
    if len(data) >= 64 and b"<html" not in data[:800].lower():
        return data
    _LAST_ERR = "not an image"
    return None


def _fetch_listing(system: str, kind: str = "Named_Boxarts") -> List[str]:
    key = (system, kind)
    if key in _LISTING_CACHE:
        return _LISTING_CACHE[key]
    sys_enc = urllib.parse.quote(system, safe="")
    kind_enc = urllib.parse.quote(kind, safe="")
    url = f"{_BASE}/{sys_enc}/{kind_enc}/?F=0"
    raw = _http_read(url)
    names: List[str] = []
    if raw:
        text = raw.decode("utf-8", errors="replace")
        for m in re.finditer(r'href="([^"]+\.(?:png|PNG))"', text):
            fn = urllib.parse.unquote(m.group(1).split("/")[-1])
            if fn and fn not in ("../",):
                names.append(fn)
        if not names:
            for line in text.splitlines():
                line = line.strip()
                if line.endswith(".png") and not line.startswith("-"):
                    names.append(line)
    _LISTING_CACHE[key] = names
    return names


def _best_listing_match(stem: str, listing: List[str]) -> Optional[str]:
    if not listing:
        return None
    want = _normalize_key(stem)
    if not want:
        return None
    best_name = ""
    best_score = 0.0
    for fn in listing:
        base = fn[:-4] if fn.lower().endswith(".png") else fn
        norm = _normalize_key(base)
        if not norm:
            continue
        if norm == want:
            return base
        score = SequenceMatcher(None, want, norm).ratio()
        len_ratio = min(len(want), len(norm)) / max(len(want), len(norm), 1)
        score *= len_ratio
        # Token overlap boost (Pokemon Red vs Pokemon Red Version)
        want_toks = set(want.split())
        norm_toks = set(norm.split())
        if want_toks and want_toks <= norm_toks:
            score = max(score, 0.88)
        if score > best_score:
            best_score = score
            best_name = base
    if best_score >= 0.78 and best_name:
        return best_name
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

    dest = covers_dir(data_root, folder) / f"{rom.stem}.png"
    kinds = ("Named_Boxarts", "Named_Titles", "Named_Snaps")

    # 1) Direct URL tries (fast path)
    for sys_name in systems:
        for kind in kinds:
            for name in _name_candidates(rom.stem):
                blob = _http_get(cover_url(sys_name, name, kind))
                if blob:
                    try:
                        dest.write_bytes(blob)
                    except OSError as e:
                        return False, str(e)[:40]
                    return True, "ok"

    # 2) Directory listing fuzzy match (handles odd dump names)
    for sys_name in systems:
        for kind in kinds:
            listing = _fetch_listing(sys_name, kind)
            hit = _best_listing_match(rom.stem, listing)
            if not hit:
                continue
            blob = _http_get(cover_url(sys_name, hit, kind))
            if blob:
                try:
                    dest.write_bytes(blob)
                except OSError as e:
                    return False, str(e)[:40]
                return True, "fuzzy"

    err = _LAST_ERR or "not found"
    return False, err


ProgressCb = Callable[[int, int, str], None]


def sync_covers(
    roms: Sequence[Path],
    *,
    system_key: str,
    folder: str,
    data_root: Path,
    overwrite: bool = False,
    on_progress: Optional[ProgressCb] = None,
) -> Tuple[int, int, int, str]:
    """
    Sync covers for a ROM list.
    Returns (downloaded, already_had, failed, last_error_hint).
    """
    global _LAST_ERR
    _LAST_ERR = ""
    local = [p for p in roms if p.is_file()]
    n = len(local)
    got = had = fail = 0
    last_fail = ""
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
            last_fail = reason
    hint = last_fail or _LAST_ERR or ""
    if fail and not got and not had and not hint:
        hint = "check Wi‑Fi"
    return got, had, fail, hint


def last_error() -> str:
    return _LAST_ERR
