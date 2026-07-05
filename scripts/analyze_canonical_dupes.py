#!/usr/bin/env python3
"""Find near-duplicate songs in random_songs.py (same hit, different formatting)."""
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
t = (ROOT / "random_songs.py").read_text(encoding="utf-8")
main = re.search(r"RANDOM_SONGS.*?=\s*\[(.*?)\]\s*\n\nRANDOM_DISCOVERY", t, re.S)
main_songs = [m.strip() for m in re.findall(r'ytsearch1:([^"]+)', main.group(1))]

_ARTIST_ALIASES = {
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
}


def _norm_artist(artist: str) -> str:
    a = re.sub(r"\s+", " ", artist.lower().strip())
    a = re.sub(r"^the\s+", "", a)
    a = re.sub(r"\s*ft\.?\s+.*$", "", a)
    a = re.sub(r"\s*feat\.?\s+.*$", "", a)
    a = re.sub(r"\s*featuring\s+.*$", "", a)
    a = re.sub(r"\s*&.*$", "", a)
    return _ARTIST_ALIASES.get(a, a)


def _norm_title(title: str) -> str:
    t = re.sub(r"\s+", " ", title.lower().strip())
    t = re.sub(r"[^\w\s']", "", t)
    return t


def canonical_key(s: str) -> str:
    if " - " not in s:
        return s.lower()
    title, artist = s.split(" - ", 1)
    return f"{_norm_title(title)}::{_norm_artist(artist)}"


by_canon: dict[str, list[str]] = defaultdict(list)
for s in main_songs:
    by_canon[canonical_key(s)].append(s)

dupes = {k: v for k, v in by_canon.items() if len(v) > 1}
print(f"canonical dupes: {len(dupes)} groups, {sum(len(v)-1 for v in dupes.values())} extra entries")
for k, v in sorted(dupes.items(), key=lambda x: -len(x[1]))[:40]:
    print(f"  {k}: {v}")
