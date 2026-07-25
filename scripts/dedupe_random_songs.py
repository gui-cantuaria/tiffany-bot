#!/usr/bin/env python3
"""Remove canonical duplicates from random_songs.py (accent/encoding variants)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "random_songs.py"
SCRIPTS = Path(__file__).resolve().parent

sys.path.insert(0, str(SCRIPTS))
from random_songs_norm import canon_key, load_entries_from_path  # noqa: E402


def main() -> int:
    raw_lines = [f"ytsearch1:{entry}" for entry in load_entries_from_path(TARGET)]

    seen: set[tuple[str, str]] = set()
    deduped: list[str] = []
    removed: list[str] = []
    for entry in raw_lines:
        key = canon_key(entry)
        if key in seen:
            removed.append(entry)
            continue
        seen.add(key)
        deduped.append(entry)

    lines = [
        f'"""Exactly {len(deduped)} famous international hits for t!r / t!random (Title - Artist)."""',
        "",
        "RANDOM_SONGS: list[str] = [",
    ]
    for entry in deduped:
        safe = entry.replace("ytsearch1:", "", 1) if entry.startswith("ytsearch1:") else entry
        safe = safe.replace('"', "").replace("\\", "").strip()
        lines.append(f'    "ytsearch1:{safe}",')
    lines.append("]")
    lines.append("")
    lines.append("# Deprecated — kept for import compat; t!r uses RANDOM_SONGS only.")
    lines.append("RANDOM_DISCOVERY: list[str] = []")
    lines.append("")
    TARGET.write_text("\n".join(lines), encoding="utf-8")

    print(f"before={len(raw_lines)} after={len(deduped)} removed={len(removed)}")
    for r in removed:
        print(f"  - {r.replace('ytsearch1:', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
