"""User-scoped preferences (language) — PostgreSQL with JSON file fallback."""

from __future__ import annotations

import logging
from typing import Optional

from infra import postgres

log = logging.getLogger("tiffany-bot")

_VALID_LANGS = frozenset({
    "en", "pt", "es", "fr", "de",
    "tr", "sv", "it", "nl", "ar", "ja", "ko", "ru",
})


async def get_language(user_id: int) -> Optional[str]:
    """Return saved language for user_id or None."""
    if not postgres.db_enabled():
        return None
    pool = postgres.pool()
    if pool is None:
        return None
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchval(
                "SELECT lang FROM user_preferences WHERE user_id = $1",
                user_id,
            )
            if row and row in _VALID_LANGS:
                return row
    except Exception as e:
        log.debug("user_preferences.get_language failed uid=%s: %s", user_id, e)
    return None


async def set_language(user_id: int, lang: str) -> None:
    """Upsert user language preference."""
    if lang not in _VALID_LANGS:
        return
    if not postgres.db_enabled():
        return
    pool = postgres.pool()
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_preferences (user_id, lang, updated_at)
                VALUES ($1, $2, now())
                ON CONFLICT (user_id) DO UPDATE
                SET lang = EXCLUDED.lang, updated_at = now()
                """,
                user_id,
                lang,
            )
    except Exception as e:
        log.warning("user_preferences.set_language failed uid=%s: %s", user_id, e)


async def migrate_json_batch(prefs: dict[str, str]) -> int:
    """One-time bulk import from user_lang_prefs.json into PostgreSQL."""
    if not prefs or not postgres.db_enabled():
        return 0
    pool = postgres.pool()
    if pool is None:
        return 0
    count = 0
    try:
        async with pool.acquire() as conn:
            for uid_str, lang in prefs.items():
                if lang not in _VALID_LANGS:
                    continue
                try:
                    uid = int(uid_str)
                except (TypeError, ValueError):
                    continue
                await conn.execute(
                    """
                    INSERT INTO user_preferences (user_id, lang, updated_at)
                    VALUES ($1, $2, now())
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    uid,
                    lang,
                )
                count += 1
    except Exception as e:
        log.warning("user_preferences.migrate_json_batch failed: %s", e)
    return count
