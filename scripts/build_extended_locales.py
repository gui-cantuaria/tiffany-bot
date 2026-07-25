#!/usr/bin/env python3
"""Build locales/{lang}/bot.json + volume.json for extended languages."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EXTENDED = ("tr", "sv", "it", "nl", "ar", "ja", "ko", "ru")
VOLUME_KEYS = (
    "volume.title",
    "volume.global",
    "volume.client_title",
    "volume.client_body",
    "volume.footer",
    "volume.ytdlp_note",
    "premium.upsell",
)

LANG_CODES = {
    "tr": "tr",
    "sv": "sv",
    "it": "it",
    "nl": "nl",
    "ar": "ar",
    "ja": "ja",
    "ko": "ko",
    "ru": "ru",
}

_PLACEHOLDER_RE = re.compile(r"\{[a-zA-Z0-9_]+\}")


def _protect(text: str) -> tuple[str, list[str]]:
    tokens: list[str] = []

    def repl(m: re.Match[str]) -> str:
        tokens.append(m.group(0))
        return f"__PH{len(tokens) - 1}__"

    return _PLACEHOLDER_RE.sub(repl, text), tokens


def _restore(text: str, tokens: list[str]) -> str:
    out = text
    for i, tok in enumerate(tokens):
        out = out.replace(f"__PH{i}__", tok)
        out = out.replace(f"__ PH {i} __", tok)
        out = out.replace(f"__PH {i}__", tok)
    return out


def _load_json(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if isinstance(v, str)}


def _translate_batch(translator, texts: list[str]) -> list[str]:
    if not texts:
        return []
    try:
        return list(translator.translate_batch(texts))
    except Exception:
        out: list[str] = []
        for t in texts:
            try:
                out.append(translator.translate(t))
                time.sleep(0.05)
            except Exception:
                out.append(t)
        return out


def build_lang(lang: str, *, dry_run: bool = False) -> int:
    from deep_translator import GoogleTranslator
    import locale_utils
    from roleplay_i18n import ROLEPLAY_I18N

    strings = locale_utils._STRINGS
    all_keys = sorted(strings.keys())
    en_vol = _load_json(ROOT / "locales" / "en" / "volume.json")
    existing_help = _load_json(ROOT / "locales" / lang / "help.json")
    existing_vol = _load_json(ROOT / "locales" / lang / "volume.json")

    bot: dict[str, str] = {}
    for key in all_keys:
        if key in VOLUME_KEYS:
            continue
        bucket = strings.get(key, {})
        if lang in bucket:
            bot[key] = bucket[lang]
            continue
        if key in existing_help:
            bot[key] = existing_help[key]
            continue
        rp = ROLEPLAY_I18N.get(key, {})
        if lang in rp:
            bot[key] = rp[lang]
            continue
        en = bucket.get("en")
        if en:
            bot[key] = en  # placeholder until translated

    to_translate: list[tuple[str, str, list[str]]] = []
    for key, val in list(bot.items()):
        bucket = strings.get(key, {})
        if lang in bucket or key in existing_help or lang in ROLEPLAY_I18N.get(key, {}):
            continue
        if val == bucket.get("en"):
            protected, tokens = _protect(val)
            to_translate.append((key, protected, tokens))

    if not dry_run and to_translate:
        translator = GoogleTranslator(source="en", target=LANG_CODES[lang])
        batch_size = 40
        for i in range(0, len(to_translate), batch_size):
            chunk = to_translate[i : i + batch_size]
            texts = [c[1] for c in chunk]
            translated = _translate_batch(translator, texts)
            for (key, _prot, tokens), tr_text in zip(chunk, translated):
                bot[key] = _restore(tr_text or bot[key], tokens)
            time.sleep(0.2)

    # Force 13-language about/help footer strings from _STRINGS when available
    for key in ("about.language.body", "help.footer", "lang.desc", "lang.placeholder", "lang.title", "lang.changed"):
        if lang in strings.get(key, {}):
            bot[key] = strings[key][lang]

    volume: dict[str, str] = {}
    for vk in VOLUME_KEYS:
        if vk in existing_vol:
            volume[vk] = existing_vol[vk]
        elif lang in strings.get(vk, {}):
            volume[vk] = strings[vk][lang]
        elif vk in en_vol:
            volume[vk] = en_vol[vk]

    vol_missing = [k for k in VOLUME_KEYS if k not in volume or volume[k] == en_vol.get(k)]
    if not dry_run and vol_missing:
        translator = GoogleTranslator(source="en", target=LANG_CODES[lang])
        for vk in vol_missing:
            src = en_vol.get(vk, "")
            if not src:
                continue
            protected, tokens = _protect(src)
            try:
                tr_text = translator.translate(protected)
                volume[vk] = _restore(tr_text, tokens)
            except Exception:
                volume[vk] = src

    lang_dir = ROOT / "locales" / lang
    lang_dir.mkdir(parents=True, exist_ok=True)
    if not dry_run:
        (lang_dir / "bot.json").write_text(
            json.dumps(dict(sorted(bot.items())), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (lang_dir / "volume.json").write_text(
            json.dumps(dict(sorted(volume.items())), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    pending = sum(1 for k in all_keys if k not in bot and k not in VOLUME_KEYS)
    print(f"{lang}: bot={len(bot)} volume={len(volume)} pending={pending} machine={len(to_translate)}")
    return len(bot)


def main() -> int:
    langs = EXTENDED
    if len(sys.argv) > 1:
        langs = tuple(a for a in sys.argv[1:] if a in EXTENDED)
    dry = "--dry-run" in sys.argv
    for lang in langs:
        build_lang(lang, dry_run=dry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
