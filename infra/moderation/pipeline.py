"""Three-layer automod pipeline — sync L1/L2, async L3 queue."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import discord

import guild_config
from infra import redis_client
from infra.moderation import rules
from infra.moderation.safe_browsing import check_urls

log = logging.getLogger("tiffany-bot")

FLOOD_LIMIT = 6
FLOOD_WINDOW_SEC = 4


class ModerationAction(str, Enum):
    NONE = "none"
    DELETE = "delete"
    WARN = "warn"


@dataclass
class ModerationResult:
    action: ModerationAction
    reason: str = ""
    layer: str = "L1"


class ModerationPipeline:
    """Run L1 (regex) + L2 (Redis flood) synchronously; L3 AI is separate async hook."""

    async def check_flood(self, guild_id: int, user_id: int) -> bool:
        """Return True if flood detected."""
        key = f"flood:{guild_id}:{user_id}"
        count = await redis_client.cache_incr(key, ttl_sec=FLOOD_WINDOW_SEC)
        return count >= FLOOD_LIMIT

    async def run_l1_l2(self, message: discord.Message) -> ModerationResult:
        content = message.content or ""
        guild_id = message.guild.id if message.guild else 0

        if not guild_config.is_anti_spam_enabled(guild_id):
            return ModerationResult(ModerationAction.NONE)

        # L2 flood
        if content.strip() and await self.check_flood(guild_id, message.author.id):
            return ModerationResult(
                ModerationAction.DELETE,
                "Anti-spam: mensagens rápido demais.",
                layer="L2",
            )

        # L1 scam
        if rules.l1_scam_match(content):
            return ModerationResult(
                ModerationAction.DELETE,
                "Link ou texto suspeito (golpe/phishing).",
                layer="L1",
            )

        # Safe Browsing on URLs (cached — fast after first hit)
        urls = rules.extract_urls(content)
        if urls:
            threat, reason = await check_urls(urls)
            if threat:
                return ModerationResult(ModerationAction.DELETE, reason, layer="L1-GSB")

        return ModerationResult(ModerationAction.NONE)

    def needs_l3_ai(self, message: discord.Message) -> bool:
        if not message.guild:
            return False
        if not guild_config.is_strict_filter_enabled(message.guild.id):
            return False
        return rules.needs_ai_scan(message.content or "")


_pipeline: Optional[ModerationPipeline] = None


def get_pipeline() -> ModerationPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ModerationPipeline()
    return _pipeline
