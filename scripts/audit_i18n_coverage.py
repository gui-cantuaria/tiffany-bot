#!/usr/bin/env python3
"""Audit Tiffany i18n: per-lang coverage, EN fallback leaks, untranslated JSON strings."""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import locale_utils  # noqa: E402
from infra import i18n_loader  # noqa: E402

ALL_LANGS = locale_utils.ALL_LANGS
CORE_LANGS = locale_utils.CORE_LANGS
EXTENDED_LANGS = tuple(l for l in ALL_LANGS if l not in CORE_LANGS)

# Keys intentionally identical across langs (commands, brands, placeholders).
_IDENTICAL_OK_PREFIXES = (
    "slash.cmd.",
    "gw.",
    "emb.",
)
_IDENTICAL_OK_KEYS = frozenset({
    "volume.ytdlp_note",
    "premium.upsell",
})

# Sample keys that MUST be translated (user-facing prose).
_CRITICAL_KEYS = (
    "help.title",
    "help.desc",
    "help.music.body",
    "help.chat.body",
    "help.footer",
    "lang.title",
    "lang.desc",
    "lang.changed",
    "lang.search_btn",
    "lang.search_not_found",
    "about.desc",
    "volume.title",
    "volume.client_body",
    "cmd.error.generic",
    "slash.guild_only",
)


def _all_keys() -> set[str]:
    keys = set(locale_utils._STRINGS.keys())
    catalog = ROOT / "locales" / "_catalog_en.json"
    if catalog.exists():
        keys.update(json.loads(catalog.read_text(encoding="utf-8")).keys())
    i18n_loader.ensure_loaded()
    for lang in ALL_LANGS:
        keys.update(i18n_loader._cache.get(lang, {}).keys())
    return keys


def _en_text(key: str) -> str:
    return locale_utils.tr("en", key)


def _looks_english(text: str) -> bool:
    """Heuristic: ASCII-heavy prose likely still English."""
    if not text or len(text) < 12:
        return False
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    ascii_ratio = sum(1 for c in letters if ord(c) < 128) / len(letters)
    en_markers = (
        " the ", " and ", " your ", " with ", " please ", " command",
        " language", " choose ", " pick ", " bot ", " queue",
    )
    low = text.lower()
    return ascii_ratio > 0.92 and any(m in low for m in en_markers)


def _json_native_keys(lang: str) -> dict[str, str]:
    i18n_loader.ensure_loaded()
    bucket = dict(i18n_loader._cache.get(lang, {}))
    en_bucket = i18n_loader._cache.get("en", {})
    native: dict[str, str] = {}
    for key, val in bucket.items():
        en_val = en_bucket.get(key)
        if en_val is None:
            native[key] = val
        elif val != en_val:
            native[key] = val
    return native


