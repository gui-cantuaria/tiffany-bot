"""
Tiffany Bot — Telemetry Service
===============================
Records all core operations (especially AI requests) for dashboard reporting,
billing transparency, and analytics.
"""

from __future__ import annotations

import logging
from typing import Optional

from infra import postgres

log = logging.getLogger("tiffany-bot")

class TelemetryService:
    @staticmethod
    async def record_ai_usage(
        user_id: int, 
        guild_id: Optional[int], 
        model: str, 
        tokens: int, 
        latency_ms: int,
        quota_used: int,
        cache_hit: bool,
        success: bool = True,
        error_msg: str = ""
    ) -> None:
        """Records an AI usage event into the telemetry table."""
        pool = postgres.pool()
        if not pool:
            return
            
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO telemetry_ai_usage 
                    (user_id, guild_id, model, tokens, latency_ms, quota_used, cache_hit, success, error_msg, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
                    """,
                    str(user_id),
                    str(guild_id) if guild_id else None,
                    model,
                    tokens,
                    latency_ms,
                    quota_used,
                    cache_hit,
                    success,
                    error_msg
                )
        except Exception as e:
            # We don't want telemetry failures to break the bot's core flow
            log.warning("Failed to record AI telemetry: %s", e)
