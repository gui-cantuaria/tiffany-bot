#!/usr/bin/env python3
"""Generate hi / vi / uk locale JSON from _catalog_en.json via OpenRouter."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv(ROOT / ".env")

TARGETS = {
    "hi": "Hindi (Devanagari script, natural Indian Hindi)",
    "vi": "Vietnamese (natural Vietnamese, diacritics)",
    "uk": "Ukrainian (natural Ukrainian, Cyrillic)",
}

BATCH = 45
MODEL = "google/gemini-3.1-flash-lite"

HELP_KEYS = (
    "help.title", "help.desc", "help.music.title", "help.music.body",
    "help.chat.title", "help.chat.body", "help.dice.title", "help.dice.body",
    "help.settings.title", "help.settings.body", "help.footer", "slash.cmd.help",
)
VOLUME_KEYS = (
    "volume.title", "volume.global", "volume.client_title", "volume.client_body",
    "volume.footer", "volume.ytdlp_note", "premium.upsell",
)

FOOTER_16 = {
    "en": "🌐 **`/language`** — 16 languages: EN · PT · ES · FR · DE · TR · SV · IT · NL · AR · JA · KO · RU · HI · VI · UK",
    "hi": "🌐 **`/language`** — 16 भाषाएँ: EN · PT · ES · FR · DE · TR · SV · IT · NL · AR · JA · KO · RU · HI · VI · UK",
    "vi": "🌐 **`/language`** — 16 ngôn ngữ: EN · PT · ES · FR · DE · TR · SV · IT · NL · AR · JA · KO · RU · HI · VI · UK",
    "uk": "🌐 **`/language`** — 16 мов: EN · PT · ES · FR · DE · TR · SV · IT · NL · AR · JA · KO · RU · HI · VI · UK",
}


def _preserve_placeholders(text: str) -> str:
    return text


async def _translate_batch(
    client: AsyncOpenAI,
    lang_code: str,
    lang_name: str,
    batch: dict[str, str],
) -> dict[str, str]:
    payload = json.dumps(batch, ensure_ascii=False, indent=2)
    prompt = (
        f"Translate each JSON string value to {lang_name} for a Discord bot named Tiffany.\n"
        "Rules:\n"
        "- Keep JSON keys unchanged.\n"
        "- Preserve placeholders like {{name}}, {{secs}}, {{pct}}, {{cmd}}, {{mention}} exactly.\n"
        "- Keep Discord markdown (**bold**, `code`, emojis).\n"
        "- Keep command names (/play, t!p, /stats) and brand names (YouTube, Spotify, Steam, Epic, WARP) unchanged.\n"
        "- Use /stats (not /status) for public bot health.\n"
        "- Return ONLY a valid JSON object with the same keys.\n\n"
        f"{payload}"
    )
    resp = await client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Model returned non-object JSON")
    return {k: str(v) for k, v in data.items()}


async def translate_catalog(catalog: dict[str, str], lang_code: str, lang_name: str) -> dict[str, str]:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY missing")
    client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    keys = list(catalog.keys())
    out: dict[str, str] = {}
    for i in range(0, len(keys), BATCH):
        chunk_keys = keys[i : i + BATCH]
        batch = {k: catalog[k] for k in chunk_keys}
        translated = await _translate_batch(client, lang_code, lang_name, batch)
        for k in chunk_keys:
            out[k] = translated.get(k, catalog[k])
        print(f"  {lang_code}: {min(i + BATCH, len(keys))}/{len(keys)}")
    return out


def write_lang(lang: str, catalog: dict[str, str]) -> None:
    lang_dir = ROOT / "locales" / lang
    lang_dir.mkdir(parents=True, exist_ok=True)
    (lang_dir / "bot.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    help_data = {k: catalog[k] for k in HELP_KEYS if k in catalog}
    if "help.footer" in help_data and lang in FOOTER_16:
        help_data["help.footer"] = help_data["help.footer"].replace(
            "13 languages", "16 languages"
        ).replace("13 idiomas", "16 idiomas").replace("13 langues", "16 langues")
        help_data["help.footer"] = FOOTER_16[lang]
    (lang_dir / "help.json").write_text(
        json.dumps(help_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    vol_data = {k: catalog[k] for k in VOLUME_KEYS if k in catalog}
    (lang_dir / "volume.json").write_text(
        json.dumps(vol_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {lang}: bot={len(catalog)} help={len(help_data)} volume={len(vol_data)}")


async def main() -> int:
    catalog_path = ROOT / "locales" / "_catalog_en.json"
    if not catalog_path.exists():
        import locale_utils  # noqa: WPS433
        strings = locale_utils._STRINGS
        catalog = {k: b["en"] for k, b in sorted(strings.items()) if b.get("en")}
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

    for lang, name in TARGETS.items():
        print(f"Translating {lang}...")
        translated = await translate_catalog(catalog, lang, name)
        write_lang(lang, translated)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
