"""Local MTG card database (Scryfall oracle-cards bulk → SQLite)."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

DATA_DIR = Path(
    os.environ.get("DIGI_MTG_DATA", str(Path.home() / ".esp-handset" / "tcg" / "mtg"))
)
DB_PATH = DATA_DIR / "cards.sqlite"
IMAGES_DIR = DATA_DIR / "images"
# Scryfall now ships gzipped JSONL (~25 MB); legacy JSON array still importable.
BULK_FILE = DATA_DIR / "oracle_cards.jsonl.gz"
BULK_JSON = BULK_FILE  # back-compat alias used by sync
META_PATH = DATA_DIR / "meta.json"

SCRYFALL_BULK_URL = "https://api.scryfall.com/bulk-data"


@dataclass
class Card:
    id: str
    name: str
    mana_cost: str
    type_line: str
    oracle_text: str
    power: str
    toughness: str
    loyalty: str
    image_url: str
    image_path: str

    def display_text(self) -> str:
        lines = [self.name]
        if self.mana_cost:
            lines.append(self.mana_cost)
        if self.type_line:
            lines.append(self.type_line)
        lines.append("")
        if self.oracle_text:
            lines.append(self.oracle_text)
        stats = []
        if self.power or self.toughness:
            stats.append(f"{self.power or '*'}/{self.toughness or '*'}")
        if self.loyalty:
            stats.append(f"Loyalty {self.loyalty}")
        if stats:
            lines.append("")
            lines.append(" · ".join(stats))
        return "\n".join(lines)


def data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def card_count() -> int:
    try:
        if not DB_PATH.is_file() or DB_PATH.stat().st_size < 4096:
            return 0
    except OSError:
        return 0
    try:
        with _connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM cards").fetchone()
            return int(row[0]) if row else 0
    except sqlite3.Error:
        return 0


def is_ready() -> bool:
    """True only when a real Scryfall index exists (not an empty shell DB)."""
    return card_count() >= 1000


def meta() -> dict:
    try:
        if META_PATH.is_file():
            return json.loads(META_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _connect() -> sqlite3.Connection:
    data_dir()
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cards (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            mana_cost TEXT,
            type_line TEXT,
            oracle_text TEXT,
            power TEXT,
            toughness TEXT,
            loyalty TEXT,
            image_url TEXT,
            image_path TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name COLLATE NOCASE);
        """
    )


def _row_to_card(row: sqlite3.Row) -> Card:
    return Card(
        id=str(row["id"]),
        name=str(row["name"] or ""),
        mana_cost=str(row["mana_cost"] or ""),
        type_line=str(row["type_line"] or ""),
        oracle_text=str(row["oracle_text"] or ""),
        power=str(row["power"] or ""),
        toughness=str(row["toughness"] or ""),
        loyalty=str(row["loyalty"] or ""),
        image_url=str(row["image_url"] or ""),
        image_path=str(row["image_path"] or ""),
    )


def get_card(card_id: str) -> Optional[Card]:
    if not is_ready():
        return None
    with _connect() as conn:
        row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        return _row_to_card(row) if row else None


