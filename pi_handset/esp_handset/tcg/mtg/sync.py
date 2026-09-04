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
ACCEPT = "application/json;q=0.9,*/*;q=0.8"
CHUNK = 256 * 1024


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = ssl.create_default_context()
        return ctx


def _headers() -> dict:
    # Scryfall rejects requests missing Accept (HTTP 400) or using a default UA.
    return {"User-Agent": USER_AGENT, "Accept": ACCEPT}


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    detail = ""
    try:
        body = exc.read().decode("utf-8", errors="replace")
        payload = json.loads(body)
        if isinstance(payload, dict):
            detail = str(payload.get("details") or payload.get("code") or "")[:180]
    except Exception:
        detail = ""
    if detail:
        return f"HTTP {exc.code}: {detail}"
    return f"HTTP {exc.code} {exc.reason}"


def _request(url: str, *, timeout: float = 120.0) -> bytes:
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(_http_error_message(e)) from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"network error: {e.reason}") from e


def _download_file(
    url: str,
    dest: Path,
    *,
    progress: Optional[Callable[[str, int], None]] = None,
    min_bytes: int = 1_000_000,
) -> None:
    cards_db.data_dir()
    tmp = dest.with_suffix(dest.suffix + ".part")
    if tmp.is_file():
        tmp.unlink()
    req = urllib.request.Request(url, headers=_headers())
    done = 0
    try:
        with urllib.request.urlopen(req, timeout=600, context=_ssl_context()) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
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
    except urllib.error.HTTPError as e:
        raise RuntimeError(_http_error_message(e)) from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"network error: {e.reason}") from e
    if done < min_bytes:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise RuntimeError(f"download too small ({done} bytes) — check Wi‑Fi")
    tmp.replace(dest)


def oracle_bulk_info() -> tuple[str, str]:
    """Return (download_uri, updated_at) for oracle_cards bulk."""
    raw = json.loads(_request(cards_db.SCRYFALL_BULK_URL, timeout=60).decode("utf-8"))
    items = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise RuntimeError("unexpected Scryfall bulk-data response")
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "oracle_cards":
            continue
        uri = str(
            item.get("jsonl_download_uri")
            or item.get("download_uri")
            or ""
        ).strip()
        updated = str(item.get("updated_at") or "").strip()
        if uri:
            return uri, updated
        raise RuntimeError(
            "oracle_cards listing has no download URI "
            f"(keys: {', '.join(sorted(item.keys()))})"
        )
    raise RuntimeError("oracle_cards bulk entry not found")


def oracle_bulk_download_uri() -> str:
    return oracle_bulk_info()[0]


def ensure_database(
    *,
    progress: Optional[Callable[[str, int], None]] = None,
    force: bool = False,
) -> int:
    """Download/index oracle cards if missing or Scryfall updated_at changed."""
    cards_db.data_dir()
    remote_uri = ""
    remote_updated = ""

    if not force and cards_db.is_ready():
        if progress:
            progress("Checking for updates…", 2)
        try:
            remote_uri, remote_updated = oracle_bulk_info()
            local_updated = str(cards_db.meta().get("scryfall_updated_at") or "")
            if remote_updated and local_updated and local_updated == remote_updated:
                n = cards_db.card_count()
                if progress:
                    progress(f"Up to date ({n:,} cards)", 100)
                return n
            if progress:
                progress("Update available…", 4)
        except Exception:
            n = cards_db.card_count()
            if progress:
                progress(f"Offline — using {n:,} cards", 100)
            return n
    else:
        if progress:
            progress("Contacting Scryfall…", 2)
        try:
            remote_uri, remote_updated = oracle_bulk_info()
        except Exception as e:
            raise RuntimeError(f"Scryfall API failed: {type(e).__name__}: {e}") from e

    if not remote_uri:
        try:
            remote_uri, remote_updated = oracle_bulk_info()
        except Exception as e:
            raise RuntimeError(f"Scryfall API failed: {type(e).__name__}: {e}") from e

    bulk = cards_db.BULK_FILE
    local_updated = str(cards_db.meta().get("scryfall_updated_at") or "")
    need_dl = (
        force
        or not bulk.is_file()
        or bulk.stat().st_size < 5_000_000
        or (bool(remote_updated) and local_updated != remote_updated)
    )
    if need_dl:
        if progress:
            progress("Downloading oracle cards (~25 MB)…", 5)
        try:
            _download_file(remote_uri, bulk, progress=progress, min_bytes=5_000_000)
        except Exception as e:
            raise RuntimeError(f"Bulk download failed: {type(e).__name__}: {e}") from e
    elif progress:
        progress("Using cached bulk file…", 40)

    if progress:
        progress("Building search index (slow)…", 42)
    try:
        return cards_db.import_bulk(
            bulk,
            progress=progress,
            scryfall_updated_at=remote_updated,
        )
    except Exception as e:
        raise RuntimeError(f"Index build failed: {type(e).__name__}: {e}") from e


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
