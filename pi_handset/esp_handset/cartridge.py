"""USB Digivice cartridges — mount discovery + cartridge.json manifest."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

MANIFEST_NAME = "cartridge.json"
VALID_KINDS = frozenset({"games", "music", "movies", "tv", "audiobooks"})
VALID_SYSTEMS = frozenset(
    {"gb", "nes", "smsgg", "gba", "snes", "genesis", "ps1"}
)

# Where the OS automounts removable media
_MOUNT_ROOTS = (
    Path("/media"),
    Path("/run/media"),
    Path("/mnt"),
)

_CACHE: Optional["CartridgeState"] = None
_CACHE_AT = 0.0
_CACHE_TTL = 2.0


@dataclass
class MenuAssets:
    background: Optional[Path] = None
    logo: Optional[Path] = None
    music: Optional[Path] = None
    select_sound: Optional[Path] = None


@dataclass
class CartGame:
    title: str
    system: str
    path: Path


@dataclass
class CartExtra:
    title: str
    path: Path


@dataclass
class CartScene:
    """Chapter / scene marker — start time in seconds."""

    title: str
    start_sec: float


@dataclass
class CartMovie:
    title: str
    path: Path
    menu: MenuAssets = field(default_factory=MenuAssets)
    extras: List[CartExtra] = field(default_factory=list)
    scenes: List[CartScene] = field(default_factory=list)
    subtitles: List[Path] = field(default_factory=list)


@dataclass
class CartEpisode:
    title: str
    path: Path


@dataclass
class CartSeason:
    title: str
    episodes: List[CartEpisode] = field(default_factory=list)


@dataclass
class CartShow:
    title: str
    autoplay: bool
    menu: MenuAssets = field(default_factory=MenuAssets)
    seasons: List[CartSeason] = field(default_factory=list)


@dataclass
class CartAlbum:
    title: str
    path: Path
    menu: MenuAssets = field(default_factory=MenuAssets)


@dataclass
class Cartridge:
    root: Path
    title: str
    kinds: Set[str]
    menu: MenuAssets = field(default_factory=MenuAssets)
    logo: Optional[Path] = None
    games: List[CartGame] = field(default_factory=list)
    movies: List[CartMovie] = field(default_factory=list)
    tv: List[CartShow] = field(default_factory=list)
    music: List[CartAlbum] = field(default_factory=list)
    audiobooks: List[CartAlbum] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def has_kind(self, kind: str) -> bool:
        return kind in self.kinds

    def games_for_system(self, system: str) -> List[CartGame]:
        key = system.lower()
        return [g for g in self.games if g.system == key and g.path.is_file()]


@dataclass
class CartridgeState:
    cart: Optional[Cartridge] = None
    mount: Optional[Path] = None
    error: str = ""


def _resolve(root: Path, rel: str) -> Path:
    rel = (rel or "").strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError(f"bad path: {rel!r}")
    return (root / rel).resolve()


def _menu_assets(root: Path, block: Any) -> MenuAssets:
    if not isinstance(block, dict):
        return MenuAssets()
    out = MenuAssets()
    for key, attr in (
        ("background", "background"),
        ("logo", "logo"),
        ("music", "music"),
        ("select_sound", "select_sound"),
    ):
        raw = block.get(key)
        if isinstance(raw, str) and raw.strip():
            try:
                p = _resolve(root, raw)
                setattr(out, attr, p)
            except ValueError:
                pass
    return out


def _parse_timecode(raw: Any) -> Optional[float]:
    """Accept seconds (number/str) or H:MM:SS / M:SS."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return max(0.0, float(raw))
    s = str(raw).strip().lower()
    if not s:
        return None
    if s.endswith("s") and ":" not in s:
        try:
            return max(0.0, float(s[:-1]))
        except ValueError:
            return None
    if ":" in s:
        parts = s.split(":")
        try:
            nums = [float(p) for p in parts]
        except ValueError:
            return None
        if len(nums) == 3:
            return max(0.0, nums[0] * 3600 + nums[1] * 60 + nums[2])
        if len(nums) == 2:
            return max(0.0, nums[0] * 60 + nums[1])
        return None
    try:
        return max(0.0, float(s))
    except ValueError:
        return None


