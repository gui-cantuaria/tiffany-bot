#!/usr/bin/env python3
"""Audit i18n coverage: _STRINGS core langs vs JSON locales vs roleplay_i18n."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EXTENDED = ("tr", "sv", "it", "nl", "ar", "ja", "ko", "ru")
CORE = ("en", "pt", "es", "fr", "de")


def _load_strings_dict() -> dict[str, dict[str, str]]:
    import locale_utils

    return dict(locale_utils._STRINGS)


def _json_keys(lang: str) -> set[str]:
    d = ROOT / "locales" / lang
    keys: set[str] = set()
    if not d.is_dir():
        return keys
    for p in d.glob("*.json"):
        if p.name == "meta.json":
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            keys.update(k for k, v in data.items() if isinstance(v, str))
    return keys


def main() -> int:
    strings = _load_strings_dict()
    all_keys = sorted(strings.keys())
    print(f"_STRINGS keys: {len(all_keys)}")

    from roleplay_i18n import ROLEPLAY_I18N

    rp_keys = set(ROLEPLAY_I18N.keys())
    print(f"roleplay_i18n keys: {len(rp_keys)}")

    for lang in EXTENDED:
        in_strings = {k for k in all_keys if lang in strings.get(k, {})}
        json_k = _json_keys(lang)
        rp_k = {k for k in rp_keys if lang in ROLEPLAY_I18N.get(k, {})}
        covered = json_k | rp_k | in_strings
        missing = [k for k in all_keys if k not in covered and k not in rp_keys]
        missing_rp = [k for k in rp_keys if k not in rp_k and k not in json_k]
        print(
            f"{lang}: strings={len(in_strings)} json={len(json_k)} rp={len(rp_k)} "
            f"missing_total={len(missing)} missing_rp={len(missing_rp)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
