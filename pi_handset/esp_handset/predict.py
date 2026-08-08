"""Offline predictive text for Digivice OSK."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

# Compact frequency list (~400 common English words). Enough for SMS stubs.
_BUILTIN = """
the be to of and a in that have i it for not on with he as you do at
this but his by from they we say her she or an will my one all would
there their what so up out if about who get which go me when make can
like time no just him know take people into year your good some could
them see other than then now look only come its over think also back
after use two how our work first well way even new want because any
these give day most us is was are been has had were said did get made
may find here thing more much before where need feel become leave put
mean keep let begin seem help show hear play run move live believe hold
bring happen write provide sit stand lose pay meet include continue set
learn change lead understand watch follow stop create speak read allow
add spend grow open walk win offer remember love consider appear buy
wait serve die send expect build stay fall cut reach kill remain
suggest raise pass sell require decide return explain hope develop
carry break eat support hit produce protect catch draw cover throw
hang forget thank receive join work home phone call text message please
yes no ok thanks hello hi bye morning night today tomorrow yesterday
help need want love sorry thanks please stop go come yes right left
up down back next done save send delete edit note todo alarm clock
weather music video camera gps lora radio mesh sos battery charge wifi
settings network security about linux desktop exit volume mute
""".split()


def _wordlist_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "words_en.txt"


@lru_cache(maxsize=1)
def _words() -> List[str]:
    path = _wordlist_path()
    if path.is_file():
        try:
            raw = path.read_text(encoding="utf-8").splitlines()
            words = [w.strip().lower() for w in raw if w.strip() and not w.startswith("#")]
            if words:
                return words
        except OSError:
            pass
    # dedupe preserving order
    seen = set()
    out: List[str] = []
    for w in _BUILTIN:
        w = w.lower()
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def predict(prefix: str, limit: int = 3) -> List[str]:
    """Return up to `limit` completions for the current word prefix."""
    p = (prefix or "").lower()
    if not p or not p.isalpha():
        return []
    hits: List[str] = []
    for w in _words():
        if w.startswith(p) and w != p:
            hits.append(w)
            if len(hits) >= limit:
                break
    return hits


def current_word(text: str, cursor: int = -1) -> str:
    """Word fragment left of cursor (or end of string)."""
    if cursor < 0:
        cursor = len(text)
    i = cursor
    while i > 0 and text[i - 1].isalpha():
        i -= 1
    return text[i:cursor]
