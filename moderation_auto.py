"""Automod listener — delegates L1/L2 to infra.moderation.pipeline."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands
from brand_colors import TIFFANY_RED

import guild_config
from infra.moderation.pipeline import ModerationAction, get_pipeline
from infra.moderation import rules

log = logging.getLogger("tiffany-bot")

_registered = False


async def _ai_chat_moderation(text: str) -> tuple[bool, str]:
    """L3 async AI scan."""
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
                            "DELETE for: scam links, phishing, crypto fraud, explicit sexual content, "
                            "gore, harassment, doxxing, illegal sales, self-harm encouragement, spam ads.\n"
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
        log.warning("AI chat moderation failed: %s", e)
        if rules.l1_scam_match(text):
            return True, "Link ou texto suspeito (golpe/phishing)."
        return False, ""


async def _log_mod(guild: discord.Guild, embed: discord.Embed) -> None:
    await guild_config.log_mod_action(guild, embed)


async def _notify_user(author: discord.Member, channel: discord.abc.Messageable, text: str) -> None:
    import tiffany_voice as tv
    await tv._send_private_notice(author, channel, text)


async def _apply_result(message: discord.Message, result, *, default_title: str) -> None:
    if result.action == ModerationAction.NONE:
        return
    me = message.guild.me if message.guild else None
    if me and message.channel.permissions_for(me).manage_messages:
        try:
            await message.delete()
        except discord.HTTPException as e:
            log.warning(f"Failed to delete flagged message: {e}")
    await _notify_user(message.author, message.channel, f"🛡️ {result.reason}")
    await _log_mod(
        message.guild,
        discord.Embed(
            title=default_title,
            description=f"{message.author.mention} [{result.layer}]\n{result.reason}\n`{(message.content or '')[:300]}`",
            color=TIFFANY_RED,
        ),
    )


def register(bot: commands.Bot) -> None:
    global _registered
    if _registered:
        return
    _registered = True
    pipeline = get_pipeline()

    @bot.listen("on_message")
    async def _auto_moderation(message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # L1 + L2 + Safe Browsing (sync/fast)
        result = await pipeline.run_l1_l2(message)
        if result.action != ModerationAction.NONE:
            title = "Anti-spam" if result.layer == "L2" else "Moderação automática"
            if "Safe Browsing" in result.reason or result.layer == "L1-GSB":
                title = "Link bloqueado"
            elif "phishing" in result.reason.lower() or "golpe" in result.reason.lower():
                title = "Scam bloqueado"
            await _apply_result(message, result, default_title=title)
            return

        # L3 AI (async path — only strict_filter + heuristic)
        if not pipeline.needs_l3_ai(message):
            return

        import tiffany_voice as tv
        if not tv._ai_rate_limit_consume(
            message.guild.id, bucket="moderation", user_id=message.author.id,
        ):
            return

        blocked, reason = await _ai_chat_moderation(message.content or "")
        if not blocked:
            return

        await _apply_result(
            message,
            type("R", (), {"action": ModerationAction.DELETE, "reason": reason, "layer": "L3"})(),
            default_title="Moderação IA",
        )
