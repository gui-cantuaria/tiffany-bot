"""Guild embed templates — create, edit, list, send (t!emb / /embed)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from locale_utils import (
    hybrid_desc_kwargs,
    slash_desc_kwargs,
    slash_param,
    resolve_lang,
    hybrid_ctx_reply,
    hybrid_defer,
    tr,
    GuildLang,
)


def _ctx_lang(ctx: commands.Context) -> GuildLang:
    return resolve_lang(ctx.guild, ctx.author.id if ctx.author else None)

log = logging.getLogger("tiffany-bot")

from brand_colors import TIFFANY_PINK as BRAND_PINK
_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guild_embeds.json")
_cache: dict[str, dict[str, dict[str, Any]]] = {}
_loaded = False


def _load() -> None:
    global _loaded, _cache
    if _loaded:
        return
    if os.path.exists(_STATE_FILE):
        try:
            with open(_STATE_FILE, "r", encoding="utf-8") as f:
                _cache = json.load(f)
        except Exception as e:
            log.error("Failed to load guild_embeds.json: %s", e)
            _cache = {}
    _loaded = True


def _save() -> None:
    try:
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error("Failed to save guild_embeds.json: %s", e)


def _guild_bucket(guild_id: int) -> dict[str, dict[str, Any]]:
    _load()
    return _cache.setdefault(str(guild_id), {})


def _normalize_embed_name(name: str) -> str:
    return re.sub(r"[^\w\-]", "", (name or "").strip().lower())


def _embed_is_postable(data: dict[str, Any]) -> bool:
    em = _build_from_data(data)
    return bool(
        em.title
        or em.description
        or em.fields
        or em.image
        or em.thumbnail
        or em.footer
    )


def _channel_send_perms(channel: discord.TextChannel) -> discord.Permissions | None:
    if not channel.guild or not channel.guild.me:
        return None
    return channel.permissions_for(channel.guild.me)


def _parse_color(raw: str) -> int:
    s = (raw or "").strip().lower()
    if not s:
        return BRAND_PINK
    if s.startswith("#"):
        s = s[1:]
    if s.startswith("0x"):
        s = s[2:]
    try:
        return int(s, 16)
    except ValueError:
        return BRAND_PINK


def _build_from_data(data: dict[str, Any]) -> discord.Embed:
    em = discord.Embed(
        title=(data.get("title") or "")[:256] or None,
        description=(data.get("description") or "")[:4096] or None,
        color=int(data.get("color") or BRAND_PINK),
    )
    footer = (data.get("footer") or "").strip()
    if footer:
        em.set_footer(text=footer[:2048])
    thumb = (data.get("thumbnail") or "").strip()
    if thumb:
        em.set_thumbnail(url=thumb[:512])
    image = (data.get("image") or "").strip()
    if image:
        em.set_image(url=image[:512])
    for field in data.get("fields") or []:
        if not isinstance(field, dict):
            continue
        name = (field.get("name") or "")[:256]
        value = (field.get("value") or "")[:1024]
        if name and value:
            em.add_field(name=name, value=value, inline=bool(field.get("inline")))
    return em


def _empty_embed_data() -> dict[str, Any]:
    return {
        "title": "",
        "description": "",
        "color": BRAND_PINK,
        "footer": "",
        "thumbnail": "",
        "image": "",
        "fields": [],
    }


class EmbedEditModal(discord.ui.Modal):
    def __init__(
        self,
        guild_id: int,
        name: str,
        data: dict[str, Any],
        lang: GuildLang,
        *,
        is_new: bool = False,
    ):
        title_key = "emb.modal.title_create" if is_new else "emb.modal.title"
        super().__init__(title=tr(lang, title_key))
        self.guild_id = guild_id
        self.name = name
        self.lang = lang
        self.is_new = is_new
        self.title_input = discord.ui.TextInput(
            label=tr(lang, "emb.modal.title_label"),
            default=(data.get("title") or "")[:256],
            max_length=256,
            required=False,
        )
        self.desc_input = discord.ui.TextInput(
            label=tr(lang, "emb.modal.desc_label"),
            style=discord.TextStyle.paragraph,
            default=(data.get("description") or "")[:4000],
            max_length=4000,
            required=False,
        )
        self.color_input = discord.ui.TextInput(
            label=tr(lang, "emb.modal.color_label"),
            placeholder=tr(lang, "emb.modal.color_placeholder"),
            default=hex(int(data.get("color") or BRAND_PINK)).replace("0x", "#"),
            max_length=16,
            required=False,
        )
        self.footer_input = discord.ui.TextInput(
            label=tr(lang, "emb.modal.footer_label"),
            default=(data.get("footer") or "")[:256],
            max_length=256,
            required=False,
        )
        self.add_item(self.title_input)
        self.add_item(self.desc_input)
        self.add_item(self.color_input)
        self.add_item(self.footer_input)

    async def on_submit(self, interaction: discord.Interaction):
        bucket = _guild_bucket(self.guild_id)
        bucket[self.name] = {
            "title": self.title_input.value or "",
            "description": self.desc_input.value or "",
            "color": _parse_color(self.color_input.value or ""),
            "footer": self.footer_input.value or "",
            "thumbnail": bucket.get(self.name, {}).get("thumbnail", ""),
            "image": bucket.get(self.name, {}).get("image", ""),
            "fields": bucket.get(self.name, {}).get("fields", []),
        }
        _save()
        msg_key = "emb.saved_new" if self.is_new else "emb.updated"
        msg = tr(self.lang, msg_key, name=self.name)
        await interaction.response.send_message(
            embed=discord.Embed(description=msg, color=BRAND_PINK),
            ephemeral=True,
        )


class EmbedBuilderCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedBuilderCog(bot))

    @bot.hybrid_group(
        name="embed",
        aliases=["emb"],
        invoke_without_command=True,
        dm_permission=False,
        **hybrid_desc_kwargs("slash.cmd.embed"),
    )
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def cmd_embed(ctx: commands.Context):
        lang = _ctx_lang(ctx)
        await ctx.send(
            embed=discord.Embed(
                title=tr(lang, "emb.help.title"),
                description=tr(lang, "emb.help.body"),
                color=BRAND_PINK,
            )
        )

    def _perm_check(ctx: commands.Context) -> bool:
        return bool(
            ctx.guild
            and ctx.author.guild_permissions.manage_messages
        )

    @cmd_embed.command(name="create", aliases=["new", "add"], **slash_desc_kwargs("slash.cmd.embed_create"))
    @app_commands.describe(name=slash_param("slash.param.embed_name"))
    @commands.guild_only()
    async def emb_create(ctx: commands.Context, name: str):
        lang = _ctx_lang(ctx)
        if not _perm_check(ctx):
            await hybrid_ctx_reply(ctx, tr(lang, "emb.err.perms"), error=True)
            return
        name = _normalize_embed_name(name)
        if not name or len(name) > 32:
            await hybrid_ctx_reply(ctx, tr(lang, "emb.err.bad_name"), error=True)
            return
        bucket = _guild_bucket(ctx.guild.id)
        if name in bucket:
            await hybrid_ctx_reply(ctx, tr(lang, "emb.err.exists", name=name), error=True)
            return
        if ctx.interaction:
            modal = EmbedEditModal(
                ctx.guild.id, name, _empty_embed_data(), lang, is_new=True,
            )
            await ctx.interaction.response.send_modal(modal)
            return
        bucket[name] = {
            **_empty_embed_data(),
            "description": tr(lang, "emb.default.desc", name=name),
        }
        _save()
        await hybrid_ctx_reply(ctx, tr(lang, "emb.created", name=name))

    @cmd_embed.command(name="edit", aliases=["e"], **slash_desc_kwargs("slash.cmd.embed_edit"))
    @app_commands.describe(name=slash_param("slash.param.embed_name"))
    @commands.guild_only()
    async def emb_edit(ctx: commands.Context, name: str):
        lang = _ctx_lang(ctx)
        if not _perm_check(ctx):
            await hybrid_ctx_reply(ctx, tr(lang, "emb.err.perms"), error=True)
            return
        name = _normalize_embed_name(name)
        data = _guild_bucket(ctx.guild.id).get(name)
        if not data:
            await hybrid_ctx_reply(ctx, tr(lang, "emb.err.not_found", name=name), error=True)
            return
        modal = EmbedEditModal(ctx.guild.id, name, data, lang, is_new=False)
        if ctx.interaction:
            await ctx.interaction.response.send_modal(modal)
        else:
            await hybrid_ctx_reply(ctx, tr(lang, "emb.use_slash_edit"))

    @cmd_embed.command(name="preview", aliases=["pv", "show"], **slash_desc_kwargs("slash.cmd.embed_preview"))
    @app_commands.describe(name=slash_param("slash.param.embed_name"))
    @commands.guild_only()
    async def emb_preview(ctx: commands.Context, name: str):
        lang = _ctx_lang(ctx)
        if not _perm_check(ctx):
            await hybrid_ctx_reply(ctx, tr(lang, "emb.err.perms"), error=True)
            return
        name = _normalize_embed_name(name)
        data = _guild_bucket(ctx.guild.id).get(name)
        if not data:
            await hybrid_ctx_reply(ctx, tr(lang, "emb.err.not_found", name=name), error=True)
            return
        if not _embed_is_postable(data):
            await hybrid_ctx_reply(ctx, tr(lang, "emb.err.empty_embed", name=name), error=True)
            return
        await hybrid_defer(ctx)
        await ctx.send(embed=_build_from_data(data))

    @cmd_embed.command(name="send", aliases=["post", "s"], **slash_desc_kwargs("slash.cmd.embed_send"))
    @app_commands.describe(
        name=slash_param("slash.param.embed_name"),
        channel=slash_param("slash.param.embed_channel"),
    )
    @commands.guild_only()
    async def emb_send(ctx: commands.Context, name: str, channel: Optional[discord.TextChannel] = None):
        lang = _ctx_lang(ctx)
        if not _perm_check(ctx):
            await hybrid_ctx_reply(ctx, tr(lang, "emb.err.perms"), error=True)
            return
        name = _normalize_embed_name(name)
        if not name:
            await hybrid_ctx_reply(ctx, tr(lang, "emb.err.bad_name"), error=True)
            return
        data = _guild_bucket(ctx.guild.id).get(name)
        if not data:
            await hybrid_ctx_reply(ctx, tr(lang, "emb.err.not_found", name=name), error=True)
            return
        if not _embed_is_postable(data):
            await hybrid_ctx_reply(ctx, tr(lang, "emb.err.empty_embed", name=name), error=True)
            return
        target = channel or ctx.channel
        if not isinstance(target, discord.TextChannel):
            await hybrid_ctx_reply(ctx, tr(lang, "emb.err.bad_channel"), error=True)
            return
        perms = _channel_send_perms(target)
        if not perms or not perms.send_messages or not perms.embed_links:
            await hybrid_ctx_reply(ctx, tr(lang, "emb.err.no_send_perms", channel=target.mention), error=True)
            return
        await hybrid_defer(ctx)
        try:
            await target.send(embed=_build_from_data(data))
        except discord.HTTPException as exc:
            log.warning(
                "emb send failed guild=%s template=%s channel=%s: %s",
                ctx.guild.id, name, target.id, exc,
            )
            await hybrid_ctx_reply(ctx, tr(lang, "emb.err.send_failed", name=name), error=True)
            return
        await hybrid_ctx_reply(ctx, tr(lang, "emb.sent", name=name, channel=target.mention), delete_after=12)

    @cmd_embed.command(name="list", aliases=["ls"], **slash_desc_kwargs("slash.cmd.embed_list"))
    @commands.guild_only()
    async def emb_list(ctx: commands.Context):
        lang = _ctx_lang(ctx)
        if not _perm_check(ctx):
            await hybrid_ctx_reply(ctx, tr(lang, "emb.err.perms"), error=True)
            return
        names = sorted(_guild_bucket(ctx.guild.id).keys())
        if not names:
            await hybrid_ctx_reply(ctx, tr(lang, "emb.list.empty"))
            return
        await ctx.send(
            embed=discord.Embed(
                title=tr(lang, "emb.list.title"),
                description="\n".join(f"• **`{n}`**" for n in names)[:4000],
                color=BRAND_PINK,
            )
        )

    @cmd_embed.command(name="delete", aliases=["del", "rm"], **slash_desc_kwargs("slash.cmd.embed_delete"))
    @app_commands.describe(name=slash_param("slash.param.embed_name"))
    @commands.guild_only()
    async def emb_delete(ctx: commands.Context, name: str):
        lang = _ctx_lang(ctx)
        if not _perm_check(ctx):
            await hybrid_ctx_reply(ctx, tr(lang, "emb.err.perms"), error=True)
            return
        name = _normalize_embed_name(name)
        bucket = _guild_bucket(ctx.guild.id)
        if name not in bucket:
            await hybrid_ctx_reply(ctx, tr(lang, "emb.err.not_found", name=name), error=True)
            return
        del bucket[name]
        _save()
        await hybrid_ctx_reply(ctx, tr(lang, "emb.removed", name=name), delete_after=8)
