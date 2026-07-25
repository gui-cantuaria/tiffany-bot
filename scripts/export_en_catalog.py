#!/usr/bin/env python3
"""Export English i18n catalog for extended-language translation files."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EXTENDED = ("tr", "sv", "it", "nl", "ar", "ja", "ko", "ru", "hi", "vi", "uk")


def main() -> int:
    import locale_utils

    strings = locale_utils._STRINGS
    catalog: dict[str, str] = {}
    for key, bucket in sorted(strings.items()):
        en = bucket.get("en")
        if en:
            catalog[key] = en

    out = ROOT / "locales" / "_catalog_en.json"
    out.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(catalog)} keys to {out}")

    for lang in EXTENDED:
        missing = [k for k in catalog if lang not in strings.get(k, {})]
        print(f"{lang} needs {len(missing)} translations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
