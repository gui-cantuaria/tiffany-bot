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
from typing import Optional, Tuple

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
    async def get_remaining(user_id: int, guild_id: Optional[int] = None) -> Tuple[int, bool]:
        """
        Returns (remaining_units, is_using_guild_pool)
        """
        pool = postgres.pool()
        if not pool:
            return 0, False
            
        today = await AIQuotaService._get_today_str()
        
        # 1. Determine User Plan & Limits
        user_plan = await SubscriptionService.get_plan(user_id, subject_type="user")
        user_details = SubscriptionService.get_plan_details(user_plan)
        user_limit = user_details.get("daily_ai_quotas", 3000)
        
        async with pool.acquire() as conn:
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
                guild_plan = await SubscriptionService.get_plan(guild_id, subject_type="guild")
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
        Consumes Quota Units for the model. Records telemetry.
        """
        cost = AIQuotaService.get_model_weight(model_name)
        
        pool = postgres.pool()
        if not pool:
            return False

        today = await AIQuotaService._get_today_str()
        
        async with pool.acquire() as conn:
            # Check limits
            remaining, use_guild = await AIQuotaService.get_remaining(user_id, guild_id)
            
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
    def upgrade_message(user_id: int) -> str:
        return (
            "⚠️ **Daily AI Quota Reached!**\n"
            "You have exhausted your daily quota units for AI generation.\n"
            "Upgrade to **Tiffany Plus** or **Tiffany Pro** to unlock massive limits and access to advanced models like GPT-4o and Claude Sonnet.\n"
            "Type `/premium` to view plans!"
        )
