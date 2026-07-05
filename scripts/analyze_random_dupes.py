#!/usr/bin/env python3
"""Analyze duplicates and near-duplicates in random_songs.py."""
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
t = (ROOT / "random_songs.py").read_text(encoding="utf-8")
main = re.search(r"RANDOM_SONGS.*?=\s*\[(.*?)\]\s*\n\nRANDOM_DISCOVERY", t, re.S)
disc = re.search(r"RANDOM_DISCOVERY.*?=\s*\[(.*?)\]\s*$", t, re.S)
main_songs = [m.strip() for m in re.findall(r'ytsearch1:([^"]+)', main.group(1))]
disc_songs = [m.strip() for m in re.findall(r'ytsearch1:([^"]+)', disc.group(1))] if disc else []
print("RANDOM_SONGS", len(main_songs))
print("RANDOM_DISCOVERY", len(disc_songs))

# Non Title - Artist in main
bad_fmt = [s for s in main_songs if " - " not in s]
print("main without ' - ':", len(bad_fmt), bad_fmt[:5])

# Non Title - Artist in discovery
bad_disc = disc_songs  # all generic
print("discovery entries (generic):", len(bad_disc))


def norm_key(s: str) -> str:
    s = re.sub(r"\s+", " ", s.lower().strip())
    s = re.sub(r"\s*ft\.?\s+", " ft ", s)
    s = re.sub(r"\s*feat\.?\s+", " ft ", s)
    s = re.sub(r"\s*featuring\s+", " ft ", s)
    if " - " in s:
        a, b = [x.strip() for x in s.split(" - ", 1)]
        return " | ".join(sorted([a, b]))
    return s


seen: dict[str, str] = {}
exact_dupes: list[tuple[str, str]] = []
for s in main_songs:
    k = s.lower()
    if k in seen:
        exact_dupes.append((s, seen[k]))
    seen[k] = s
print("exact dupes main", len(exact_dupes))

by_norm: dict[str, list[str]] = defaultdict(list)
for s in main_songs:
    by_norm[norm_key(s)].append(s)
norm_dupes = {k: v for k, v in by_norm.items() if len(v) > 1}
print("normalized dupes (swapped title/artist)", len(norm_dupes))
for k, v in list(norm_dupes.items())[:20]:
    print(" ", v)

by_title: dict[str, list[str]] = defaultdict(list)
for s in main_songs:
    if " - " in s:
        title = s.split(" - ", 1)[0].strip().lower()
        by_title[title].append(s)
title_dupes = {k: v for k, v in by_title.items() if len(v) > 1}
print("same title different artist:", len(title_dupes))
for k, v in list(sorted(title_dupes.items(), key=lambda x: -len(x[1])))[:15]:
    print(f"  {k!r} ({len(v)}):", v[:4])
