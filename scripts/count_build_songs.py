import re
from pathlib import Path

t = Path("_build_songs.py").read_text(encoding="utf-8")
m = re.search(r"new_songs = \[(.*?)\]\n\n# Add", t, re.S)
items = re.findall(r'"([^"]+)"', m.group(1) if m else "")
print(len(items))
