import re
from pathlib import Path

t = Path("random_songs.py").read_text(encoding="utf-8")
songs = [m.strip() for m in re.findall(r'ytsearch1:([^"]+)', t)]
seen: set[str] = set()
dup: list[str] = []
for s in songs:
    k = s.lower()
    if k in seen:
        dup.append(s)
    seen.add(k)
print("total", len(songs), "unique", len(seen), "dupes", len(dup))
