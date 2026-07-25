"""Premium entitlements — Redis cache (5 min) + PostgreSQL source of truth."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Optional

import discord
from discord.ext import commands
from brand_colors import TIFFANY_PINK, TIFFANY_RED

from infra import postgres, redis_client

log = logging.getLogger("tiffany-bot")

CACHE_TTL = int(os.getenv("PREMIUM_CACHE_TTL_SEC", "300"))
TIER_RANK = {"free": 0, "premium": 1, "premium_plus": 2}


@dataclass
class Entitlement:
    tier: str = "free"
    expires_at: Optional[datetime] = None
    source: str = "grant"

    def covers(self, required: str) -> bool:
        if self.expires_at and self.expires_at < datetime.now(timezone.utc):
            return required == "free"
        return TIER_RANK.get(self.tier, 0) >= TIER_RANK.get(required, 0)

    def to_json(self) -> str:
        return json.dumps({
            "tier": self.tier,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "source": self.source,
        })

    @classmethod
    def from_json(cls, raw: str) -> "Entitlement":
        data = json.loads(raw)
        exp = data.get("expires_at")
        expires = datetime.fromisoformat(exp) if exp else None
        return cls(tier=data.get("tier", "free"), expires_at=expires, source=data.get("source", "grant"))


def _cache_key(*, guild_id: Optional[int] = None, user_id: Optional[int] = None) -> str:
    if guild_id is not None:
        return f"ent:g:{guild_id}"
    if user_id is not None:
        return f"ent:u:{user_id}"
    raise ValueError("guild_id or user_id required")


async def invalidate_entitlement(*, guild_id: Optional[int] = None, user_id: Optional[int] = None) -> None:
    key = _cache_key(guild_id=guild_id, user_id=user_id)
    await redis_client.cache_delete(key)


async def get_entitlement(
    *,
    guild_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> Entitlement:
    key = _cache_key(guild_id=guild_id, user_id=user_id)
    cached = await redis_client.cache_get(key)
    if cached:
        try:
            return Entitlement.from_json(cached)
        except Exception:
            pass

    ent = Entitlement()
    pool = postgres.pool()
    if pool is not None:
        stype = "guild" if guild_id is not None else "user"
        sid = guild_id if guild_id is not None else user_id
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT tier, expires_at, source FROM subscriptions
                    WHERE subject_type = $1 AND subject_id = $2
                      AND (expires_at IS NULL OR expires_at > now())
                    ORDER BY tier DESC
                    LIMIT 1
                    """,
                    stype,
                    sid,
                )
                if row:
                    ent = Entitlement(
                        tier=row["tier"],
                        expires_at=row["expires_at"],
                        source=row["source"],
                    )
        except Exception as e:
            log.debug("Premium DB lookup failed: %s", e)

    await redis_client.cache_setex(key, CACHE_TTL, ent.to_json())
    return ent


async def handle_discord_subscription_event(payload: dict[str, Any]) -> None:
    """Process Discord Entitlement / App Subscription webhook payload (invalidate + upsert)."""
    # Discord sends varying shapes — normalize best-effort
    entitlements = payload.get("entitlements") or [payload]
    pool = postgres.pool()
    for item in entitlements:
        if not isinstance(item, dict):
            continue
        user_id = item.get("user_id") or item.get("user", {}).get("id")
        guild_id = item.get("guild_id")
        sku_id = item.get("sku_id") or item.get("subscription_id")
        deleted = item.get("deleted", False) or payload.get("type", "").endswith("DELETE")

        if guild_id:
            await invalidate_entitlement(guild_id=int(guild_id))
        if user_id:
            await invalidate_entitlement(user_id=int(user_id))

        if pool is None or deleted:
            continue
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO subscriptions (subject_type, subject_id, tier, source, external_id, expires_at)
                    VALUES ($1, $2, 'premium', 'discord_app_sub', $3, NULL)
                    ON CONFLICT (subject_type, subject_id, source)
                    DO UPDATE SET tier = EXCLUDED.tier, external_id = EXCLUDED.external_id, updated_at = now()
                    """,
                    "guild" if guild_id else "user",
                    int(guild_id or user_id),
                    str(sku_id or ""),
                )
        except Exception as e:
            log.warning("Failed to upsert subscription: %s", e)


def requires_premium(tier: str = "premium"):
    """Decorator for slash/hybrid handlers — checks guild entitlement only when needed."""

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(ctx: commands.Context, *args, **kwargs):
            guild_id = ctx.guild.id if ctx.guild else None
            if guild_id is None:
                await ctx.send(embed=discord.Embed(description="Premium feature — guild only.", color=TIFFANY_RED))
                return
            ent = await get_entitlement(guild_id=guild_id)
            if not ent.covers(tier):
                import locale_utils
                lang = locale_utils.resolve_lang(ctx.guild, ctx.author.id)
                await ctx.send(
                    embed=discord.Embed(
                        description=locale_utils.tr(lang, "premium.upsell"),
                        color=TIFFANY_PINK,
                    ),
                    ephemeral=bool(ctx.interaction),
                )
                return
            return await func(ctx, *args, **kwargs)

        return wrapper

    return decorator
