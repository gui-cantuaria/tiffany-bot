#!/usr/bin/env python3
"""Legado: prefira py scripts/merge_all_song_sources.py (todas as fontes)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "random_songs.py"

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from song_catalog_expansion import ARTIST_HITS  # noqa: E402


def load_existing() -> list[str]:
    text = TARGET.read_text(encoding="utf-8")
    return [m.strip() for m in re.findall(r'ytsearch1:([^"]+)', text)]


def flatten_catalog() -> list[str]:
    out: list[str] = []
    for artist, titles in ARTIST_HITS.items():
        for title in titles:
            t = title.strip()
            if t:
                out.append(f"{artist} {t}")
    return out


def main() -> None:
    seen: set[str] = set()
    unique: list[str] = []
    for s in load_existing():
        k = s.lower()
        if k not in seen:
            seen.add(k)
            unique.append(s)
    before = len(unique)

    added = 0
    for s in flatten_catalog():
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        unique.append(s)
        added += 1

    lines = [
        f'"""Lista de {len(unique)} musicas internacionais de grande sucesso para t!r / t!random."""\n\n',
        "RANDOM_SONGS: list[str] = [\n",
    ]
    for s in unique:
        lines.append(f'    "ytsearch1:{s}",\n')
    lines.append("]\n")
    TARGET.write_text("".join(lines), encoding="utf-8")
    print(f"Existentes: {before} | Novas unicas: {added} | Total: {len(unique)}")


if __name__ == "__main__":
    main()