def _parse_subtitles(root: Path, block: Any) -> List[Path]:
    """``subtitles``: string path, list of paths, or list of {path} objects."""
    out: List[Path] = []
    if block is None:
        return out
    items: List[Any]
    if isinstance(block, str):
        items = [block]
    elif isinstance(block, list):
        items = block
    else:
        return out
    for item in items:
        rel = ""
        if isinstance(item, str):
            rel = item.strip()
        elif isinstance(item, dict):
            rel = str(item.get("path") or "").strip()
        if not rel:
            continue
        try:
            p = _resolve(root, rel)
        except ValueError:
            continue
        if p.is_file():
            out.append(p)
    return out


def _parse_scenes(block: Any) -> List[CartScene]:
    out: List[CartScene] = []
    if not isinstance(block, list):
        return out
    for i, entry in enumerate(block):
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or f"Scene {i + 1}").strip()
        start = _parse_timecode(
            entry.get("time", entry.get("start", entry.get("at")))
        )
        if start is None:
            continue
        out.append(CartScene(title=title, start_sec=start))
    return out


def _resolve_logo(root: Path, data: Dict[str, Any], menu: MenuAssets) -> Optional[Path]:
    """Logo for DVD menu: JSON logo → menu.logo → menu/logo.png → logo.png."""
    raw = data.get("logo")
    if isinstance(raw, str) and raw.strip():
        try:
            p = _resolve(root, raw.strip())
            if p.is_file():
                return p
        except ValueError:
            pass
    if menu.logo is not None and menu.logo.is_file():
        return menu.logo
    for rel in ("menu/logo.png", "menu/logo.jpg", "logo.png", "logo.jpg"):
        p = root / rel
        if p.is_file():
            return p
    return None


def _parse_manifest(root: Path, data: Dict[str, Any]) -> Cartridge:
    title = str(data.get("title") or root.name or "Cartridge").strip()
    kinds_raw = data.get("kinds") or []
    if not isinstance(kinds_raw, list):
        kinds_raw = []
    kinds = {str(k).strip().lower() for k in kinds_raw if str(k).strip()}
    kinds &= VALID_KINDS
    if not kinds:
        # Infer from sections if author omitted kinds
        if data.get("games"):
            kinds.add("games")
        if data.get("movies"):
            kinds.add("movies")
        if data.get("tv"):
            kinds.add("tv")
        if data.get("music"):
            kinds.add("music")
        if data.get("audiobooks"):
            kinds.add("audiobooks")

    menu = _menu_assets(root, data.get("menu"))
    cart = Cartridge(
        root=root,
        title=title,
        kinds=kinds,
        menu=menu,
        logo=_resolve_logo(root, data, menu),
        raw=data,
    )

    for entry in data.get("games") or []:
        if not isinstance(entry, dict):
            continue
        sys_key = str(entry.get("system") or "").strip().lower()
        rel = str(entry.get("path") or "").strip()
        gtitle = str(entry.get("title") or Path(rel).stem or "Game").strip()
        if sys_key not in VALID_SYSTEMS or not rel:
            continue
        try:
            path = _resolve(root, rel)
        except ValueError:
            continue
        cart.games.append(CartGame(title=gtitle, system=sys_key, path=path))

    for entry in data.get("movies") or []:
        if not isinstance(entry, dict):
            continue
        rel = str(entry.get("path") or "").strip()
        mtitle = str(entry.get("title") or Path(rel).stem or "Movie").strip()
        if not rel:
            continue
        try:
            path = _resolve(root, rel)
        except ValueError:
            continue
        extras: List[CartExtra] = []
        for ex in entry.get("extras") or []:
            if not isinstance(ex, dict):
                continue
            er = str(ex.get("path") or "").strip()
            et = str(ex.get("title") or Path(er).stem or "Extra").strip()
            if not er:
                continue
            try:
                ep = _resolve(root, er)
            except ValueError:
                continue
            extras.append(CartExtra(title=et, path=ep))
        cart.movies.append(
            CartMovie(
                title=mtitle,
                path=path,
                menu=_menu_assets(root, entry.get("menu")),
                extras=extras,
                scenes=_parse_scenes(entry.get("scenes")),
                subtitles=_parse_subtitles(
                    root, entry.get("subtitles", entry.get("subs"))
                ),
            )
        )

    for entry in data.get("tv") or []:
        if not isinstance(entry, dict):
            continue
        stitle = str(entry.get("title") or "Show").strip()
        autoplay = bool(entry.get("autoplay", True))
        show = CartShow(
            title=stitle,
            autoplay=autoplay,
            menu=_menu_assets(root, entry.get("menu")),
        )
        for season in entry.get("seasons") or []:
            if not isinstance(season, dict):
                continue
            se_title = str(season.get("title") or "Season").strip()
            cs = CartSeason(title=se_title)
            for ep in season.get("episodes") or []:
                if not isinstance(ep, dict):
                    continue
                er = str(ep.get("path") or "").strip()
                et = str(ep.get("title") or Path(er).stem or "Episode").strip()
                if not er:
                    continue
                try:
                    path = _resolve(root, er)
                except ValueError:
                    continue
                cs.episodes.append(CartEpisode(title=et, path=path))
            if cs.episodes:
                show.seasons.append(cs)
        if show.seasons:
            cart.tv.append(show)

    def _albums(key: str) -> List[CartAlbum]:
        out: List[CartAlbum] = []
        for entry in data.get(key) or []:
            if not isinstance(entry, dict):
                continue
            rel = str(entry.get("path") or "").strip()
            atitle = str(entry.get("title") or Path(rel).name or "Album").strip()
            if not rel:
                continue
            try:
                path = _resolve(root, rel)
            except ValueError:
                continue
            out.append(
                CartAlbum(
                    title=atitle,
                    path=path,
                    menu=_menu_assets(root, entry.get("menu")),
                )
            )
        return out

    cart.music = _albums("music")
    cart.audiobooks = _albums("audiobooks")
    return cart


