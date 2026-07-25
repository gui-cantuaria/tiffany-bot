#!/usr/bin/env python3
"""Validate random_songs.py: exact count, no exact/canonical duplicates."""
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from random_songs_norm import canon_key, load_entries_from_path  # noqa: E402

songs = load_entries_from_path(ROOT / "random_songs.py")

seen: set[str] = set()
exact_dupes: list[str] = []
for s in songs:
    k = s.lower()
    if k in seen:
        exact_dupes.append(s)
    seen.add(k)

by_canon: dict[tuple[str, str], list[str]] = defaultdict(list)
bad_fmt = [s for s in songs if " - " not in s]
for s in songs:
    if " - " not in s:
        continue
    by_canon[canon_key(s)].append(s)
canon_dupes = {k: v for k, v in by_canon.items() if len(v) > 1}

t = (ROOT / "random_songs.py").read_text(encoding="utf-8")
disc = re.search(r"RANDOM_DISCOVERY.*?=\s*\[(.*?)\]", t, re.S)
disc_n = len(re.findall(r"ytsearch1:", disc.group(1))) if disc else 0

print(f"RANDOM_SONGS={len(songs)} exact_unique={len(seen)} exact_dupes={len(exact_dupes)}")
print(f"canonical_dupes={len(canon_dupes)} bad_format={len(bad_fmt)} discovery={disc_n}")
ok = not exact_dupes and not canon_dupes and not bad_fmt and disc_n == 0 and len(songs) == len(seen)
sys.exit(0 if ok else 1)
