"""
Tiffany Bot — Subscription Service
==================================
Manages the lifecycle of Premium Subscriptions, decoupling Discord commands
from Stripe APIs and Database queries.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional, Any

from infra import postgres

log = logging.getLogger("tiffany-bot")

# Load pricing config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "pricing.json")
try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        PRICING_CONFIG = json.load(f).get("plans", {})
except Exception as e:
    log.error("Failed to load pricing config: %s", e)
    PRICING_CONFIG = {}

class SubscriptionService:
    
    @staticmethod
    async def get_plan(subject_id: int, subject_type: str = "guild", conn: Any = None) -> str:
        """Returns the active plan name for a user or guild, or 'free'. Reuses DB conn if provided."""
        if conn is not None:
            try:
                row = await conn.fetchrow(
                    """
                    SELECT tier, expires_at 
                    FROM subscriptions 
                    WHERE subject_id = $1 AND subject_type = $2 AND cancelled_at IS NULL
                    """,
                    int(subject_id), subject_type
                )
                if row:
                    return row["tier"]
            except Exception as e:
                log.warning("SubscriptionService.get_plan error on provided conn: %s", e)
            return "free"

        pool = postgres.pool()
        if not pool:
            return "free"
            
        try:
            async with pool.acquire() as db_conn:
                row = await db_conn.fetchrow(
                    """
                    SELECT tier, expires_at 
                    FROM subscriptions 
                    WHERE subject_id = $1 AND subject_type = $2 AND cancelled_at IS NULL
                    """,
                    int(subject_id), subject_type
                )
                if row:
                    return row["tier"]
        except Exception as e:
            log.warning("SubscriptionService.get_plan error: %s", e)
            
        return "free"

    @staticmethod
    def get_plan_details(plan_name: str) -> dict[str, Any]:
        """Returns plan details from config."""
        return PRICING_CONFIG.get(plan_name.lower(), PRICING_CONFIG.get("free", {}))

    @staticmethod
    async def check_discount_eligibility(guild: Any) -> Optional[str]:
        """
        Business Logic: Decides if a guild deserves a promotion code.
        Requires >10,000 members AND at least 30 days of bot presence AND >500 commands (simulated).
        """
        if not guild or not hasattr(guild, "member_count"):
            return None
            
        # 1. Member Count Check
        if guild.member_count < 10000:
            return None
            
        # 2. Time in server check (simulated via guild.me.joined_at)
        import datetime

        import discord
        if guild.me and guild.me.joined_at:
            days_in_server = (discord.utils.utcnow() - guild.me.joined_at).days
            if days_in_server < 30:
                return None
                
        # 3. Command Usage check (Assuming we'd query DB for command logs)
        # For this implementation, if they pass the first two, we'll grant it.
        # In a full production env, add: command_count = await query_commands(guild.id)
        
        return "PARTNER50"
