"""Localized permission denial messages for Tiffany commands."""

from __future__ import annotations

from typing import Optional, Sequence

import discord
from discord.ext import commands

from locale_utils import GuildLang, hybrid_ctx_reply, slash_ephemeral, tr

TIFFANY_RED = 0xFF0000

_PERM_LABEL_KEYS: dict[str, str] = {
    "administrator": "perm.administrator",
    "manage_guild": "perm.manage_guild",
    "manage_messages": "perm.manage_messages",
    "manage_channels": "perm.manage_channels",
    "manage_roles": "perm.manage_roles",
    "attach_files": "perm.attach_files",
    "embed_links": "perm.embed_links",
    "send_messages": "perm.send_messages",
    "connect": "perm.connect",
    "speak": "perm.speak",
    "read_message_history": "perm.read_message_history",
    "add_reactions": "perm.add_reactions",
    "moderate_members": "perm.moderate_members",
    "ban_members": "perm.ban_members",
    "kick_members": "perm.kick_members",
}

_USER_PERM_OVERRIDES: dict[str, str] = {
    "mod-panel": "err.perms.mod_panel",
    "mod": "err.perms.mod_panel",
    "modpanel": "err.perms.mod_panel",
    "giveaway create": "gw.err.missing_perms",
    "giveaway end": "gw.err.missing_perms",
    "giveaway reroll": "gw.err.missing_perms",
}


def _command_key(command: object | None) -> str:
    if command is None:
        return ""
    qualified = getattr(command, "qualified_name", None) or getattr(command, "name", None) or ""
    return str(qualified).strip().lower()


def format_perm_list(lang: GuildLang, perm_names: Sequence[str]) -> str:
    labels: list[str] = []
    for name in perm_names:
        key = _PERM_LABEL_KEYS.get(name)
        labels.append(tr(lang, key) if key else name.replace("_", " ").title())
    return ", ".join(labels)


def user_missing_perms_message(
    lang: GuildLang,
    missing: Sequence[str],
    *,
    command: object | None = None,
) -> str:
    cmd_key = _command_key(command)
    override = _USER_PERM_OVERRIDES.get(cmd_key)
    if override:
        return tr(lang, override)
    return tr(lang, "err.perms.user", perms=format_perm_list(lang, missing))


def bot_missing_perms_message(
    lang: GuildLang,
    missing: Sequence[str],
    *,
    channel: object | None = None,
) -> str:
    perms = format_perm_list(lang, missing)
    mention = getattr(channel, "mention", None)
    if mention:
        return tr(lang, "err.perms.bot_channel", channel=mention, perms=perms)
    return tr(lang, "err.perms.bot", perms=perms)


def bot_channel_missing(
    channel: object | None,
    **required: bool,
) -> list[str]:
    """Return missing bot permission names in a guild channel (empty in DMs)."""
    if not channel or not required:
        return []
    guild = getattr(channel, "guild", None)
    if guild is None:
        return []
    me = guild.me
    if me is None:
        return [name for name, flag in required.items() if flag]
    if not hasattr(channel, "permissions_for"):
        return []
    perms = channel.permissions_for(me)
    missing: list[str] = []
    for name, flag in required.items():
        if flag and not getattr(perms, name, False):
            missing.append(name)
    return missing


def _unwrap_command_error(error: Exception) -> Exception:
    if isinstance(error, commands.CommandInvokeError):
        return error.original or error
    if isinstance(error, discord.app_commands.CommandInvokeError):
        return error.original or error
    if isinstance(error, commands.CheckFailure):
        original = getattr(error, "original", None)
        if original and original is not error:
            return _unwrap_command_error(original)
    return error


def resolve_command_error_message(
    lang: GuildLang,
    error: Exception,
    *,
    command: object | None = None,
) -> Optional[str]:
    """Map discord permission errors to a user-facing message, or None if unknown."""
    err = _unwrap_command_error(error)
    if isinstance(err, (commands.MissingPermissions, discord.app_commands.MissingPermissions)):
        missing = getattr(err, "missing_permissions", [])
        return user_missing_perms_message(lang, missing, command=command)
    if isinstance(err, (commands.BotMissingPermissions, discord.app_commands.BotMissingPermissions)):
        missing = getattr(err, "missing_permissions", [])
        return bot_missing_perms_message(lang, missing)
    if isinstance(err, (commands.NoPrivateMessage, discord.app_commands.NoPrivateMessage)):
        return tr(lang, "err.guild_only")
    if isinstance(err, (commands.CommandOnCooldown, discord.app_commands.CommandOnCooldown)):
        retry_sec = getattr(err, "retry_after", 0.0)
        return tr(lang, "err.cooldown", secs=f"{retry_sec:.0f}")
    if isinstance(err, (commands.CheckFailure, discord.app_commands.CheckFailure)):
        return tr(lang, "err.guild_only")
    return None


async def reply_command_permission_error(
    ctx: commands.Context,
    error: Exception,
    *,
    delete_after: float | None = 8,
) -> bool:
    from locale_utils import resolve_lang

    discord_locale = None
    if ctx.interaction:
        loc = getattr(ctx.interaction, "locale", None)
        if loc is not None and hasattr(loc, "value"):
            discord_locale = str(loc.value)
        elif loc is not None:
            discord_locale = str(loc)
    lang = resolve_lang(
        ctx.guild,
        ctx.author.id if ctx.author else None,
        discord_locale=discord_locale,
    )
    msg = resolve_command_error_message(lang, error, command=ctx.command)
    if not msg:
        return False
    await hybrid_ctx_reply(ctx, msg, error=True, delete_after=delete_after)
    return True


async def reply_slash_permission_error(
    interaction: discord.Interaction,
    error: Exception,
    *,
    command: object | None = None,
) -> bool:
    from locale_utils import resolve_lang

    lang = resolve_lang(
        interaction.guild,
        interaction.user.id if interaction.user else None,
    )
    cmd = command or interaction.command
    msg = resolve_command_error_message(lang, error, command=cmd)
    if not msg:
        return False
    embed = discord.Embed(description=msg, color=TIFFANY_RED)
    ephem = slash_ephemeral(interaction)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=ephem)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=ephem)
    except discord.HTTPException:
        return False
    return True
