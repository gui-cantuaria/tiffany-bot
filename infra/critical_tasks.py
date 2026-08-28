"""Watchdog for news/offers background loops — auto-restart if a deploy, bug, or stall stops them."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING, Callable, Awaitable

if TYPE_CHECKING:
    from discord.ext import commands, tasks

log = logging.getLogger("tiffany-bot")

_FUSO_BR = timezone(timedelta(hours=-3))
_offers_reload_attempts = 0
MAX_OFFERS_RELOAD_ATTEMPTS = 3

_last_news_heartbeat: float = time.time()
_last_offers_heartbeat: float = time.time()


def record_news_heartbeat() -> None:
    global _last_news_heartbeat
    _last_news_heartbeat = time.time()


def record_offers_heartbeat() -> None:
    global _last_offers_heartbeat
    _last_offers_heartbeat = time.time()


def reset_offers_reload_attempts() -> None:
    global _offers_reload_attempts
    _offers_reload_attempts = 0


async def ensure_critical_loops(
    bot: commands.Bot,
    *,
    news_task: tasks.Loop,
    reload_offers: Callable[[], Awaitable[None]] | None = None,
    hora_inicio: int = 7,
    hora_fim: int = 23,
    max_stall_seconds: float = 7200.0,
) -> None:
    """Restart news/offers loops if they stopped or stalled; retry offers cog load up to 3 times."""
    global _offers_reload_attempts, _last_news_heartbeat, _last_offers_heartbeat

    if not bot.is_ready():
        return

    now = time.time()
    now_br = datetime.now(_FUSO_BR)
    is_active_hours = hora_inicio <= now_br.hour < hora_fim

    # 1. News loop health check
    if not news_task.is_running():
        log.error("WATCHDOG: news loop stopped — restarting verificar_feeds")
        try:
            news_task.start()
            record_news_heartbeat()
        except Exception as e:
            log.exception(f"WATCHDOG: failed to start verificar_feeds: {e}")
    elif is_active_hours and (now - _last_news_heartbeat) > max_stall_seconds:
        log.warning(
            "WATCHDOG: news loop appears stalled (no heartbeat in %.1f hours) — restarting",
            (now - _last_news_heartbeat) / 3600,
        )
        try:
            news_task.cancel()
            news_task.start()
            record_news_heartbeat()
        except Exception as e:
            log.exception(f"WATCHDOG: failed to restart stalled news loop: {e}")

    # 2. Offers cog & loop health check
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
    if deals_loop is not None:
        if not deals_loop.is_running():
            log.error("WATCHDOG: offers loop stopped — restarting deals_loop")
            try:
                deals_loop.start()
                record_offers_heartbeat()
            except Exception as e:
                log.exception(f"WATCHDOG: failed to start deals_loop: {e}")
        elif is_active_hours and (now - _last_offers_heartbeat) > max_stall_seconds:
            log.warning(
                "WATCHDOG: offers loop appears stalled (no heartbeat in %.1f hours) — restarting",
                (now - _last_offers_heartbeat) / 3600,
            )
            try:
                deals_loop.cancel()
                deals_loop.start()
                record_offers_heartbeat()
            except Exception as e:
                log.exception(f"WATCHDOG: failed to restart stalled offers loop: {e}")
