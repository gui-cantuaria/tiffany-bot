"""Central i18n middleware — binds per-user language before every interaction/command."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Optional

import discord
from discord.ext import commands

import locale_utils
from locale_utils import GuildLang

log = logging.getLogger("tiffany-bot")

_current_lang: ContextVar[Optional[GuildLang]] = ContextVar("tiffany_i18n_lang", default=None)
_current_user_id: ContextVar[Optional[int]] = ContextVar("tiffany_i18n_user", default=None)


def current_lang(*, fallback: GuildLang = "en") -> GuildLang:
    """Language bound for the current async context (interaction/command)."""
    lang = _current_lang.get()
    if lang is not None:
        return lang
    return fallback


def is_bound() -> bool:
    return _current_lang.get() is not None


def current_user_id() -> Optional[int]:
    return _current_user_id.get()


def clear_context() -> None:
    _current_lang.set(None)
    _current_user_id.set(None)


async def bind_user(
    user_id: int,
    *,
    discord_locale: Optional[str] = None,
) -> GuildLang:
    """Fetch user language (cache → Redis → PG → Discord locale → en) and bind to context."""
    lang = await locale_utils.resolve_lang_async(user_id, discord_locale=discord_locale)
    _current_lang.set(lang)
    _current_user_id.set(user_id)
    return lang


def bind_user_sync(
    user_id: int,
    *,
    discord_locale: Optional[str] = None,
) -> GuildLang:
    """Sync bind using in-memory/json prefs only (legacy paths)."""
    lang = locale_utils.resolve_lang(None, user_id, discord_locale=discord_locale)
    _current_lang.set(lang)
    _current_user_id.set(user_id)
    return lang


def _discord_locale_str(interaction: discord.Interaction) -> Optional[str]:
    loc = getattr(interaction, "locale", None)
    if loc is not None and hasattr(loc, "value"):
        return str(loc.value)
    if loc is not None:
        return str(loc)
    user = interaction.user
    uloc = getattr(user, "locale", None) if user else None
    if uloc is not None and hasattr(uloc, "value"):
        return str(uloc.value)
    if uloc is not None:
        return str(uloc)
    return None


async def bind_interaction(interaction: discord.Interaction) -> GuildLang:
    """Bind language for any Discord interaction (slash, buttons, selects, modals)."""
    if not interaction.user:
        clear_context()
        return "en"
    return await bind_user(interaction.user.id, discord_locale=_discord_locale_str(interaction))


async def bind_context(ctx: commands.Context) -> GuildLang:
    """Bind language for prefix/hybrid text commands."""
    if not ctx.author:
        clear_context()
        return "en"
    discord_locale = None
    if ctx.interaction:
        discord_locale = _discord_locale_str(ctx.interaction)
    return await bind_user(ctx.author.id, discord_locale=discord_locale)


def register_i18n_middleware(bot: commands.Bot) -> None:
    """Register global hooks that bind user language before handlers run."""

    @bot.listen("on_interaction")
    async def _i18n_on_interaction(interaction: discord.Interaction) -> None:
        try:
            await bind_interaction(interaction)
        except Exception as e:
            log.debug("i18n bind_interaction failed: %s", e)

    @bot.before_invoke
    async def _i18n_before_invoke(ctx: commands.Context) -> None:
        try:
            await bind_context(ctx)
        except Exception as e:
            log.debug("i18n bind_context failed: %s", e)
