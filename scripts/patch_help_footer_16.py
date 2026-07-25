#!/usr/bin/env python3
"""Patch help.footer in all locale help.json files to list 16 languages."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOOTER = (
    "🌐 **`/language`** — 16 languages: "
    "EN · PT · ES · FR · DE · TR · SV · IT · NL · AR · JA · KO · RU · HI · VI · UK"
)
REPLACEMENTS = [
    ("13 languages", "16 languages"),
    ("13 idiomas", "16 idiomas"),
    ("13 langues", "16 langues"),
    ("13 Sprachen", "16 Sprachen"),
    ("13言語", "16言語"),
    ("13개", "16개"),
    ("13 языков", "16 языков"),
    ("13 dil", "16 dil"),
    ("13 språk", "16 språk"),
    ("13 lingue", "16 lingue"),
    ("13 talen", "16 talen"),
    ("13 لغة", "16 لغة"),
    ("13 доступно", "16 доступно"),
    ("· RU", "· RU · HI · VI · UK"),
]


def main() -> int:
    locales = ROOT / "locales"
    for path in sorted(locales.glob("*/help.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        footer = data.get("help.footer", "")
        if not footer:
            continue
        new_footer = footer
        for old, new in REPLACEMENTS:
            new_footer = new_footer.replace(old, new)
        if "HI · VI · UK" not in new_footer and "help.footer" in data:
            # Force canonical suffix if still old list
            if "RU" in new_footer and "HI" not in new_footer:
                new_footer = FOOTER if path.parent.name == "en" else new_footer
        data["help.footer"] = new_footer
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Updated {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
