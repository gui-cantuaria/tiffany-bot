"""Customizable giveaways — hybrid /giveaway + t!gw commands."""

from __future__ import annotations

import json
import logging
import os
import random
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

log = logging.getLogger("tiffany-bot")

BRAND_PINK = 0xFF69B4
_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "giveaways.json")
_MAX_ENTRIES_PER_GW = 10_000
_state: dict[str, Any] = {"active": {}, "ended": {}}
_loaded = False


def _load_state() -> None:
    global _loaded, _state
    if _loaded:
        return
    if os.path.exists(_STATE_FILE):
        try:
            with open(_STATE_FILE, "r", encoding="utf-8") as f:
                _state = json.load(f)
        except Exception as e:
            log.error("Failed to load giveaways.json: %s", e)
            _state = {"active": {}, "ended": {}}
    _state.setdefault("active", {})
    _state.setdefault("ended", {})
    _loaded = True


def _save_state() -> None:
    try:
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(_state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error("Failed to save giveaways.json: %s", e)


def _parse_duration(text: str) -> Optional[int]:
    """Parse duration like 30m, 2h, 1d into seconds."""
    m = re.fullmatch(r"(\d+)\s*([smhd])", (text or "").strip().lower())
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(unit, 0)
    if not mult or n <= 0:
        return None
    return n * mult


def _fmt_remaining(seconds: float) -> str:
    s = max(0, int(seconds))
    if s >= 86400:
        return f"{s // 86400}d {(s % 86400) // 3600}h"
    if s >= 3600:
        return f"{s // 3600}h {(s % 3600) // 60}m"
    if s >= 60:
        return f"{s // 60}m {s % 60}s"
    return f"{s}s"


def _build_giveaway_embed(gw: dict, *, ended: bool = False) -> discord.Embed:
    ends_at = float(gw.get("ends_at") or 0)
    remaining = ends_at - time.time()
    winners = int(gw.get("winners") or 1)
    entries = gw.get("entries") or []
    host_id = int(gw.get("host_id") or 0)
    prize = (gw.get("prize") or "Prêmio").strip()

    em = discord.Embed(
        title="🎁 Sorteio Tiffany",
        description=f"**Prêmio:** {prize[:500]}",
        color=BRAND_PINK if not ended else 0x808080,
    )
    em.add_field(name="Vencedores", value=str(winners), inline=True)
    em.add_field(name="Participantes", value=str(len(entries)), inline=True)
    if ended:
        em.add_field(name="Status", value="Encerrado", inline=True)
    else:
        em.add_field(name="Termina em", value=_fmt_remaining(remaining), inline=True)
    if host_id:
        em.set_footer(text=f"Host: {host_id} · t!gw list · /giveaway")
    return em


class GiveawayEnterView(discord.ui.View):
    def __init__(self, giveaway_id: str):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        btn = discord.ui.Button(
            label="Participar",
            emoji="🎉",
            style=discord.ButtonStyle.success,
            custom_id=f"tiffany_gw_enter:{giveaway_id}",
        )
        btn.callback = self._enter_callback
        self.add_item(btn)

    async def _enter_callback(self, interaction: discord.Interaction):
        if interaction.user.bot:
            await interaction.response.send_message("Bots não podem participar.", ephemeral=True)
            return
        _load_state()
        gw = _state["active"].get(self.giveaway_id)
        if not gw:
            await interaction.response.send_message(
                "Este sorteio já encerrou ou não existe mais.", ephemeral=True,
            )
            return
        if time.time() >= float(gw.get("ends_at") or 0):
            await interaction.response.send_message("Sorteio encerrado.", ephemeral=True)
            return
        uid = interaction.user.id
        entries = gw.setdefault("entries", [])
        if uid in entries:
            await interaction.response.send_message("Você já está participando! 🎀", ephemeral=True)
            return
        if len(entries) >= _MAX_ENTRIES_PER_GW:
            await interaction.response.send_message(
                "Este sorteio atingiu o limite de participantes.", ephemeral=True,
            )
            return
        entries.append(uid)
        _save_state()
        await interaction.response.send_message("Você entrou no sorteio! Boa sorte ✨", ephemeral=True)
        try:
            if interaction.message:
                await interaction.message.edit(embed=_build_giveaway_embed(gw), view=self)
        except Exception:
            pass


async def _finish_giveaway(bot: commands.Bot, gw_id: str, *, reroll: bool = False) -> Optional[list[int]]:
    _load_state()
    gw = _state["active"].pop(gw_id, None)
    if not gw:
        return None
    entries = list(dict.fromkeys(gw.get("entries") or []))
    winners_n = max(1, min(int(gw.get("winners") or 1), len(entries) or 1))
    picked: list[int] = []
    if entries:
        pool = entries.copy()
        random.shuffle(pool)
        picked = pool[:winners_n]
    gw["winners_picked"] = picked
    gw["ended_at"] = time.time()
    _state["ended"][gw_id] = gw
    _save_state()

    channel_id = int(gw.get("channel_id") or 0)
    msg_id = int(gw.get("message_id") or 0)
    channel = bot.get_channel(channel_id)
    if channel is None and channel_id:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception:
            channel = None
    if channel and msg_id:
        try:
            msg = await channel.fetch_message(msg_id)
            await msg.edit(embed=_build_giveaway_embed(gw, ended=True), view=None)
        except Exception:
            pass
    return picked


class GiveawaysCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        _load_state()
        for gw_id in _state.get("active", {}):
            self.bot.add_view(GiveawayEnterView(gw_id))
        self._expire_loop.start()

    def cog_unload(self):
        self._expire_loop.cancel()

    @tasks.loop(seconds=30)
    async def _expire_loop(self):
        _load_state()
        now = time.time()
        expired = [
            gid for gid, gw in _state.get("active", {}).items()
            if now >= float(gw.get("ends_at") or 0)
        ]
        for gw_id in expired:
            picked = await _finish_giveaway(self.bot, gw_id)
            if picked is None:
                continue
            gw = _state["ended"].get(gw_id, {})
            channel_id = int(gw.get("channel_id") or 0)
            channel = self.bot.get_channel(channel_id)
            if channel is None and channel_id:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except Exception:
                    channel = None
            prize = gw.get("prize") or "Prêmio"
            if channel and picked:
                mentions = " ".join(f"<@{u}>" for u in picked)
                await channel.send(
                    embed=discord.Embed(
                        title="🎉 Sorteio encerrado!",
                        description=f"**Prêmio:** {prize[:300]}\n\nVencedor(es): {mentions}",
                        color=BRAND_PINK,
                    )
                )
            elif channel:
                await channel.send(
                    embed=discord.Embed(
                        title="🎁 Sorteio encerrado",
                        description=f"**Prêmio:** {prize[:300]}\n\nNinguém participou desta vez.",
                        color=0x808080,
                    )
                )

    @_expire_loop.before_loop
    async def _before_expire(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawaysCog(bot))

    @bot.hybrid_group(
        name="giveaway",
        aliases=["gw"],
        invoke_without_command=True,
        description="Customizable Tiffany giveaways",
        dm_permission=False,
    )
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def cmd_giveaway(ctx: commands.Context):
        await ctx.send(
            embed=discord.Embed(
                title="🎁 Sorteios Tiffany",
                description=(
                    "**Comandos (t! ou /):**\n"
                    "`t!gw create <tempo> <vencedores> <prêmio>` — ex: `t!gw create 2h 1 Nitro Discord`\n"
                    "`t!gw end [id]` — encerra agora\n"
                    "`t!gw reroll [id]` — sorteia de novo\n"
                    "`t!gw list` — sorteios ativos\n\n"
                    "Tempo: `30m`, `2h`, `1d`"
                ),
                color=BRAND_PINK,
            )
        )

    @cmd_giveaway.command(name="create", aliases=["c", "new"])
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def gw_create(
        ctx: commands.Context,
        duration: str,
        winners: int,
        *,
        prize: str,
    ):
        if not ctx.guild:
            await ctx.send("Use em um servidor.", ephemeral=True)
            return
        secs = _parse_duration(duration)
        if not secs or secs < 60:
            await ctx.send("Tempo inválido. Use ex: `30m`, `2h`, `1d` (mínimo 1 min).")
            return
        if winners < 1 or winners > 20:
            await ctx.send("Número de vencedores: entre **1** e **20**.")
            return
        prize = (prize or "").strip()
        if len(prize) < 2:
            await ctx.send("Descreva o prêmio.")
            return

        gw_id = uuid.uuid4().hex[:12]
        ends_at = time.time() + secs
        gw = {
            "id": gw_id,
            "guild_id": ctx.guild.id,
            "channel_id": ctx.channel.id,
            "host_id": ctx.author.id,
            "prize": prize[:500],
            "winners": winners,
            "ends_at": ends_at,
            "entries": [],
            "created_at": time.time(),
        }
        view = GiveawayEnterView(gw_id)
        em = _build_giveaway_embed(gw)
        msg = await ctx.send(embed=em, view=view)
        gw["message_id"] = msg.id
        _load_state()
        _state["active"][gw_id] = gw
        _save_state()
        bot.add_view(view)
        await ctx.send(
            embed=discord.Embed(
                description=f"Sorteio criado! ID: `{gw_id}` · termina em **{_fmt_remaining(secs)}**",
                color=BRAND_PINK,
            ),
            delete_after=15,
        )

    @gw_create.error
    async def gw_create_error(ctx: commands.Context, error: Exception):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Precisa da permissão **Gerenciar servidor**.", ephemeral=True)

    @cmd_giveaway.command(name="end", aliases=["stop", "finish"])
    @commands.has_permissions(manage_guild=True)
    async def gw_end(ctx: commands.Context, gw_id: str = ""):
        _load_state()
        if not gw_id:
            active = [
                g for g in _state["active"].values()
                if int(g.get("guild_id") or 0) == ctx.guild.id
            ]
            if len(active) != 1:
                await ctx.send("Informe o ID: `t!gw end <id>` ou deixe só um sorteio ativo.")
                return
            gw_id = active[0]["id"]
        gw = _state["active"].get(gw_id)
        if not gw or int(gw.get("guild_id") or 0) != ctx.guild.id:
            await ctx.send("Sorteio não encontrado ou já encerrado neste servidor.")
            return
        picked = await _finish_giveaway(ctx.bot, gw_id)
        if picked:
            mentions = " ".join(f"<@{u}>" for u in picked)
            await ctx.send(
                embed=discord.Embed(
                    title="🎉 Sorteio encerrado!",
                    description=f"Vencedor(es): {mentions}",
                    color=BRAND_PINK,
                )
            )
        else:
            await ctx.send("Sorteio encerrado — nenhum participante.")

    @cmd_giveaway.command(name="reroll", aliases=["rr"])
    @commands.has_permissions(manage_guild=True)
    async def gw_reroll(ctx: commands.Context, gw_id: str = ""):
        _load_state()
        if not gw_id:
            ended = [
                g for g in _state["ended"].values()
                if int(g.get("guild_id") or 0) == ctx.guild.id
            ]
            if not ended:
                await ctx.send("Nenhum sorteio encerrado neste servidor.")
                return
            gw = ended[-1]
            gw_id = gw["id"]
        else:
            gw = _state["ended"].get(gw_id)
        if not gw or int(gw.get("guild_id") or 0) != ctx.guild.id:
            await ctx.send("Sorteio encerrado não encontrado neste servidor.")
            return
        entries = list(dict.fromkeys(gw.get("entries") or []))
        if not entries:
            await ctx.send("Sem participantes para reroll.")
            return
        winners_n = max(1, min(int(gw.get("winners") or 1), len(entries)))
        picked = random.sample(entries, winners_n)
        mentions = " ".join(f"<@{u}>" for u in picked)
        await ctx.send(
            embed=discord.Embed(
                title="🔄 Reroll",
                description=f"Novo(s) vencedor(es): {mentions}",
                color=BRAND_PINK,
            )
        )

    @cmd_giveaway.command(name="list", aliases=["ls"])
    async def gw_list(ctx: commands.Context):
        _load_state()
        active = [
            g for g in _state["active"].values()
            if int(g.get("guild_id") or 0) == (ctx.guild.id if ctx.guild else 0)
        ]
        if not active:
            await ctx.send("Nenhum sorteio ativo neste servidor.")
            return
        lines = []
        for g in active:
            rem = _fmt_remaining(float(g.get("ends_at") or 0) - time.time())
            lines.append(
                f"• `{g['id']}` — **{g.get('prize', '?')[:40]}** · "
                f"{len(g.get('entries') or [])} entradas · {rem}"
            )
        await ctx.send(
            embed=discord.Embed(
                title="🎁 Sorteios ativos",
                description="\n".join(lines)[:4000],
                color=BRAND_PINK,
            )
        )
