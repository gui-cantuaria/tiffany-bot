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


def _parse_database_url(url: str) -> tuple[str, dict[str, Any]]:
    """Strip libpq-style query params that asyncpg expects as kwargs."""
    from urllib.parse import parse_qs, urlparse, urlunparse

    parsed = urlparse(url)
    if not parsed.query:
        return url, {}
    qs = parse_qs(parsed.query, keep_blank_values=True)
    kwargs: dict[str, Any] = {}
    ssl_vals = qs.pop("ssl", [])
    if ssl_vals and ssl_vals[0].lower() in ("disable", "false", "0", "off"):
        kwargs["ssl"] = False
    clean_query = "&".join(f"{k}={v[0]}" for k, v in qs.items() if v)
    clean = urlunparse(parsed._replace(query=clean_query))
    return clean, kwargs


async def init_db() -> None:
    global _pool
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        log.info("DATABASE_URL unset — JSON file persistence for giveaways/embeds")
        return
    try:
        import asyncpg
        clean_url, pool_kwargs = _parse_database_url(url)
        _pool = await asyncpg.create_pool(
            clean_url,
            min_size=1,
            max_size=10,
            command_timeout=30,
            **pool_kwargs,
        )
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
    """Apply all schema/*.sql in order (idempotent CREATE IF NOT EXISTS)."""
    if _pool is None:
        return
    schema_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "schema",
    )
    if not os.path.isdir(schema_dir):
        log.warning("Migration directory missing: %s", schema_dir)
        return
    sql_files = sorted(f for f in os.listdir(schema_dir) if f.endswith(".sql"))
    if not sql_files:
        log.warning("No SQL migrations found in %s", schema_dir)
        return
    async with _pool.acquire() as conn:
        for fname in sql_files:
            path = os.path.join(schema_dir, fname)
            with open(path, "r", encoding="utf-8") as f:
                sql = f.read()
            await conn.execute(sql)
            log.info("PostgreSQL schema applied (%s)", fname)
