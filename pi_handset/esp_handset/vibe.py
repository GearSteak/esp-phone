"""MCP23017 vibration motor (GPB7) for haptic notification alerts."""

from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_async_lock = threading.Lock()
_async_active = False


def _vibes_enabled() -> bool:
    try:
        from esp_handset import store

        prefs = store.load("sounds.json", {"enabled": True, "profile": "Normal"})
        if prefs.get("profile") == "Silent":
            return False
        return bool(prefs.get("enabled", True))
    except Exception:
        return True


def _set_vibe(on: bool) -> bool:
    try:
        from esp_handset import mcp23017

        return bool(mcp23017.set_output("VIBE", on))
    except Exception:
        return False


def pulse(ms: int = 150, *, force: bool = False) -> bool:
    """Single vibration pulse. Returns False if muted or MCP unavailable."""
    if not force and not _vibes_enabled():
        return False
    ms = max(30, min(1200, int(ms)))
    with _lock:
        if not _set_vibe(True):
            return False
        try:
            time.sleep(ms / 1000.0)
        finally:
            _set_vibe(False)
    return True


def chirp(*, force: bool = False) -> bool:
    return pulse(140, force=force)


def alert(*, force: bool = False) -> bool:
    if not force and not _vibes_enabled():
        return False
    with _lock:
        ok = pulse(220, force=True)
        time.sleep(0.07)
        ok = pulse(300, force=True) or ok
        return ok


def vibe_async(kind: str = "alert", *, force: bool = False) -> None:
    """Fire-and-forget haptic pattern (chirp | alert)."""
    global _async_active
    with _async_lock:
        if _async_active:
            return
        _async_active = True

    def _run() -> None:
        global _async_active
        try:
            if kind == "chirp":
                chirp(force=force)
            else:
                alert(force=force)
        except Exception:
            pass
        finally:
            with _async_lock:
                _async_active = False

    threading.Thread(target=_run, name="digi-vibe", daemon=True).start()
