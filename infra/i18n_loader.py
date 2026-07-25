"""Namespaced JSON locale loader — overlays locale_utils._STRINGS (PG overlay later)."""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

log = logging.getLogger("tiffany-bot")

_LOCALES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locales")

# All supported Tiffany languages (priority order for partial translations)
SUPPORTED_LANGS: tuple[str, ...] = (
    "en", "pt", "es", "fr", "de",
    "tr", "sv", "it", "nl", "ar", "ja", "ko", "ru",
    "hi", "vi", "uk",
)

_FALLBACK_CHAIN: tuple[str, ...] = ("en",)

_cache: dict[str, dict[str, str]] = {}
_loaded = False


def _load_lang(lang: str) -> dict[str, str]:
    lang_dir = os.path.join(_LOCALES_DIR, lang)
    merged: dict[str, str] = {}
    if not os.path.isdir(lang_dir):
        return merged
    for fname in sorted(os.listdir(lang_dir)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(lang_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, str):
                        merged[k] = v
        except Exception as e:
            log.warning("Failed to load locale file %s: %s", path, e)
    return merged


def ensure_loaded() -> None:
    global _loaded, _cache
    if _loaded:
        return
    for lang in SUPPORTED_LANGS:
        _cache[lang] = _load_lang(lang)
    _loaded = True
    total = sum(len(v) for v in _cache.values())
    log.info("i18n JSON catalog: %d strings across %d langs", total, len(_cache))


def lookup(lang: str, key: str) -> Optional[str]:
    """Return string from JSON catalog or None."""
    ensure_loaded()
    bucket = _cache.get(lang) or {}
    if key in bucket:
        return bucket[key]
    for fb in _FALLBACK_CHAIN:
        if fb == lang:
            continue
        fb_bucket = _cache.get(fb) or {}
        if key in fb_bucket:
            return fb_bucket[key]
    return None


async def lookup_db(lang: str, key: str) -> Optional[str]:
    """Future: load from PostgreSQL i18n_strings (hot cache in Redis)."""
    from infra import postgres, redis_client
    if not postgres.db_enabled():
        return None
    ck = f"i18n:{lang}:{key}"
    cached = await redis_client.cache_get(ck)
    if cached:
        return cached
    pool = postgres.pool()
    if pool is None:
        return None
    try:
        async with pool.acquire() as conn:
            val = await conn.fetchval(
                "SELECT value FROM i18n_strings WHERE key_id = $1 AND lang = $2",
                key,
                lang,
            )
            if val:
                await redis_client.cache_setex(ck, 3600, val)
            return val
    except Exception:
        return None