def find_mounts() -> List[Path]:
    found: List[Path] = []
    seen: Set[str] = set()
    for base in _MOUNT_ROOTS:
        if not base.is_dir():
            continue
        try:
            for child in base.iterdir():
                if not child.is_dir():
                    continue
                # /media/user/DIGIVICE or /media/DIGIVICE
                candidates = [child]
                if child.is_dir():
                    try:
                        for sub in child.iterdir():
                            if sub.is_dir():
                                candidates.append(sub)
                    except OSError:
                        pass
                for mount in candidates:
                    manifest = mount / MANIFEST_NAME
                    if not manifest.is_file():
                        continue
                    key = str(mount.resolve())
                    if key in seen:
                        continue
                    seen.add(key)
                    found.append(mount)
        except OSError:
            continue
    found.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return found


def load_at(root: Path) -> Cartridge:
    manifest = root / MANIFEST_NAME
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("cartridge.json must be a JSON object")
    return _parse_manifest(root.resolve(), data)


def refresh(*, force: bool = False) -> CartridgeState:
    global _CACHE, _CACHE_AT
    now = time.monotonic()
    if not force and _CACHE is not None and (now - _CACHE_AT) < _CACHE_TTL:
        return _CACHE

    mounts = find_mounts()
    if not mounts:
        _CACHE = CartridgeState(cart=None, mount=None, error="")
        _CACHE_AT = now
        return _CACHE

    root = mounts[0]
    try:
        cart = load_at(root)
        _CACHE = CartridgeState(cart=cart, mount=root, error="")
    except Exception as e:
        _CACHE = CartridgeState(cart=None, mount=root, error=str(e))
    _CACHE_AT = now
    return _CACHE


def current() -> Optional[Cartridge]:
    return refresh().cart


def takeover_games() -> bool:
    c = current()
    return c is not None and c.has_kind("games")


def takeover_media_kind(kind: str) -> bool:
    c = current()
    return c is not None and c.has_kind(kind)


def cart_label() -> str:
    st = refresh()
    if st.cart is not None:
        return st.cart.title
    if st.error and st.mount:
        return "Cart error"
    return ""


def invalidate_cache() -> None:
    global _CACHE, _CACHE_AT
    _CACHE = None
    _CACHE_AT = 0.0
