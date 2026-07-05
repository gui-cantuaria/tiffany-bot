#!/usr/bin/env python3
"""Rebuild random_songs.py with exactly 5000 famous hits as 'Title - Artist'."""
from __future__ import annotations

import importlib.util
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "random_songs.py"
SCRIPTS = Path(__file__).resolve().parent
TARGET_COUNT = 5000

# Drop niche game/anime themes that are not mainstream radio hits.
_DROP_EXACT = {
    "pokemon theme song",
    "yu-gi-oh theme song",
    "super mario bros ground theme",
    "legend of zelda main theme",
    "pac-man theme",
    "final fantasy vii main theme",
    "metal gear solid main theme",
    "halo theme song",
    "god of war main theme",
    "the last of us main theme",
}


def _load_catalog_artists() -> dict[str, list[str]]:
    spec = importlib.util.spec_from_file_location(
        "song_catalog_expansion", SCRIPTS / "song_catalog_expansion.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return dict(mod.ARTIST_HITS)


def _load_existing() -> list[str]:
    text = TARGET.read_text(encoding="utf-8")
    block = text.split("RANDOM_DISCOVERY")[0]
    return [m.strip() for m in re.findall(r'ytsearch1:([^"]+)', block)]


def _load_discovery_block() -> str:
    text = TARGET.read_text(encoding="utf-8")
    m = re.search(r"(RANDOM_DISCOVERY: list\[str\] = \[.*?\]\n)", text, re.S)
    return m.group(1) if m else ""


def _load_build_songs() -> list[str]:
    path = ROOT / "_build_songs.py"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    m = re.search(r"new_songs = \[(.*?)\]\n\n# Add", text, re.S)
    if not m:
        return []
    return [s.strip() for s in re.findall(r'"([^"]+)"', m.group(1)) if s.strip()]


def _load_bulk_lines() -> list[str]:
    path = SCRIPTS / "extra_songs_bulk.txt"
    if not path.exists():
        return []
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


def _discover_artists_from_lines(lines: list[str], min_titles: int = 2) -> list[str]:
    """Infer 'Artist' prefixes from 'Artist Title' lines."""
    prefix_titles: dict[str, set[str]] = defaultdict(set)
    for line in lines:
        if " - " in line:
            continue
        words = line.split()
        if len(words) < 2:
            continue
        for i in range(1, min(6, len(words))):
            prefix = " ".join(words[:i])
            title = " ".join(words[i:]).strip()
            if title:
                prefix_titles[prefix].add(title)
    return sorted(
        (p for p, titles in prefix_titles.items() if len(titles) >= min_titles),
        key=len,
        reverse=True,
    )


def _build_artist_list(catalog: dict[str, list[str]], raw_lines: list[str]) -> list[str]:
    catalog_artists = sorted(catalog.keys(), key=len, reverse=True)
    discovered = [
        a for a in _discover_artists_from_lines(raw_lines, min_titles=2) if a not in catalog
    ]
    discovered.sort(key=len, reverse=True)
    return catalog_artists + discovered


def _is_plausible_entry(title: str, artist: str, known_artists: set[str] | None = None) -> bool:
    if len(title) < 2 or len(artist) < 2:
        return False
    if len(artist.split()) > 5:
        return False
    if known_artists:
        if artist in known_artists:
            return True
        for known in known_artists:
            if len(known) < 4:
                continue
            if artist.startswith(known + " ") and artist != known:
                rest = artist[len(known) + 1 :]
                if rest.lower().startswith(("ft ", "feat ", "featuring ", "with ")):
                    return True
                return False
    return True


def _parse_artist_title(line: str, artists: list[str]) -> str | None:
    s = line.strip()
    if not s:
        return None
    if " - " in s:
        title, artist = s.split(" - ", 1)
        title, artist = title.strip(), artist.strip()
        if title and artist:
            return f"{title} - {artist}"
        return None
    for artist in artists:
        prefix = artist + " "
        if s.startswith(prefix):
            title = s[len(prefix):].strip()
            if title:
                return f"{title} - {artist}"
    return None


def _normalize_entry(entry: str, known_artists: set[str] | None = None) -> str | None:
    s = entry.strip()
    if not s or " - " not in s:
        return None
    title, artist = s.split(" - ", 1)
    title = re.sub(r"\s+", " ", title.strip())
    artist = re.sub(r"\s+", " ", artist.strip())
    if not title or not artist:
        return None
    if not _is_plausible_entry(title, artist, known_artists):
        return None
    key = f"{title} - {artist}".lower()
    if key in _DROP_EXACT:
        return None
    return f"{title} - {artist}"


def _catalog_entries(catalog: dict[str, list[str]], known_artists: set[str]) -> list[str]:
    out: list[str] = []
    for artist, titles in catalog.items():
        for title in titles:
            norm = _normalize_entry(f"{title.strip()} - {artist}", known_artists)
            if norm:
                out.append(norm)
    return out


def _load_fill_hits() -> list[str]:
    path = SCRIPTS / "famous_hits_fill.py"
    if not path.exists():
        return []
    spec = importlib.util.spec_from_file_location("famous_hits_fill", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return [str(s).strip() for s in getattr(mod, "FAMOUS_HITS", []) if str(s).strip()]


def _collect_candidates() -> tuple[list[str], list[str], list[str]]:
    """Return (priority_existing, catalog, supplemental) in fame order."""
    catalog = _load_catalog_artists()
    catalog_artists = set(catalog.keys())
    raw_bulk = _load_bulk_lines()
    raw_build = _load_build_songs()
    parse_artists = _build_artist_list(catalog, raw_bulk + raw_build)

    existing_norm: list[str] = []
    for s in _load_existing():
        norm = _normalize_entry(s, catalog_artists) or _normalize_entry(
            _parse_artist_title(s, parse_artists) or "", catalog_artists
        )
        if norm:
            existing_norm.append(norm)

    catalog_norm = _catalog_entries(catalog, catalog_artists)

    supplemental: list[str] = []
    for line in raw_build + raw_bulk:
        parsed = _parse_artist_title(line, parse_artists)
        norm = _normalize_entry(parsed, catalog_artists) if parsed else None
        if norm:
            supplemental.append(norm)

    return existing_norm, catalog_norm, supplemental


def _load_topup_hits() -> list[str]:
    path = SCRIPTS / "topup_5000_hits.py"
    if not path.exists():
        return []
    spec = importlib.util.spec_from_file_location("topup_5000_hits", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return [str(s).strip() for s in getattr(mod, "TOPUP_HITS", []) if str(s).strip()]


def _apply_fill_hits(base: list[str], catalog_artists: set[str]) -> list[str]:
    seen_exact = {s.lower() for s in base}
    seen_canon = {canonical_song_key(s) for s in base}
    out = list(base)
    for s in _load_fill_hits():
        norm = _normalize_entry(s, catalog_artists)
        if not norm:
            continue
        exact = norm.lower()
        canon = canonical_song_key(norm)
        if exact in seen_exact or canon in seen_canon:
            continue
        seen_exact.add(exact)
        seen_canon.add(canon)
        out.append(norm)
    return out


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
    "outkast": "outkast",
}


def _norm_title(title: str) -> str:
    t = re.sub(r"\s+", " ", title.lower().strip())
    t = re.sub(r"[^\w\s']", "", t)
    return t


def _norm_artist(artist: str) -> str:
    a = re.sub(r"\s+", " ", artist.lower().strip())
    a = re.sub(r"^the\s+", "", a)
    a = re.sub(r"\s*ft\.?\s+.*$", "", a)
    a = re.sub(r"\s*feat\.?\s+.*$", "", a)
    a = re.sub(r"\s*featuring\s+.*$", "", a)
    a = re.sub(r"\s*&.*$", "", a)
    return _ARTIST_ALIASES.get(a, a)


def canonical_song_key(entry: str) -> str:
    """Stable key for dedup (same hit with different formatting counts once)."""
    s = entry.strip()
    if " - " not in s:
        return re.sub(r"\s+", " ", s.lower())
    title, artist = s.split(" - ", 1)
    return f"{_norm_title(title)}::{_norm_artist(artist)}"


def _merge_unique(priority_batches: list[list[str]]) -> list[str]:
    seen_exact: set[str] = set()
    seen_canon: set[str] = set()
    out: list[str] = []
    for batch in priority_batches:
        for s in batch:
            exact = s.lower()
            canon = canonical_song_key(s)
            if exact in seen_exact or canon in seen_canon:
                continue
            seen_exact.add(exact)
            seen_canon.add(canon)
            out.append(s)
    return out


def _write_output(songs: list[str]) -> None:
    if len(songs) != TARGET_COUNT:
        raise SystemExit(f"Expected {TARGET_COUNT} songs, got {len(songs)}")

    canon_keys = [canonical_song_key(s) for s in songs]
    if len(canon_keys) != len(set(canon_keys)):
        dupes = len(canon_keys) - len(set(canon_keys))
        raise SystemExit(f"Canonical duplicate keys remain: {dupes}")

    lines = [
        f'"""Exactly {TARGET_COUNT} famous international hits for t!r / t!random (Title - Artist)."""\n\n',
        "RANDOM_SONGS: list[str] = [\n",
    ]
    for s in songs:
        lines.append(f'    "ytsearch1:{s}",\n')
    lines.append("]\n\n")
    lines.append("# Deprecated — kept for import compat; t!r uses RANDOM_SONGS only.\n")
    lines.append("RANDOM_DISCOVERY: list[str] = []\n")
    TARGET.write_text("".join(lines), encoding="utf-8")


def main() -> None:
    existing, catalog, supplemental = _collect_candidates()
    merged = _merge_unique([existing, catalog, supplemental])
    catalog_artists = set(_load_catalog_artists().keys())
    merged = _apply_fill_hits(merged, catalog_artists)
    # Dedicated top-up to reach exactly TARGET_COUNT after canonical dedup.
    seen_exact = {s.lower() for s in merged}
    seen_canon = {canonical_song_key(s) for s in merged}
    for s in _load_topup_hits():
        norm = _normalize_entry(s, catalog_artists) or s
        exact = norm.lower()
        canon = canonical_song_key(norm)
        if exact in seen_exact or canon in seen_canon:
            continue
        seen_exact.add(exact)
        seen_canon.add(canon)
        merged.append(norm)
    print(f"Unique candidates: {len(merged)} (existing {len(existing)}, catalog {len(catalog)}, extra {len(supplemental)})")

    if len(merged) < TARGET_COUNT:
        raise SystemExit(
            f"Not enough famous songs after merge ({len(merged)}). "
            "Add more sources or relax filters."
        )

    final = merged[:TARGET_COUNT]
    _write_output(final)
    print(f"Wrote {TARGET_COUNT} unique songs to {TARGET}")


if __name__ == "__main__":
    main()
