"""Giveaway persistence — PostgreSQL when DATABASE_URL set, else giveaways.json."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Optional

from infra import postgres

log = logging.getLogger("tiffany-bot")

_STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "giveaways.json")


def use_database() -> bool:
    return postgres.db_enabled() and postgres.pool() is not None


async def create_giveaway(
    *,
    guild_id: int,
    channel_id: int,
    host_id: int,
    prize: str,
    winner_count: int,
    ends_at: float,
    requirements: Optional[dict] = None,
    embed_style: Optional[dict] = None,
) -> str:
    """Return giveaway id (UUID string)."""
    gw_id = str(uuid.uuid4())
    if use_database():
        pool = postgres.pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO giveaways (id, guild_id, channel_id, host_id, prize, winner_count, ends_at, requirements, embed_style)
                VALUES ($1::uuid, $2, $3, $4, $5, $6, to_timestamp($7), $8::jsonb, $9::jsonb)
                """,
                gw_id,
                guild_id,
                channel_id,
                host_id,
                prize,
                winner_count,
                ends_at,
                json.dumps(requirements or {}),
                json.dumps(embed_style or {}),
            )
        return gw_id
    # JSON fallback handled by giveaways_cog today
    return gw_id


async def list_active() -> list[dict[str, Any]]:
    if not use_database():
        return []
    pool = postgres.pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM giveaways WHERE status = 'active' AND ends_at > now()"
        )
    return [dict(r) for r in rows]