def main() -> int:
    keys = sorted(_all_keys())
    print("=== Tiffany i18n audit ===\n")
    print(f"Languages: {len(ALL_LANGS)} — {', '.join(ALL_LANGS)}")
    print(f"Total keys tracked: {len(keys)}\n")

    # --- Per-lang JSON file stats ---
    print("--- JSON catalog (locales/<lang>/) ---")
    i18n_loader.ensure_loaded()
    for lang in ALL_LANGS:
        n = len(i18n_loader._cache.get(lang, {}))
        print(f"  {lang:>3}: {n:4} keys in JSON")
    print()

    # --- tr() resolution: same as EN for extended langs ---
    print("--- tr(lang) identical to tr(en) [extended langs, critical keys] ---")
    for lang in EXTENDED_LANGS:
        same = []
        for key in _CRITICAL_KEYS:
            if key not in keys:
                continue
            got = locale_utils.tr(lang, key)
            en = _en_text(key)
            if got == en:
                same.append(key)
        if same:
            print(f"  {lang}: {len(same)} critical keys still EN → {', '.join(same[:8])}{'…' if len(same) > 8 else ''}")
        else:
            print(f"  {lang}: OK (critical keys translated)")
    print()

    # --- Full identical-to-EN count per extended lang ---
    print("--- Full catalog: tr(lang) == tr(en) ---")
    for lang in EXTENDED_LANGS:
        identical = 0
        missing = 0
        for key in keys:
            got = locale_utils.tr(lang, key)
            if got == key:
                missing += 1
                continue
            if got == _en_text(key):
                if key in _IDENTICAL_OK_KEYS or key.startswith(_IDENTICAL_OK_PREFIXES):
                    continue
                identical += 1
        pct = 100 * identical / max(len(keys), 1)
        print(f"  {lang}: {identical} keys fall back to EN ({pct:.1f}%), {missing} raw key leaks")
    print()

    # --- JSON entries that are copy-paste English in non-en bot.json ---
    print("--- Untranslated strings in JSON (English prose in non-en files) ---")
    for lang in EXTENDED_LANGS:
        suspicious: list[str] = []
        native = _json_native_keys(lang)
        for key, val in native.items():
            if key.startswith(_IDENTICAL_OK_PREFIXES) or key in _IDENTICAL_OK_KEYS:
                continue
            if _looks_english(val) and len(val) > 20:
                suspicious.append(key)
        if suspicious:
            print(f"  {lang}: {len(suspicious)} possibly-English JSON strings")
            for k in suspicious[:5]:
                print(f"    · {k}: {native[k][:70]}…")
            if len(suspicious) > 5:
                print(f"    … +{len(suspicious) - 5} more")
        else:
            print(f"  {lang}: OK")
    print()

    # --- Core langs: _STRINGS coverage ---
    print("--- Core langs _STRINGS coverage ---")
    for lang in CORE_LANGS:
        missing = [k for k in keys if k in locale_utils._STRINGS and lang not in locale_utils._STRINGS[k]]
        if missing:
            print(f"  {lang}: missing {len(missing)} _STRINGS entries")
        else:
            covered = sum(1 for k in keys if k in locale_utils._STRINGS)
            print(f"  {lang}: {covered} keys in _STRINGS")
    print()

    # --- New lang.search_* keys ---
    print("--- lang.search_* (language picker) ---")
    search_keys = [k for k in keys if k.startswith("lang.search")]
    for lang in ALL_LANGS:
        gaps = [k for k in search_keys if locale_utils.tr(lang, k) == _en_text(k) and lang != "en"]
        if gaps:
            print(f"  {lang}: uses EN for {len(gaps)}/{len(search_keys)} search keys")
        elif lang == "en":
            print(f"  en: source language ({len(search_keys)} keys)")
        else:
            print(f"  {lang}: all {len(search_keys)} search keys localized")
    print()

    # --- Fallback chain verification ---
    print("--- Fallback chain ---")
    print(f"  DEFAULT_LANG: {locale_utils.DEFAULT_LANG}")
    print(f"  i18n_loader._FALLBACK_CHAIN: {i18n_loader._FALLBACK_CHAIN}")
    print(f"  tr() order: JSON[{lang}] → JSON[en] → _STRINGS[{lang}] → _STRINGS[en] → key")
    test_key = "help.title"
    fake = locale_utils.tr("en", test_key)
    assert fake, "sanity"
    print(f"  smoke tr('tr', '{test_key}'): {locale_utils.tr('tr', test_key)[:50]}…")
    print()

    # --- Worst gaps summary ---
    gaps_by_lang: dict[str, list[str]] = defaultdict(list)
    for lang in EXTENDED_LANGS:
        for key in _CRITICAL_KEYS:
            if locale_utils.tr(lang, key) == _en_text(key):
                gaps_by_lang[lang].append(key)

    if gaps_by_lang:
        print("--- ACTION: critical gaps to fix ---")
        for lang, gap_keys in sorted(gaps_by_lang.items()):
            print(f"  {lang}: {', '.join(gap_keys)}")
    else:
        print("--- Critical user-facing keys: all extended langs have native text ---")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