def search(query: str, *, limit: int = 40) -> List[Card]:
    q = (query or "").strip()
    if not q or not is_ready():
        return []
    like = f"%{q}%"
    prefix = f"{q}%"
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM cards
            WHERE name LIKE ? COLLATE NOCASE
               OR oracle_text LIKE ? COLLATE NOCASE
               OR type_line LIKE ? COLLATE NOCASE
            ORDER BY
                CASE WHEN name LIKE ? COLLATE NOCASE THEN 0
                     WHEN name LIKE ? COLLATE NOCASE THEN 1
                     ELSE 2 END,
                name COLLATE NOCASE
            LIMIT ?
            """,
            (like, like, like, prefix, like, int(limit)),
        ).fetchall()
    return [_row_to_card(r) for r in rows]


def _card_fields(raw: dict) -> tuple[str, str, str, str, str, str, str, str]:
    name = str(raw.get("name") or "")
    mana = str(raw.get("mana_cost") or "")
    type_line = str(raw.get("type_line") or "")
    oracle = str(raw.get("oracle_text") or "")
    power = str(raw.get("power") or "")
    toughness = str(raw.get("toughness") or "")
    loyalty = str(raw.get("loyalty") or "")
    image_url = ""

    faces = raw.get("card_faces")
    if isinstance(faces, list) and faces:
        parts: List[str] = []
        for face in faces:
            if not isinstance(face, dict):
                continue
            fn = str(face.get("name") or "")
            ft = str(face.get("type_line") or "")
            fo = str(face.get("oracle_text") or "")
            block = "\n".join(x for x in (fn, ft, fo) if x)
            if block:
                parts.append(block)
            if not image_url:
                uris = face.get("image_uris") or {}
                if isinstance(uris, dict):
                    image_url = str(
                        uris.get("normal") or uris.get("large") or uris.get("small") or ""
                    )
            if not mana and face.get("mana_cost"):
                mana = str(face.get("mana_cost"))
            if not power and face.get("power"):
                power = str(face.get("power"))
            if not toughness and face.get("toughness"):
                toughness = str(face.get("toughness"))
            if not loyalty and face.get("loyalty"):
                loyalty = str(face.get("loyalty"))
        if parts:
            oracle = "\n\n".join(parts)
    else:
        uris = raw.get("image_uris") or {}
        if isinstance(uris, dict):
            image_url = str(
                uris.get("normal") or uris.get("large") or uris.get("small") or ""
            )

    return name, mana, type_line, oracle, power, toughness, loyalty, image_url


def _iter_bulk_cards(json_path: Path):
    """Yield card dicts from Scryfall bulk: .jsonl.gz, .jsonl, or legacy JSON array."""
    name = json_path.name.lower()
    if name.endswith(".jsonl.gz") or name.endswith(".gz"):
        import gzip

        with gzip.open(json_path, "rt", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                if isinstance(raw, dict):
                    yield raw
        return

    if name.endswith(".jsonl"):
        with json_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                if isinstance(raw, dict):
                    yield raw
        return

    # Legacy: single JSON array
    with json_path.open(encoding="utf-8") as fh:
        cards = json.load(fh)
    if not isinstance(cards, list):
        raise ValueError("bulk JSON must be a list of cards or JSONL")
    for raw in cards:
        if isinstance(raw, dict):
            yield raw


def import_bulk(
    json_path: Path,
    *,
    progress: Optional[Callable[[str, int], None]] = None,
) -> int:
    """Parse Scryfall oracle-cards bulk into SQLite. Returns card count."""
    data_dir()
    if not json_path.is_file():
        raise FileNotFoundError(str(json_path))

    if progress:
        progress("Opening bulk file…", 42)

    tmp = DB_PATH.with_suffix(".sqlite.tmp")
    if tmp.is_file():
        tmp.unlink()

    conn = sqlite3.connect(str(tmp), timeout=60)
    total = 0
    try:
        _schema(conn)
        conn.execute("DELETE FROM cards")
        batch: list[tuple] = []
        for i, raw in enumerate(_iter_bulk_cards(json_path)):
            cid = str(raw.get("id") or "")
            if not cid:
                continue
            name, mana, type_line, oracle, power, toughness, loyalty, image_url = _card_fields(
                raw
            )
            batch.append(
                (
                    cid,
                    name,
                    mana,
                    type_line,
                    oracle,
                    power,
                    toughness,
                    loyalty,
                    image_url,
                    "",
                )
            )
            total += 1
            if len(batch) >= 500:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO cards
                    (id, name, mana_cost, type_line, oracle_text, power, toughness,
                     loyalty, image_url, image_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    batch,
                )
                conn.commit()
                batch.clear()
            if progress and i % 400 == 0:
                # ~34k oracle cards typical; soft ramp 42→95 while streaming
                progress(f"Indexing {total:,}…", min(95, 42 + (total // 500)))
        if batch:
            conn.executemany(
                """
                INSERT OR REPLACE INTO cards
                (id, name, mana_cost, type_line, oracle_text, power, toughness,
                 loyalty, image_url, image_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch,
            )
            conn.commit()
    finally:
        conn.close()

    if total < 1000:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise RuntimeError(f"index too small ({total} cards) — bulk file may be corrupt")

    if DB_PATH.is_file():
        DB_PATH.unlink()
    tmp.replace(DB_PATH)

    META_PATH.write_text(
        json.dumps(
            {
                "imported_at": time.time(),
                "card_count": total,
                "source": str(json_path.name),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if progress:
        progress(f"Ready — {total:,} cards", 100)
    return total


def set_image_path(card_id: str, path: str) -> None:
    if not is_ready():
        return
    with _connect() as conn:
        conn.execute(
            "UPDATE cards SET image_path = ? WHERE id = ?",
            (path, card_id),
        )
        conn.commit()


def image_file_for(card: Card) -> Optional[Path]:
    if card.image_path:
        p = Path(card.image_path)
        if p.is_file():
            return p
    if not card.image_url:
        return None
    safe = card.id.replace("/", "_")
    dest = IMAGES_DIR / f"{safe}.jpg"
    return dest if dest.is_file() else None
