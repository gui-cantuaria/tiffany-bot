#!/usr/bin/env python3
"""Mescla todas as fontes em random_songs.py. Uso: py scripts/merge_all_song_sources.py"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "random_songs.py"
SCRIPTS = Path(__file__).resolve().parent


def load_existing() -> list[str]:
    text = TARGET.read_text(encoding="utf-8")
    return [m.strip() for m in re.findall(r'ytsearch1:([^"]+)', text)]


def load_artist_hits(module_name: str) -> list[str]:
    path = SCRIPTS / f"{module_name}.py"
    if not path.exists():
        return []
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    out: list[str] = []
    for artist, titles in mod.ARTIST_HITS.items():
        for title in titles:
            t = str(title).strip()
            if t:
                out.append(f"{artist} {t}")
    return out


def load_build_songs() -> list[str]:
    path = ROOT / "_build_songs.py"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    m = re.search(r"new_songs = \[(.*?)\]\n\n# Add", text, re.S)
    if not m:
        return []
    return [s.strip() for s in re.findall(r'"([^"]+)"', m.group(1))]


def load_final_hits() -> list[str]:
    path = SCRIPTS / "final_hits.py"
    if not path.exists():
        return []
    spec = importlib.util.spec_from_file_location("final_hits", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return [str(s).strip() for s in getattr(mod, "FINAL_HITS", []) if str(s).strip()]


def load_extra_lines() -> list[str]:
    path = SCRIPTS / "extra_songs_bulk.txt"
    if not path.exists():
        return []
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            lines.append(s)
    return lines


def merge_unique(sources: list[list[str]]) -> tuple[list[str], int]:
    seen: set[str] = set()
    unique: list[str] = []
    added = 0
    for batch in sources:
        for s in batch:
            k = s.lower()
            if k in seen:
                continue
            seen.add(k)
            unique.append(s)
            added += 1
    return unique, added


def main() -> None:
    existing = load_existing()
    before = len({s.lower() for s in existing})

    catalog_batches = [
        load_artist_hits("song_catalog_expansion"),
        load_artist_hits("song_catalog_expansion_2"),
        load_artist_hits("song_catalog_expansion_3"),
        load_build_songs(),
        load_extra_lines(),
        load_final_hits(),
    ]

    seen = {s.lower() for s in existing}
    unique = list(existing)
    catalog_added = 0
    for batch in catalog_batches:
        for s in batch:
            k = s.lower()
            if k in seen:
                continue
            seen.add(k)
            unique.append(s)
            catalog_added += 1

    lines = [
        f'"""Lista de {len(unique)} musicas internacionais de grande sucesso para t!r / t!random."""\n\n',
        "RANDOM_SONGS: list[str] = [\n",
    ]
    for s in unique:
        lines.append(f'    "ytsearch1:{s}",\n')
    lines.append("]\n")
    disc_m = re.search(r"(RANDOM_DISCOVERY: list\[str\] = \[.*?\]\n)", TARGET.read_text(encoding="utf-8"), re.S)
    if disc_m:
        lines.append("\n")
        lines.append(disc_m.group(1))
    TARGET.write_text("".join(lines), encoding="utf-8")
    print(f"Base: {before} | Novas: {catalog_added} | Total: {len(unique)}")


if __name__ == "__main__":
    main()
