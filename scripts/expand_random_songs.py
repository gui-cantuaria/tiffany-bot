#!/usr/bin/env python3
"""Expand random_songs.py to a fixed target (default 10_000) with strict dedup.

Sources (priority order when scores tie — existing always kept first):
  1. Current random_songs.py entries
  2. Curated local modules (song_catalog_expansion, famous_hits_fill, …)
  3. Billboard Hot 100 archive (peak top-10 or 20+ weeks on chart)
  4. Spotify TidyTuesday CSV (popularity-ranked; threshold adapts to fill gap)
  5. Optional user CSV (--csv) or Kaggle-style export

Usage:
  py scripts/expand_random_songs.py
  py scripts/expand_random_songs.py --target 10000 --dry-run
  py scripts/expand_random_songs.py --csv data/my_spotify.csv --no-download
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
TARGET_FILE = ROOT / "random_songs.py"

sys.path.insert(0, str(SCRIPTS))
from random_songs_norm import canon_key, load_entries_from_path, parse_entry  # noqa: E402

DEFAULT_TARGET = 10_000

SPOTIFY_CSV_URL = (
    "https://raw.githubusercontent.com/rfordatascience/tidytuesday/master/data/"
    "2020/2020-01-21/spotify_songs.csv"
)
BILLBOARD_CSV_URL = (
    "https://raw.githubusercontent.com/rfordatascience/tidytuesday/main/data/"
    "2021/2021-09-14/billboard.csv"
)

REMIX_SUFFIX_RE = re.compile(
    r"\s*[-–—]\s*(.*remix.*|.*mix.*|radio edit|edit|version|rework|sped up|slowed.*)$",
    re.I,
)

CATALOG_MODULES = (
    "song_catalog_expansion",
    "song_catalog_expansion_2",
    "song_catalog_expansion_3",
)


@dataclass(order=True)
class Candidate:
    score: float
    entry: str


def _load_module(name: str):
    path = SCRIPTS / f"{name}.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def _fetch_url(url: str, timeout: int = 90) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "TiffanyBot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _clean_track_title(title: str) -> str:
    t = REMIX_SUFFIX_RE.sub("", title).strip()
    t = re.sub(r"\s*\(with [^)]+\)\s*", " ", t, flags=re.I).strip()
    t = re.sub(r"\s*\(feat\.? [^)]+\)\s*", " ", t, flags=re.I).strip()
    return re.sub(r"\s+", " ", t)


def load_existing_entries() -> list[str]:
    return load_entries_from_path(TARGET_FILE)


def load_known_artists() -> set[str]:
    artists: set[str] = set()
    for mod_name in CATALOG_MODULES:
        mod = _load_module(mod_name)
        if mod and hasattr(mod, "ARTIST_HITS"):
            artists.update(mod.ARTIST_HITS.keys())
    return artists


def load_local_batches(known_artists: set[str]) -> list[Candidate]:
    out: list[Candidate] = []

    for mod_name in CATALOG_MODULES:
        mod = _load_module(mod_name)
        if not mod or not hasattr(mod, "ARTIST_HITS"):
            continue
        for artist, titles in mod.ARTIST_HITS.items():
            for title in titles:
                entry = parse_entry(f"{str(title).strip()} - {artist}", known_artists=known_artists)
                if entry:
                    out.append(Candidate(950.0, entry))

    for mod_name, attr, score in (
        ("famous_hits_fill", "FAMOUS_HITS", 940.0),
        ("final_hits", "FINAL_HITS", 900.0),
        ("topup_5000_hits", "TOPUP_HITS", 880.0),
    ):
        mod = _load_module(mod_name)
        if not mod:
            continue
        for raw in getattr(mod, attr, []):
            entry = parse_entry(str(raw).strip(), known_artists=known_artists)
            if entry:
                out.append(Candidate(score, entry))

    bulk_path = SCRIPTS / "extra_songs_bulk.txt"
    if bulk_path.exists():
        for line in bulk_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            entry = parse_entry(s, known_artists=known_artists)
            if entry:
                out.append(Candidate(870.0, entry))

    build_path = ROOT / "_build_songs.py"
    if build_path.exists():
        text = build_path.read_text(encoding="utf-8")
        m = re.search(r"new_songs = \[(.*?)\]\n\n# Add", text, re.S)
        if m:
            for raw in re.findall(r'"([^"]+)"', m.group(1)):
                entry = parse_entry(raw.strip(), known_artists=known_artists)
                if entry:
                    out.append(Candidate(860.0, entry))

    return out


def load_billboard_candidates() -> list[Candidate]:
    try:
        raw = _fetch_url(BILLBOARD_CSV_URL)
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"Billboard CSV skipped: {e}")
        return []

    best: dict[tuple[str, str], Candidate] = {}
    reader = csv.DictReader(io.StringIO(raw))
    for row in reader:
        try:
            peak = int(float(row.get("peak_position") or 99))
            weeks = int(float(row.get("weeks_on_chart") or 0))
        except ValueError:
            continue
        # Extremely famous: top-10 peak OR long chart run (Billboard Hot 100).
        if peak > 10 and weeks < 20:
            continue
        song = _clean_track_title((row.get("song") or "").strip())
        artist = (row.get("performer") or "").strip()
        entry = parse_entry(f"{song} - {artist}")
        if not entry:
            continue
        key = canon_key(entry)
        score = float((11 - min(peak, 10)) * 25 + min(weeks, 40))
        prev = best.get(key)
        if prev is None or score > prev.score:
            best[key] = Candidate(score, entry)
    return list(best.values())


def load_spotify_csv_candidates(
    csv_text: str,
    *,
    min_popularity: int,
) -> list[Candidate]:
    best: dict[tuple[str, str], Candidate] = {}
    reader = csv.DictReader(io.StringIO(csv_text))
    fields = {f.lower(): f for f in (reader.fieldnames or [])}

    def col(*names: str) -> str | None:
        for n in names:
            if n in fields:
                return fields[n]
        return None

    title_col = col("track_name", "song", "title", "name")
    artist_col = col("track_artist", "artist", "performer", "artists")
    pop_col = col("track_popularity", "popularity", "pop")

    if not title_col or not artist_col:
        return []

    for row in reader:
        try:
            pop = int(float(row.get(pop_col or "") or 0)) if pop_col else min_popularity
        except ValueError:
            pop = 0
        if pop < min_popularity:
            continue
        title = _clean_track_title(row.get(title_col) or "")
        artist = (row.get(artist_col) or "").strip()
        entry = parse_entry(f"{title} - {artist}")
        if not entry:
            continue
        key = canon_key(entry)
        score = float(pop)
        prev = best.get(key)
        if prev is None or score > prev.score:
            best[key] = Candidate(score, entry)
    return list(best.values())


def load_spotify_remote_candidates(min_popularity: int) -> list[Candidate]:
    try:
        raw = _fetch_url(SPOTIFY_CSV_URL)
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"Spotify CSV skipped: {e}")
        return []
    return load_spotify_csv_candidates(raw, min_popularity=min_popularity)


def load_user_csv(path: Path, min_popularity: int) -> list[Candidate]:
    if not path.exists():
        print(f"User CSV not found: {path}")
        return []
    return load_spotify_csv_candidates(
        path.read_text(encoding="utf-8"), min_popularity=min_popularity,
    )


def merge_to_target(
    existing: list[str],
    batches: list[list[Candidate]],
    *,
    target: int,
) -> tuple[list[str], dict[str, int]]:
    seen_exact: set[str] = set()
    seen_canon: set[tuple[str, str]] = set()
    out: list[str] = []
    stats = {"existing": len(existing), "existing_kept": 0, "existing_deduped": 0, "added": 0}

    for entry in existing:
        key = canon_key(entry)
        exact = entry.lower()
        if exact in seen_exact or key in seen_canon:
            stats["existing_deduped"] += 1
            continue
        seen_exact.add(exact)
        seen_canon.add(key)
        out.append(entry)
        stats["existing_kept"] += 1

    flat = [c for batch in batches for c in batch]
    flat.sort(key=lambda c: c.score, reverse=True)

    for cand in flat:
        if len(out) >= target:
            break
        exact = cand.entry.lower()
        key = canon_key(cand.entry)
        if exact in seen_exact or key in seen_canon:
            continue
        seen_exact.add(exact)
        seen_canon.add(key)
        out.append(cand.entry)
        stats["added"] += 1

    return out, stats


def adaptive_spotify_fill(
    existing: list[str],
    base_batches: list[list[Candidate]],
    *,
    target: int,
    allow_download: bool,
    user_csv: Path | None,
) -> tuple[list[str], dict[str, int]]:
    """Lower Spotify popularity floor until target is met or floor hits minimum."""
    merged_stats: dict[str, int] = {}
    for floor in (75, 70, 65, 60, 55):
        batches = list(base_batches)
        if user_csv:
            batches.append(load_user_csv(user_csv, min_popularity=floor))
        if allow_download:
            batches.append(load_spotify_remote_candidates(min_popularity=floor))
        songs, stats = merge_to_target(existing, batches, target=target)
        merged_stats = stats
        merged_stats["spotify_floor"] = floor
        if len(songs) >= target:
            return songs, merged_stats
    return songs, merged_stats


def validate_output(songs: list[str], target: int) -> None:
    if len(songs) != target:
        raise SystemExit(f"Expected exactly {target} songs, got {len(songs)}")

    canon_keys = [canon_key(s) for s in songs]
    if len(canon_keys) != len(set(canon_keys)):
        dupes = len(canon_keys) - len(set(canon_keys))
        raise SystemExit(f"Canonical duplicates remain: {dupes}")

    bad = [s for s in songs if " - " not in s]
    if bad:
        raise SystemExit(f"Malformed entries (missing ' - '): {len(bad)}")


def _sanitize_for_file(entry: str) -> str:
    """Remove characters that break Python double-quoted literals."""
    return entry.replace('"', "").replace("\\", "").strip()


def write_random_songs(songs: list[str], target: int) -> None:
    lines = [
        f'"""Exactly {target} famous international hits for t!r / t!random (Title - Artist)."""',
        "",
        "RANDOM_SONGS: list[str] = [",
    ]
    for entry in songs:
        safe = _sanitize_for_file(entry)
        lines.append(f'    "ytsearch1:{safe}",')
    lines.append("]")
    lines.append("")
    lines.append("# Deprecated — kept for import compat; t!r uses RANDOM_SONGS only.")
    lines.append("RANDOM_DISCOVERY: list[str] = []")
    lines.append("")
    TARGET_FILE.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Expand random_songs.py to a fixed target count.")
    p.add_argument("--target", type=int, default=DEFAULT_TARGET, help="Final song count (default: 10000)")
    p.add_argument("--csv", type=Path, default=None, help="Optional local CSV (Spotify/Kaggle format)")
    p.add_argument("--no-download", action="store_true", help="Skip remote CSV downloads")
    p.add_argument("--dry-run", action="store_true", help="Compute stats without writing random_songs.py")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    target = int(args.target)
    existing = load_existing_entries()
    if not existing:
        raise SystemExit("No existing entries found in random_songs.py")

    known_artists = load_known_artists()
    batches: list[list[Candidate]] = [
        load_local_batches(known_artists),
        load_billboard_candidates(),
    ]

    songs, stats = adaptive_spotify_fill(
        existing,
        batches,
        target=target,
        allow_download=not args.no_download,
        user_csv=args.csv,
    )

    if len(songs) < target:
        raise SystemExit(
            f"Could only reach {len(songs)} unique famous hits (target {target}). "
            "Add --csv with a larger dataset or lower fame filters in the script."
        )

    songs = songs[:target]
    validate_output(songs, target)

    report = {
        "target": target,
        "existing_raw": stats.get("existing", len(existing)),
        "existing_kept": stats.get("existing_kept", len(existing)),
        "existing_deduped": stats.get("existing_deduped", 0),
        "added": stats.get("added", len(songs) - len(existing)),
        "final": len(songs),
        "spotify_popularity_floor": stats.get("spotify_floor"),
    }
    print(json.dumps(report, indent=2))

    if args.dry_run:
        print("Dry run — random_songs.py not modified.")
        return 0

    write_random_songs(songs, target)
    print(f"Wrote {TARGET_FILE} with {len(songs)} songs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
