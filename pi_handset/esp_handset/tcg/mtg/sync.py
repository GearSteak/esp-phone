"""Download Scryfall bulk data and card images for offline MTG search."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from esp_handset.tcg.mtg import cards_db

USER_AGENT = "Digivice/1.0 (+https://github.com/GearSteak/esp-phone)"
CHUNK = 256 * 1024


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = ssl.create_default_context()
        return ctx


def _request(url: str, *, timeout: float = 120.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
        return resp.read()


def _download_file(
    url: str,
    dest: Path,
    *,
    progress: Optional[Callable[[str, int], None]] = None,
) -> None:
    cards_db.data_dir()
    tmp = dest.with_suffix(dest.suffix + ".part")
    if tmp.is_file():
        tmp.unlink()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=600, context=_ssl_context()) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with tmp.open("wb") as out:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress:
                    if total > 0:
                        pct = min(39, int(done * 39 / total))
                        mb = done / (1024 * 1024)
                        progress(f"Downloading… {mb:.0f} MB", pct)
                    elif done and done % (2 * 1024 * 1024) < CHUNK:
                        mb = done / (1024 * 1024)
                        progress(f"Downloading… {mb:.0f} MB", 10)
    if done < 1_000_000:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise RuntimeError(f"download too small ({done} bytes) — check Wi‑Fi")
    tmp.replace(dest)


def oracle_bulk_download_uri() -> str:
    raw = json.loads(_request(cards_db.SCRYFALL_BULK_URL, timeout=60).decode("utf-8"))
    items = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise RuntimeError("unexpected Scryfall bulk-data response")
    for item in items:
        if isinstance(item, dict) and item.get("type") == "oracle_cards":
            uri = str(item.get("download_uri") or "")
            if uri:
                return uri
    raise RuntimeError("oracle_cards bulk entry not found")


def ensure_database(
    *,
    progress: Optional[Callable[[str, int], None]] = None,
    force: bool = False,
) -> int:
    """Download Scryfall oracle-cards (if needed) and build SQLite. Returns card count."""
    cards_db.data_dir()
    if not force and cards_db.is_ready():
        n = cards_db.card_count()
        if progress:
            progress(f"Database ready ({n:,} cards)", 100)
        return n

    if progress:
        progress("Contacting Scryfall…", 2)
    try:
        uri = oracle_bulk_download_uri()
    except Exception as e:
        raise RuntimeError(f"Scryfall API failed: {e}") from e

    need_dl = (
        force
        or not cards_db.BULK_JSON.is_file()
        or cards_db.BULK_JSON.stat().st_size < 1_000_000
    )
    if need_dl:
        if progress:
            progress("Downloading oracle cards (~120 MB)…", 5)
        try:
            _download_file(uri, cards_db.BULK_JSON, progress=progress)
        except Exception as e:
            raise RuntimeError(f"Bulk download failed: {e}") from e
    elif progress:
        progress("Using cached bulk JSON…", 40)

    if progress:
        progress("Building search index (slow)…", 42)
    try:
        return cards_db.import_bulk(cards_db.BULK_JSON, progress=progress)
    except Exception as e:
        raise RuntimeError(f"Index build failed: {e}") from e


def download_card_image(
    card_id: str,
    image_url: str,
    *,
    progress: Optional[Callable[[str, int], None]] = None,
) -> Optional[Path]:
    if not image_url:
        return None
    cards_db.data_dir()
    safe = card_id.replace("/", "_")
    dest = cards_db.IMAGES_DIR / f"{safe}.jpg"
    if dest.is_file() and dest.stat().st_size > 1024:
        cards_db.set_image_path(card_id, str(dest))
        return dest
    try:
        if progress:
            progress("Downloading art…", 50)
        data = _request(image_url, timeout=90)
        dest.write_bytes(data)
        cards_db.set_image_path(card_id, str(dest))
        return dest
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as e:
        if progress:
            progress(f"Image failed: {e}", 0)
        return None
