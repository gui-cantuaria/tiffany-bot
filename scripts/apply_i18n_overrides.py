#!/usr/bin/env python3
"""Merge locales/_overrides/<lang>.json into locales/<lang>/bot.json (no AI)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OVERRIDES_DIR = ROOT / "locales" / "_overrides"


def apply_lang(lang: str) -> int:
    override_path = OVERRIDES_DIR / f"{lang}.json"
    bot_path = ROOT / "locales" / lang / "bot.json"
    if not override_path.exists():
        return 0
    if not bot_path.exists():
        print(f"skip {lang}: no bot.json")
        return 0
    overrides = json.loads(override_path.read_text(encoding="utf-8"))
    data = json.loads(bot_path.read_text(encoding="utf-8"))
    changed = 0
    for key, val in overrides.items():
        if data.get(key) != val:
            data[key] = val
            changed += 1
    if changed:
        bot_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{lang}: applied {changed}/{len(overrides)} overrides")
    return changed


def main() -> int:
    if not OVERRIDES_DIR.is_dir():
        print("No overrides directory")
        return 1
    total = 0
    for path in sorted(OVERRIDES_DIR.glob("*.json")):
        total += apply_lang(path.stem)
    print(f"Total keys updated: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
