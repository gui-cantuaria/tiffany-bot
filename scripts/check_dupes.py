#!/usr/bin/env python3
"""Validate random_songs.py: exact count, no exact/canonical duplicates."""
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
t = (ROOT / "random_songs.py").read_text(encoding="utf-8")
main = re.search(r"RANDOM_SONGS.*?=\s*\[(.*?)\]", t, re.S)
if not main:
    print("RANDOM_SONGS block not found", file=sys.stderr)
    sys.exit(1)
songs = [m.strip() for m in re.findall(r'ytsearch1:([^"]+)', main.group(1))]

seen: set[str] = set()
exact_dupes: list[str] = []
for s in songs:
    k = s.lower()
    if k in seen:
        exact_dupes.append(s)
    seen.add(k)

def _norm_title(title: str) -> str:
    t = re.sub(r"\s+", " ", title.lower().strip())
    return re.sub(r"[^\w\s']", "", t)

def _norm_artist(artist: str) -> str:
    a = re.sub(r"\s+", " ", artist.lower().strip())
    a = re.sub(r"^the\s+", "", a)
    a = re.sub(r"\s*ft\.?\s+.*$", "", a)
    a = re.sub(r"\s*feat\.?\s+.*$", "", a)
    return a

by_canon: dict[str, list[str]] = defaultdict(list)
bad_fmt = [s for s in songs if " - " not in s]
for s in songs:
    if " - " not in s:
        continue
    title, artist = s.split(" - ", 1)
    by_canon[f"{_norm_title(title)}::{_norm_artist(artist)}"].append(s)
canon_dupes = {k: v for k, v in by_canon.items() if len(v) > 1}

disc = re.search(r"RANDOM_DISCOVERY.*?=\s*\[(.*?)\]", t, re.S)
disc_n = len(re.findall(r"ytsearch1:", disc.group(1))) if disc else 0

print(f"RANDOM_SONGS={len(songs)} exact_unique={len(seen)} exact_dupes={len(exact_dupes)}")
print(f"canonical_dupes={len(canon_dupes)} bad_format={len(bad_fmt)} discovery={disc_n}")
ok = len(songs) == 5000 and not exact_dupes and not canon_dupes and not bad_fmt and disc_n == 0
sys.exit(0 if ok else 1)

