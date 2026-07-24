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

log = logging.getLogger("tiffany-bot")

BRAND_PINK = 0xFF69B4
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


class EmbedEditModal(discord.ui.Modal, title="Editar embed"):
    def __init__(self, guild_id: int, name: str, data: dict[str, Any]):
        super().__init__()
        self.guild_id = guild_id
        self.name = name
        self.title_input = discord.ui.TextInput(
            label="Título",
            default=(data.get("title") or "")[:256],
            max_length=256,
            required=False,
        )
        self.desc_input = discord.ui.TextInput(
            label="Descrição",
            style=discord.TextStyle.paragraph,
            default=(data.get("description") or "")[:4000],
            max_length=4000,
            required=False,
        )
        self.color_input = discord.ui.TextInput(
            label="Cor (hex)",
            default=hex(int(data.get("color") or BRAND_PINK)).replace("0x", "#"),
            max_length=16,
            required=False,
        )
        self.footer_input = discord.ui.TextInput(
            label="Footer",
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
        await interaction.response.send_message(
            f"Embed **`{self.name}`** atualizado! Use `t!emb send {self.name}`.",
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
        description="Create and send custom embeds",
        dm_permission=False,
    )
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def cmd_embed(ctx: commands.Context):
        await ctx.send(
            embed=discord.Embed(
                title="📝 Embed Builder",
                description=(
                    "**Comandos:**\n"
                    "`t!emb create <nome>` — cria embed vazio (modal de edição)\n"
                    "`t!emb edit <nome>` — abre modal para editar\n"
                    "`t!emb preview <nome>` — pré-visualiza\n"
                    "`t!emb send <nome> [#canal]` — publica no canal\n"
                    "`t!emb list` — lista embeds salvos\n"
                    "`t!emb delete <nome>` — remove\n\n"
                    "Requer **Gerenciar Mensagens**."
                ),
                color=BRAND_PINK,
            )
        )

    def _perm_check(ctx: commands.Context) -> bool:
        return bool(
            ctx.guild
            and ctx.author.guild_permissions.manage_messages
        )

    @cmd_embed.command(name="create", aliases=["new", "add"])
    async def emb_create(ctx: commands.Context, name: str):
        if not _perm_check(ctx):
            await ctx.send("Precisa de **Gerenciar Mensagens**.", ephemeral=True)
            return
        name = re.sub(r"[^\w\-]", "", (name or "").strip().lower())
        if not name or len(name) > 32:
            await ctx.send("Nome inválido (use letras, números, `-`, máx 32).")
            return
        bucket = _guild_bucket(ctx.guild.id)
        if name in bucket:
            await ctx.send(f"Já existe **`{name}`**. Use `t!emb edit {name}`.")
            return
        bucket[name] = {
            "title": "Título do embed",
            "description": "Descrição aqui — edite com `t!emb edit " + name + "`",
            "color": BRAND_PINK,
            "footer": "",
            "thumbnail": "",
            "image": "",
            "fields": [],
        }
        _save()
        modal = EmbedEditModal(ctx.guild.id, name, bucket[name])
        if ctx.interaction:
            await ctx.interaction.response.send_modal(modal)
        else:
            await ctx.send(
                embed=discord.Embed(
                    description=(
                        f"Embed **`{name}`** criado! "
                        f"Use **`/embed edit {name}`** (slash abre o modal de edição)."
                    ),
                    color=BRAND_PINK,
                )
            )

    @cmd_embed.command(name="edit", aliases=["e"])
    async def emb_edit(ctx: commands.Context, name: str):
        if not _perm_check(ctx):
            await ctx.send("Precisa de **Gerenciar Mensagens**.", ephemeral=True)
            return
        name = (name or "").strip().lower()
        data = _guild_bucket(ctx.guild.id).get(name)
        if not data:
            await ctx.send(f"Embed **`{name}`** não encontrado.")
            return
        modal = EmbedEditModal(ctx.guild.id, name, data)
        if ctx.interaction:
            await ctx.interaction.response.send_modal(modal)
        else:
            await ctx.send("Use **`/embed edit`** (slash) para abrir o modal no Discord.")

    @cmd_embed.command(name="preview", aliases=["pv", "show"])
    async def emb_preview(ctx: commands.Context, name: str):
        if not _perm_check(ctx):
            await ctx.send("Precisa de **Gerenciar Mensagens**.", ephemeral=True)
            return
        name = (name or "").strip().lower()
        data = _guild_bucket(ctx.guild.id).get(name)
        if not data:
            await ctx.send(f"Embed **`{name}`** não encontrado.")
            return
        await ctx.send(embed=_build_from_data(data))

    @cmd_embed.command(name="send", aliases=["post", "s"])
    async def emb_send(ctx: commands.Context, name: str, channel: Optional[discord.TextChannel] = None):
        if not _perm_check(ctx):
            await ctx.send("Precisa de **Gerenciar Mensagens**.", ephemeral=True)
            return
        name = (name or "").strip().lower()
        data = _guild_bucket(ctx.guild.id).get(name)
        if not data:
            await ctx.send(f"Embed **`{name}`** não encontrado.")
            return
        target = channel or ctx.channel
        if not isinstance(target, discord.TextChannel):
            await ctx.send("Canal inválido.")
            return
        await target.send(embed=_build_from_data(data))
        await ctx.send(f"Embed **`{name}`** enviado em {target.mention}.", delete_after=8)

    @cmd_embed.command(name="list", aliases=["ls"])
    async def emb_list(ctx: commands.Context):
        if not _perm_check(ctx):
            await ctx.send("Precisa de **Gerenciar Mensagens**.", ephemeral=True)
            return
        names = sorted(_guild_bucket(ctx.guild.id).keys())
        if not names:
            await ctx.send("Nenhum embed salvo. Crie com `t!emb create regras`.")
            return
        await ctx.send(
            embed=discord.Embed(
                title="📝 Embeds salvos",
                description="\n".join(f"• **`{n}`**" for n in names)[:4000],
                color=BRAND_PINK,
            )
        )

    @cmd_embed.command(name="delete", aliases=["del", "rm"])
    async def emb_delete(ctx: commands.Context, name: str):
        if not _perm_check(ctx):
            await ctx.send("Precisa de **Gerenciar Mensagens**.", ephemeral=True)
            return
        name = (name or "").strip().lower()
        bucket = _guild_bucket(ctx.guild.id)
        if name not in bucket:
            await ctx.send(f"Embed **`{name}`** não encontrado.")
            return
        del bucket[name]
        _save()
        await ctx.send(f"Embed **`{name}`** removido.", delete_after=8)
