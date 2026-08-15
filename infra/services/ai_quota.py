"""
Tiffany Bot — AI Quota Service
==============================
Manages daily quota units for AI generation based on dynamic model weights
and subscription plans, completely decoupled from the Discord layer.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from typing import Optional, Tuple, Any

from infra import postgres
from infra.services.subscription import SubscriptionService
from infra.services.telemetry import TelemetryService

log = logging.getLogger("tiffany-bot")

# Load model weights config
MODELS_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "ai_models.json")
try:
    with open(MODELS_CONFIG_PATH, "r", encoding="utf-8") as f:
        MODELS_CONFIG = json.load(f).get("models", {})
except Exception as e:
    log.error("Failed to load AI models config: %s", e)
    MODELS_CONFIG = {}


class AIQuotaService:
    
    @staticmethod
    async def _get_today_str() -> str:
        return datetime.datetime.utcnow().strftime("%Y-%m-%d")

    @staticmethod
    def get_model_weight(model_name: str) -> int:
        """Returns the cost (in Quota Units) of a specific model."""
        model_data = MODELS_CONFIG.get(model_name.lower())
        return model_data.get("weight", 1) if model_data else 1

    @staticmethod
    async def get_remaining(user_id: int, guild_id: Optional[int] = None, conn: Optional[Any] = None) -> Tuple[int, bool]:
        """
        Returns (remaining_units, is_using_guild_pool), reusing DB connection if provided to prevent pool exhaustion.
        """
        if conn is not None:
            return await AIQuotaService._check_limits_on_conn(conn, user_id, guild_id)

        pool = postgres.pool()
        if not pool:
            return 0, False
            
        async with pool.acquire() as db_conn:
            return await AIQuotaService._check_limits_on_conn(db_conn, user_id, guild_id)

    @staticmethod
    async def _check_limits_on_conn(conn: Any, user_id: int, guild_id: Optional[int]) -> Tuple[int, bool]:
        today = await AIQuotaService._get_today_str()
        
        # 1. Determine User Plan & Limits (passing conn to avoid nested acquire in SubscriptionService)
        user_plan = await SubscriptionService.get_plan(user_id, subject_type="user", conn=conn)
        user_details = SubscriptionService.get_plan_details(user_plan)
        user_limit = user_details.get("daily_ai_quotas", 30) # Corrected fallback to match pricing.json Free Tier
        
        # Check user usage
        user_used = await conn.fetchval(
            "SELECT quota_used FROM ai_usage_daily WHERE subject_type = 'user' AND subject_id = $1 AND day = $2::date",
            int(user_id), today
        ) or 0
        
        user_remaining = max(0, user_limit - user_used)
        if user_remaining > 0:
            return user_remaining, False
            
        # 2. If user is out, check Guild Limit (if in a guild)
        if guild_id:
            guild_plan = await SubscriptionService.get_plan(guild_id, subject_type="guild", conn=conn)
            guild_details = SubscriptionService.get_plan_details(guild_plan)
            guild_limit = guild_details.get("daily_ai_quotas", 0)
            
            if guild_limit > 0:
                guild_used = await conn.fetchval(
                    "SELECT quota_used FROM ai_usage_daily WHERE subject_type = 'guild' AND subject_id = $1 AND day = $2::date",
                    int(guild_id), today
                ) or 0
                
                guild_remaining = max(0, guild_limit - guild_used)
                if guild_remaining > 0:
                    return guild_remaining, True

        return 0, False

    @staticmethod
    async def can_use(user_id: int, guild_id: Optional[int], model_name: str) -> bool:
        """Checks if the user has enough Quota Units for the model."""
        cost = AIQuotaService.get_model_weight(model_name)
        remaining, _ = await AIQuotaService.get_remaining(user_id, guild_id)
        return remaining >= cost

    @staticmethod
    async def consume(user_id: int, guild_id: Optional[int], model_name: str, latency_ms: int = 0) -> bool:
        """
        Consumes Quota Units for the model. Records telemetry. Reuses active connection.
        """
        cost = AIQuotaService.get_model_weight(model_name)
        
        pool = postgres.pool()
        if not pool:
            return False

        today = await AIQuotaService._get_today_str()
        
        async with pool.acquire() as conn:
            # Check limits reusing the active connection (no nested pool acquisition!)
            remaining, use_guild = await AIQuotaService.get_remaining(user_id, guild_id, conn=conn)
            
            if remaining < cost:
                # Log rate limit event
                await TelemetryService.record_ai_usage(
                    user_id, guild_id, model_name, 0, latency_ms, 0, False, False, "Rate Limited: Out of Quota Units"
                )
                return False 
                
            # Upsert usage
            await conn.execute(
                """
                INSERT INTO ai_usage_daily (subject_type, subject_id, day, quota_used)
                VALUES ($1, $2, $3::date, $4)
                ON CONFLICT (subject_type, subject_id, day) 
                DO UPDATE SET quota_used = ai_usage_daily.quota_used + $4
                """,
                'guild' if use_guild else 'user',
                int(guild_id) if use_guild else int(user_id),
                today, cost
            )
            
            # Record successful telemetry
            await TelemetryService.record_ai_usage(
                user_id, guild_id, model_name, cost * 100, latency_ms, cost, False, True, ""
            )
            return True

    @staticmethod
    def upgrade_message(lang, user_id: int) -> str:
        from infra import postgres
        from locale_utils import tr
        
        if not postgres.pool():
            return tr(lang, "ai_quota.err.offline")
            
        return tr(lang, "ai_quota.err.exceeded")

    @staticmethod
    async def grant_credits(
        user_id: int, 
        credits: int, 
        reason: str = "Admin bonus grant", 
        granted_by: Optional[int] = None
    ) -> dict[str, Any]:
        """
        Securely grants bonus AI quota units to a user.
        Server-side permission enforcement & transaction audit ledger.
        """
        if credits <= 0 or credits > 100000:
            raise ValueError("Amount of credits must be between 1 and 100,000.")

        pool = postgres.pool()
        today = await AIQuotaService._get_today_str()
        
        if pool:
            async with pool.acquire() as conn:
                # Reduce quota_used (negative offset = bonus capacity) or insert negative usage
                await conn.execute(
                    """
                    INSERT INTO ai_usage_daily (subject_type, subject_id, day, quota_used)
                    VALUES ('user', $1, $2::date, $3)
                    ON CONFLICT (subject_type, subject_id, day)
                    DO UPDATE SET quota_used = GREATEST(0, ai_usage_daily.quota_used - $4)
                    """,
                    int(user_id), today, 0, credits
                )
                
                # Get new remaining balance
                new_rem, _ = await AIQuotaService.get_remaining(user_id, conn=conn)

                # Record admin audit telemetry
                await TelemetryService.record_ai_usage(
                    user_id, None, "admin_grant", 0, 0, credits, True, True, f"Admin {granted_by or 0} granted {credits} credits: {reason}"
                )
                
                return {
                    "status": "SUCCESS",
                    "user_id": user_id,
                    "credits_granted": credits,
                    "reason": reason,
                    "granted_by": granted_by,
                    "new_remaining": new_rem
                }

        return {
            "status": "OFFLINE_MOCK",
            "user_id": user_id,
            "credits_granted": credits,
            "reason": reason,
            "granted_by": granted_by,
            "new_remaining": credits
        }

