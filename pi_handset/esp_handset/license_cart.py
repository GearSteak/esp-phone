"""Paper / e-Reader-style Digivice license carts.

USB carts still carry big media. Paper cards only unlock local ROMs and act as
a single virtual insert: scan to insert, eject before scanning another.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DATA = Path.home() / ".esp-handset"
CARDS_DIR = DATA / "license_cards"
CATALOG_PATH = CARDS_DIR / "catalog.json"
ACTIVE_PATH = CARDS_DIR / "active.json"
OWNED_PATH = CARDS_DIR / "owned.json"

PAYLOAD_PREFIX = "DIGIVICE-CARD"
PAYLOAD_VERSION = "1"

_DEMO_ID = "demo-hello"


@dataclass
class LicenseGame:
    title: str
    system: str
    path: Path


@dataclass
class LicenseCard:
    id: str
    title: str
    games: List[LicenseGame] = field(default_factory=list)
    secret: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActiveLicense:
    card_id: str
    title: str
    inserted_at: float


def cards_dir() -> Path:
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    return CARDS_DIR


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_json(path: Path, data: Any) -> None:
    cards_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def ensure_default_catalog() -> None:
    """Seed a demo card the first time Digivice needs the catalog."""
    cards_dir()
    if CATALOG_PATH.is_file():
        return
    demo_rom = DATA / "roms" / "gb" / "demo_hello.gb"
    catalog = {
        "version": 1,
        "cards": [
            {
                "id": _DEMO_ID,
                "title": "Hello Digivice",
                "secret": "digivice-demo-secret",
                "games": [
                    {
                        "title": "Demo Hello",
                        "system": "gb",
                        "path": "roms/gb/demo_hello.gb",
                    }
                ],
            }
        ],
    }
    _write_json(CATALOG_PATH, catalog)
    # Placeholder note so the path is obvious if the ROM is missing
    try:
        demo_rom.parent.mkdir(parents=True, exist_ok=True)
        tip = demo_rom.parent / "LICENSE_CARD_DEMO.txt"
        if not tip.is_file():
            tip.write_text(
                "Paper-cart demo expects a Game Boy ROM here:\n"
                f"  {demo_rom}\n\n"
                "Copy any .gb/.gbc file to that name to test launch after scanning\n"
                "the demo card (docs/LICENSE_CARDS.md).\n",
                encoding="utf-8",
            )
    except OSError:
        pass


def _resolve_rom(rel: str) -> Path:
    rel = (rel or "").strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError(f"bad rom path: {rel!r}")
    return (DATA / rel).resolve()


def _parse_card(raw: Dict[str, Any]) -> Optional[LicenseCard]:
    cid = str(raw.get("id") or "").strip()
    if not cid:
        return None
    title = str(raw.get("title") or cid).strip() or cid
    secret = str(raw.get("secret") or "").strip()
    games: List[LicenseGame] = []
    block = raw.get("games")
    if isinstance(block, list):
        for g in block:
            if not isinstance(g, dict):
                continue
            system = str(g.get("system") or "").strip().lower()
            path_s = str(g.get("path") or "").strip()
            gtitle = str(g.get("title") or Path(path_s).stem or "Game").strip()
            if not system or not path_s:
                continue
            try:
                path = _resolve_rom(path_s)
            except ValueError:
                continue
            games.append(LicenseGame(title=gtitle, system=system, path=path))
    return LicenseCard(id=cid, title=title, games=games, secret=secret, raw=raw)


def load_catalog() -> List[LicenseCard]:
    ensure_default_catalog()
    data = _read_json(CATALOG_PATH, {})
    cards: List[LicenseCard] = []
    if isinstance(data, dict):
        block = data.get("cards")
        if isinstance(block, list):
            for item in block:
                if isinstance(item, dict):
                    c = _parse_card(item)
                    if c is not None:
                        cards.append(c)
    return cards


def get_card(card_id: str) -> Optional[LicenseCard]:
    want = (card_id or "").strip()
    for c in load_catalog():
        if c.id == want:
            return c
    return None


def encode_payload(card_id: str, *, secret: str = "") -> str:
    """Human/QR payload. Optional HMAC-ish tag when catalog has a secret."""
    cid = (card_id or "").strip()
    if not cid:
        raise ValueError("empty card id")
    if secret:
        tag = hashlib.sha256(f"{secret}:{cid}".encode("utf-8")).hexdigest()[:10]
        return f"{PAYLOAD_PREFIX}:{PAYLOAD_VERSION}:{cid}:{tag}"
    return f"{PAYLOAD_PREFIX}:{PAYLOAD_VERSION}:{cid}"


def parse_payload(text: str) -> Tuple[str, str]:
    """Return (card_id, sig_or_empty). Raises ValueError on bad payload."""
    raw = (text or "").strip()
    # Allow scanning URLs / whitespace noise around the token
    m = re.search(
        rf"{re.escape(PAYLOAD_PREFIX)}:{PAYLOAD_VERSION}:([A-Za-z0-9._\-]+)(?::([0-9a-fA-F]+))?",
        raw,
    )
    if not m:
        raise ValueError("not a Digivice card QR")
    return m.group(1), (m.group(2) or "")


def verify_payload(card_id: str, sig: str, card: LicenseCard) -> bool:
    if not card.secret:
        return True
    if not sig:
        return False
    expect = hashlib.sha256(f"{card.secret}:{card.id}".encode("utf-8")).hexdigest()[:10]
    return sig.lower() == expect.lower()


def owned_ids() -> List[str]:
    data = _read_json(OWNED_PATH, {"ids": []})
    if isinstance(data, dict) and isinstance(data.get("ids"), list):
        return [str(x) for x in data["ids"]]
    return []


def mark_owned(card_id: str) -> None:
    ids = owned_ids()
    if card_id not in ids:
        ids.append(card_id)
        _write_json(OWNED_PATH, {"ids": ids, "updated_at": time.time()})


def active() -> Optional[ActiveLicense]:
    data = _read_json(ACTIVE_PATH, None)
    if not isinstance(data, dict):
        return None
    cid = str(data.get("card_id") or "").strip()
    if not cid:
        return None
    title = str(data.get("title") or cid).strip() or cid
    try:
        inserted = float(data.get("inserted_at") or 0)
    except (TypeError, ValueError):
        inserted = 0.0
    return ActiveLicense(card_id=cid, title=title, inserted_at=inserted)


def active_card() -> Optional[LicenseCard]:
    act = active()
    if act is None:
        return None
    return get_card(act.card_id)


def is_inserted() -> bool:
    return active() is not None


def active_title() -> str:
    act = active()
    return act.title if act else ""


def eject() -> bool:
    """Clear the virtual paper cart. Returns True if something was ejected."""
    if not ACTIVE_PATH.is_file() and active() is None:
        return False
    had = active() is not None
    try:
        if ACTIVE_PATH.is_file():
            ACTIVE_PATH.unlink()
    except OSError:
        _write_json(ACTIVE_PATH, {})
    return had


def insert_from_payload(text: str) -> LicenseCard:
    """Parse QR/text, verify, insert. Raises ValueError with a short reason."""
    card_id, sig = parse_payload(text)
    card = get_card(card_id)
    if card is None:
        raise ValueError(f"unknown card id: {card_id}")
    if not verify_payload(card_id, sig, card):
        raise ValueError("bad card signature")
    act = active()
    if act is not None and act.card_id != card_id:
        raise ValueError(f"eject “{act.title}” first")
    if act is not None and act.card_id == card_id:
        return card  # already inserted
    mark_owned(card_id)
    _write_json(
        ACTIVE_PATH,
        {
            "card_id": card.id,
            "title": card.title,
            "inserted_at": time.time(),
        },
    )
    return card


def gated_rom_map() -> Dict[str, str]:
    """resolved rom path → card_id for every catalog-gated ROM."""
    out: Dict[str, str] = {}
    for card in load_catalog():
        for g in card.games:
            try:
                key = str(g.path.resolve())
            except OSError:
                key = str(g.path)
            out[key] = card.id
    return out


def rom_visible(path: Path) -> bool:
    """Ungated ROMs always visible; gated ones only while their card is inserted."""
    try:
        key = str(path.resolve())
    except OSError:
        key = str(path)
    card_id = gated_rom_map().get(key)
    if not card_id:
        return True
    act = active()
    return act is not None and act.card_id == card_id


def license_games_for_system(system: str) -> List[Tuple[str, Path]]:
    card = active_card()
    if card is None:
        return []
    key = (system or "").strip().lower()
    out: List[Tuple[str, Path]] = []
    for g in card.games:
        if g.system != key:
            continue
        out.append((g.title, g.path))
    return out


def takeover_games() -> bool:
    """True when a paper cart is inserted and lists at least one game."""
    card = active_card()
    return card is not None and bool(card.games)


def demo_payload() -> str:
    ensure_default_catalog()
    card = get_card(_DEMO_ID)
    if card is None:
        return encode_payload(_DEMO_ID)
    return encode_payload(card.id, secret=card.secret)
