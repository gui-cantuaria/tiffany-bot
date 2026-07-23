"""Automatic chat moderation — spam, scams, sensitive content (phase B)."""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from typing import Optional

import discord
from discord.ext import commands

import guild_config

log = logging.getLogger("tiffany-bot")

# Flood: max messages in window
_FLOOD_LIMIT = 6
_FLOOD_WINDOW_SEC = 4.0

_msg_times: dict[tuple[int, int], list[float]] = defaultdict(list)

_SCAM_RE = re.compile(
    r"(?i)"
    r"(discord(?:app)?\.(?:com|gift)|discord-nitro|free\s+nitro|steamcommun[il]ty|"
    r"steamcornmunity|st[e3]am\s*gift|airdrop\s+crypto|binance\s+giveaway|"
    r"claim\s+your\s+nitro|@everyone\s+free|nitro\s+for\s+free|"
    r"discord\.gg/[a-z0-9]{8,}.*nitro|"
    r"onlyfans\s+leak|onlyfans\s+free|"
    r"cp\s+link|child\s+porn|"
    r"send\s+nudes|pack\s+vip\s+gr[aá]tis)"
)

_INVITE_SPAM_RE = re.compile(
    r"(?i)(discord(?:\.gg|app\.com/invite)/[a-z0-9-]{2,})"
)

_NSFW_HEURISTIC_RE = re.compile(
    r"(?i)\b(porn|xxx|hentai|nude|nudes|onlyfans|nsfw|18\+|\+18|sexo\s+explicito)\b"
)

_registered = False


def _trim_flood(guild_id: int, user_id: int) -> list[float]:
    key = (guild_id, user_id)
    now = time.monotonic()
    times = [t for t in _msg_times[key] if now - t < _FLOOD_WINDOW_SEC]
    _msg_times[key] = times
    return times


def _needs_ai_scan(content: str) -> bool:
    if not content or len(content.strip()) < 8:
        return False
    if _SCAM_RE.search(content):
        return True
    if len(_INVITE_SPAM_RE.findall(content)) >= 2:
        return True
    if _NSFW_HEURISTIC_RE.search(content):
        return True
    caps = sum(1 for c in content if c.isupper())
    if len(content) >= 20 and caps / max(len(content), 1) > 0.7:
        return True
    return False


async def _ai_chat_moderation(text: str) -> tuple[bool, str]:
    """Return (should_action, reason). Uses tiffany_voice OpenRouter client."""
    import tiffany_voice as tv
    client = tv._get_openrouter_client()
    if client is None:
        return False, ""
    snippet = text.strip()[:400]
    try:
        async with tv._ai_semaphore:
            resp = await client.chat.completions.create(
                model="google/gemini-3.1-flash-lite",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You moderate Discord chat for a gaming/tech community. "
                            "Reply with ONE line: ACTION|REASON\n"
                            "ACTION is ALLOW, DELETE, or WARN.\n"
                            "DELETE for: scam links (fake Nitro/Steam), phishing, crypto fraud, "
                            "explicit sexual content, gore, harassment, doxxing, illegal sales, "
                            "self-harm encouragement, spam advertising.\n"
                            "WARN for mild spam or suspicious but not clearly malicious.\n"
                            "ALLOW for normal conversation.\n"
                            "REASON short PT-BR phrase for the user (max 80 chars)."
                        ),
                    },
                    {"role": "user", "content": snippet},
                ],
                max_tokens=40,
                temperature=0.0,
                timeout=10.0,
            )
        raw = (resp.choices[0].message.content or "").strip()
        parts = raw.split("|", 1)
        action = parts[0].strip().upper()
        reason = parts[1].strip() if len(parts) > 1 else "Conteúdo não permitido."
        if action.startswith("DELETE"):
            return True, reason[:120]
        return False, reason[:120]
    except Exception as e:
        log.debug("AI chat moderation failed: %s", e)
        return False, ""


async def _log_mod(guild: discord.Guild, embed: discord.Embed) -> None:
    await guild_config.log_mod_action(guild, embed)


async def _notify_user(
    author: discord.Member,
    channel: discord.abc.Messageable,
    text: str,
) -> None:
    import tiffany_voice as tv
    await tv._send_private_notice(author, channel, text)


def register(bot: commands.Bot) -> None:
    global _registered
    if _registered:
        return
    _registered = True

    @bot.listen("on_message")
    async def _auto_moderation(message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if guild_config.is_blacklisted(message.guild.id, message.author.id):
            return

        content = message.content or ""
        guild_id = message.guild.id

        # --- Flood (anti_spam) ---
        if guild_config.is_anti_spam_enabled(guild_id) and content.strip():
            times = _trim_flood(guild_id, message.author.id)
            times.append(time.monotonic())
            _msg_times[(guild_id, message.author.id)] = times
            if len(times) >= _FLOOD_LIMIT:
                me = message.guild.me
                if me and message.channel.permissions_for(me).manage_messages:
                    try:
                        await message.delete()
                    except discord.HTTPException:
                        pass
                await _notify_user(
                    message.author,
                    message.channel,
                    "🛡️ Calma aí — você está mandando mensagens rápido demais (anti-spam).",
                )
                await _log_mod(
                    message.guild,
                    discord.Embed(
                        title="Anti-spam",
                        description=f"{message.author.mention} flood ({len(times)} msgs)",
                        color=0xED2939,
                    ),
                )
                return

        # --- Fast scam regex (always on when anti_spam) ---
        if guild_config.is_anti_spam_enabled(guild_id) and _SCAM_RE.search(content):
            me = message.guild.me
            if me and message.channel.permissions_for(me).manage_messages:
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass
            await _notify_user(
                message.author,
                message.channel,
                "🛡️ Mensagem removida — link ou texto suspeito (golpe/phishing).",
            )
            await _log_mod(
                message.guild,
                discord.Embed(
                    title="Scam bloqueado",
                    description=f"{message.author.mention}: `{content[:200]}`",
                    color=0xED2939,
                ),
            )
            return

        # --- AI layer (strict_filter guilds, heuristic trigger) ---
        if not guild_config.is_strict_filter_enabled(guild_id):
            return
        if not _needs_ai_scan(content):
            return

        blocked, reason = await _ai_chat_moderation(content)
        if not blocked:
            return

        me = message.guild.me
        if me and message.channel.permissions_for(me).manage_messages:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
        user_msg = f"🛡️ {reason or 'Conteúdo removido pelas diretrizes do servidor.'}"
        await _notify_user(message.author, message.channel, user_msg)
        await _log_mod(
            message.guild,
            discord.Embed(
                title="Moderação IA",
                description=f"{message.author.mention}\n{reason}\n`{content[:300]}`",
                color=0xED2939,
            ),
        )
