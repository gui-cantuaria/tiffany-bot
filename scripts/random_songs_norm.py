"""Shared normalization and parsing for random_songs.py maintenance scripts."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# Niche themes / non-radio hits — excluded from t!random expansion.
DROP_EXACT_CANON: frozenset[tuple[str, str]] = frozenset({
    ("pokemon theme song", "__bad__"),
    ("super mario bros ground theme", "__bad__"),
    ("legend of zelda main theme", "__bad__"),
    ("pac man theme", "__bad__"),
    ("final fantasy vii main theme", "__bad__"),
    ("metal gear solid main theme", "__bad__"),
    ("god of war main theme", "__bad__"),
    ("the last of us main theme", "__bad__"),
    ("halo theme song", "__bad__"),
})

_ARTIST_ALIASES: dict[str, str] = {
    "2pac": "tupac",
    "tupac shakur": "tupac",
    "the weeknd": "weeknd",
    "the beatles": "beatles",
    "the rolling stones": "rolling stones",
    "the cranberries": "cranberries",
    "the chainsmokers": "chainsmokers",
    "the killers": "killers",
    "the police": "police",
    "the cure": "cure",
    "the doors": "doors",
    "the who": "who",
    "the clash": "clash",
    "the strokes": "strokes",
    "the smiths": "smiths",
    "the xx": "xx",
    "the 1975": "1975",
    "the black eyed peas": "black eyed peas",
    "the white stripes": "white stripes",
    "the prodigy": "prodigy",
    "the offspring": "offspring",
    "the smashing pumpkins": "smashing pumpkins",
    "the lumineers": "lumineers",
    "the national": "national",
    "the war on drugs": "war on drugs",
    "the human league": "human league",
    "the eagles": "eagles",
}


def fold_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def norm_title(title: str) -> str:
    t = fold_accents(re.sub(r"\s+", " ", title.lower().strip()))
    t = re.sub(r"\([^)]*\)", "", t)
    t = re.sub(r"[^\w\s']", "", t)
    return re.sub(r"\s+", " ", t).strip()


def norm_artist(artist: str) -> str:
    a = fold_accents(re.sub(r"\s+", " ", artist.lower().strip()))
    a = re.sub(r"^the\s+", "", a)
    a = re.sub(r"\s*ft\.?\s+.*$", "", a)
    a = re.sub(r"\s*feat\.?\s+.*$", "", a)
    a = re.sub(r"\s*featuring\s+.*$", "", a)
    a = re.sub(r"\s*&.*$", "", a)
    return _ARTIST_ALIASES.get(a, a)


def canon_key(entry: str) -> tuple[str, str]:
    """Canonical dedup key: (normalized_title, normalized_primary_artist)."""
    body = entry.replace("ytsearch1:", "", 1).strip()
    if " - " not in body:
        return ("__bad__", body.lower())
    title, artist = body.split(" - ", 1)
    return (norm_title(title), norm_artist(artist))


def canon_key_str(entry: str) -> str:
    t, a = canon_key(entry)
    return f"{t}::{a}"


def _clean_part(part: str) -> str:
    return re.sub(r"\s+", " ", part.strip())


def parse_entry(raw: str, *, known_artists: set[str] | None = None) -> str | None:
    """Parse to official 'Title - Artist' display form."""
    s = raw.strip()
    if not s:
        return None
    if s.startswith("ytsearch1:"):
        s = s[len("ytsearch1:") :].strip()

    if " - " in s:
        title, artist = s.split(" - ", 1)
        title, artist = _clean_part(title), _clean_part(artist)
    elif known_artists:
        matched = False
        for name in sorted(known_artists, key=len, reverse=True):
            prefix = name + " "
            if s.startswith(prefix):
                title = _clean_part(s[len(prefix) :])
                artist = name
                matched = True
                break
        if not matched:
            return None
    else:
        return None

    if len(title) < 2 or len(artist) < 2:
        return None
    if len(artist.split()) > 6:
        return None
    title = title.replace('"', "").replace("\\", "")
    artist = artist.replace('"', "").replace("\\", "")
    if canon_key(f"{title} - {artist}") in DROP_EXACT_CANON:
        return None
    return f"{title} - {artist}"


def is_valid_entry(entry: str) -> bool:
    return parse_entry(entry) is not None


_ENTRY_LINE_RE = re.compile(r'^\s*"ytsearch1:([^"]+)",?\s*$', re.M)


def load_entries_from_py(text: str) -> list[str]:
    """Parse RANDOM_SONGS entries from random_songs.py source (line-safe)."""
    return [m.strip() for m in _ENTRY_LINE_RE.findall(text)]


def load_entries_from_path(path: Path) -> list[str]:
    return load_entries_from_py(path.read_text(encoding="utf-8"))
