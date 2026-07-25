"""Watchdog for news/offers background loops — auto-restart if a deploy or bug stops them."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Awaitable

if TYPE_CHECKING:
    from discord.ext import commands, tasks

log = logging.getLogger("tiffany-bot")

_offers_reload_attempts = 0
MAX_OFFERS_RELOAD_ATTEMPTS = 3


def reset_offers_reload_attempts() -> None:
    global _offers_reload_attempts
    _offers_reload_attempts = 0


async def ensure_critical_loops(
    bot: commands.Bot,
    *,
    news_task: tasks.Loop,
    reload_offers: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """Restart news/offers loops if they stopped; retry offers cog load up to 3 times."""
    global _offers_reload_attempts

    if not bot.is_ready():
        return

    if not news_task.is_running():
        log.error("WATCHDOG: news loop stopped — restarting verificar_feeds")
        news_task.start()

    cog = bot.get_cog("OffersCog")
    if cog is None and reload_offers and _offers_reload_attempts < MAX_OFFERS_RELOAD_ATTEMPTS:
        _offers_reload_attempts += 1
        log.warning(
            "WATCHDOG: OffersCog missing — reload attempt %d/%d",
            _offers_reload_attempts,
            MAX_OFFERS_RELOAD_ATTEMPTS,
        )
        try:
            await reload_offers()
            cog = bot.get_cog("OffersCog")
            if cog is not None:
                reset_offers_reload_attempts()
        except Exception:
            log.exception("WATCHDOG: offers_cog reload failed")

    cog = bot.get_cog("OffersCog")
    if cog is None:
        return

    deals_loop = getattr(cog, "deals_loop", None)
    if deals_loop is not None and not deals_loop.is_running():
        log.error("WATCHDOG: offers loop stopped — restarting deals_loop")
        deals_loop.start()
