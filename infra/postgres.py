"""Optional PostgreSQL pool — asyncpg when DATABASE_URL is set."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

log = logging.getLogger("tiffany-bot")

_pool: Any = None


def db_enabled() -> bool:
    return bool(os.getenv("DATABASE_URL", "").strip())


async def init_db() -> None:
    global _pool
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        log.info("DATABASE_URL unset — JSON file persistence for giveaways/embeds")
        return
    try:
        import asyncpg
        _pool = await asyncpg.create_pool(url, min_size=1, max_size=10, command_timeout=30)
        log.info("PostgreSQL pool ready")
    except ImportError:
        log.warning("asyncpg not installed — pip install asyncpg for DB features")
    except Exception as e:
        log.warning("PostgreSQL unavailable (%s) — JSON fallback", e)


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> Any:
    return _pool


@asynccontextmanager
async def acquire() -> AsyncIterator[Any]:
    if _pool is None:
        raise RuntimeError("Database not initialized")
    async with _pool.acquire() as conn:
        yield conn


async def run_migrations() -> None:
    """Apply schema/001_initial.sql if tables missing (idempotent CREATE IF NOT EXISTS)."""
    if _pool is None:
        return
    schema_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "schema",
        "001_initial.sql",
    )
    if not os.path.exists(schema_path):
        log.warning("Migration file missing: %s", schema_path)
        return
    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()
    async with _pool.acquire() as conn:
        await conn.execute(sql)
    log.info("PostgreSQL schema applied (001_initial.sql)")
