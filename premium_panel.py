"""
Tiffany Bot — Premium Configuration Panel
=========================================
Advanced UI (Buttons, Selects, Modals) for Guild Owners to configure
premium features (News, Offers, AI Guardrails) natively in Discord.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import discord
from discord.ui import Button, Modal, Select, TextInput, View

from brand_colors import TIFFANY_PINK, TIFFANY_RED
from infra import postgres

log = logging.getLogger("tiffany-bot")

# ---------------------------------------------------------------------------
# Database Helpers
# ---------------------------------------------------------------------------
async def get_premium_config(guild_id: int) -> dict[str, Any]:
    pool = postgres.pool()
    if not pool:
        return {}
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT config FROM guild_premium_config WHERE guild_id = $1", guild_id
        )
        if row and row["config"]:
            return json.loads(row["config"]) if isinstance(row["config"], str) else dict(row["config"])
        return {}


async def update_premium_config(guild_id: int, section: str, updates: dict[str, Any]) -> None:
    pool = postgres.pool()
    if not pool:
        return
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT config FROM guild_premium_config WHERE guild_id = $1", guild_id
        )
        cfg = json.loads(existing) if isinstance(existing, str) else dict(existing or {})
        
        if section not in cfg:
            cfg[section] = {}
        for k, v in updates.items():
            cfg[section][k] = v

        await conn.execute(
            """
            UPDATE guild_premium_config 
            SET config = $1::jsonb, updated_at = now() 
            WHERE guild_id = $2
            """,
            json.dumps(cfg),
            guild_id,
        )


# ---------------------------------------------------------------------------
# Offers Configuration UI
# ---------------------------------------------------------------------------
class OffersLayoutModal(Modal, title="Configure Offers Layout"):
    def __init__(self, current_cfg: dict, view: "PremiumDashboardView"):
        super().__init__()
        self.view_ref = view
        
        layout = current_cfg.get("embed_layout", {})
        self.btn_pos = TextInput(
            label="Button Position (top/bottom)",
            default=layout.get("button_position", "bottom"),
            max_length=6,
        )
        self.max_chars = TextInput(
            label="Title Max Chars (ex: 256)",
            default=str(layout.get("title_max_chars", 256)),
            max_length=4,
        )
        self.min_disc = TextInput(
            label="Min Discount % (ex: 15)",
            default=str(current_cfg.get("min_discount_pct", 0)),
            max_length=3,
        )
        
        self.add_item(self.btn_pos)
        self.add_item(self.max_chars)
        self.add_item(self.min_disc)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            updates = {
                "min_discount_pct": int(self.min_disc.value) if self.min_disc.value.isdigit() else 0,
                "embed_layout": {
                    "button_position": self.btn_pos.value.lower() if self.btn_pos.value.lower() in ("top", "bottom") else "bottom",
                    "title_max_chars": int(self.max_chars.value) if self.max_chars.value.isdigit() else 256,
                    "title_max_words": 0,
                    "show_affiliate": True,
                }
            }
            await update_premium_config(interaction.guild_id, "offers", updates)
            await interaction.response.send_message("✅ Offers layout updated!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


class OffersNSFWSelect(Select):
    def __init__(self, current_nsfw: bool):
        options = [
            discord.SelectOption(label="NSFW Blocked (Safe)", value="false", default=not current_nsfw, emoji="🛡️"),
            discord.SelectOption(label="NSFW Allowed (18+)", value="true", default=current_nsfw, emoji="🔞"),
        ]
        super().__init__(placeholder="NSFW Offers Toggle", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        is_nsfw = self.values[0] == "true"
        await update_premium_config(interaction.guild_id, "offers", {"nsfw_enabled": is_nsfw})
        await interaction.response.send_message(f"✅ Offers NSFW set to: {is_nsfw}", ephemeral=True)


class OffersConfigView(View):
    def __init__(self, guild_id: int, current_cfg: dict, parent_view: "PremiumDashboardView"):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.current_cfg = current_cfg
        self.parent_view = parent_view
        self.add_item(OffersNSFWSelect(current_cfg.get("nsfw_enabled", False)))

    @discord.ui.button(label="Edit Layout & Discount", style=discord.ButtonStyle.primary, emoji="🛠️", row=1)
    async def edit_layout(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(OffersLayoutModal(self.current_cfg, self.parent_view))

    @discord.ui.button(label="Back to Dashboard", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: Button):
        await self.parent_view.refresh(interaction)


# ---------------------------------------------------------------------------
# News Configuration UI
# ---------------------------------------------------------------------------
class NewsRSSModal(Modal, title="Configure Custom RSS Feeds"):
    def __init__(self, current_cfg: dict):
        super().__init__()
        rss_urls = current_cfg.get("custom_rss_urls", [])
        self.rss_input = TextInput(
            label="Custom RSS URLs (One per line)",
            style=discord.TextStyle.paragraph,
            default="\n".join(rss_urls) if rss_urls else "",
            placeholder="https://example.com/feed.xml\nhttps://news.com/rss",
            required=False,
        )
        self.add_item(self.rss_input)

    async def on_submit(self, interaction: discord.Interaction):
        urls = [url.strip() for url in self.rss_input.value.split("\n") if url.strip().startswith("http")]
        await update_premium_config(interaction.guild_id, "news", {"custom_rss_urls": urls[:10]}) # max 10
        await interaction.response.send_message(f"✅ Saved {len(urls)} custom RSS feeds!", ephemeral=True)


class NewsTranslateSelect(Select):
    def __init__(self, auto_translate: bool):
        options = [
            discord.SelectOption(label="Keep Original Language", value="false", default=not auto_translate, emoji="🌐"),
            discord.SelectOption(label="Auto-Translate to Guild Lang", value="true", default=auto_translate, emoji="🗣️"),
        ]
        super().__init__(placeholder="Auto-Translate News?", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        auto = self.values[0] == "true"
        await update_premium_config(interaction.guild_id, "news", {"auto_translate": auto})
        await interaction.response.send_message(f"✅ Auto-translate set to: {auto}", ephemeral=True)


class NewsConfigView(View):
    def __init__(self, guild_id: int, current_cfg: dict, parent_view: "PremiumDashboardView"):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.current_cfg = current_cfg
        self.parent_view = parent_view
        self.add_item(NewsTranslateSelect(current_cfg.get("auto_translate", False)))

    @discord.ui.button(label="Edit Custom RSS", style=discord.ButtonStyle.primary, emoji="📰", row=1)
    async def edit_rss(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(NewsRSSModal(self.current_cfg))

    @discord.ui.button(label="Back to Dashboard", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: Button):
        await self.parent_view.refresh(interaction)


# ---------------------------------------------------------------------------
# White-Label Configuration UI
# ---------------------------------------------------------------------------
class WhiteLabelModal(Modal, title="Configure White-Labeling"):
    def __init__(self, current_cfg: dict):
        super().__init__()
        
        self.embed_color = TextInput(
            label="Embed Hex Color (e.g. #FF0000)",
            default=current_cfg.get("embed_color", ""),
            placeholder="#FFFFFF",
            required=False,
            max_length=7,
        )
        self.footer_text = TextInput(
            label="Custom Footer Text",
            default=current_cfg.get("footer_text", ""),
            placeholder="Powered by MyServer",
            required=False,
            max_length=100,
        )
        
        self.add_item(self.embed_color)
        self.add_item(self.footer_text)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            updates = {
                "embed_color": self.embed_color.value.strip(),
                "footer_text": self.footer_text.value.strip(),
            }
            await update_premium_config(interaction.guild_id, "white_label", updates)
            await interaction.response.send_message("✅ White-label settings updated!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


class WhiteLabelConfigView(View):
    def __init__(self, guild_id: int, current_cfg: dict, parent_view: "PremiumDashboardView"):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.current_cfg = current_cfg
        self.parent_view = parent_view

    @discord.ui.button(label="Edit Branding", style=discord.ButtonStyle.primary, emoji="🎨", row=0)
    async def edit_branding(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(WhiteLabelModal(self.current_cfg))

    @discord.ui.button(label="Back to Dashboard", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: Button):
        await self.parent_view.refresh(interaction)


# ---------------------------------------------------------------------------
# Main Premium Dashboard
# ---------------------------------------------------------------------------
class PremiumDashboardView(View):
    def __init__(self, guild_id: int, package: str, author_id: int = None):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.package = package
        self.author_id = author_id
        self.add_item(Button(label="Manage Subscription (Stripe)", style=discord.ButtonStyle.link, url="https://billing.stripe.com/p/session/test", row=1))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id is not None and interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Este painel não foi aberto por você.", ephemeral=True)
            return False
            
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Apenas administradores podem configurar o Premium.", ephemeral=True)
            return False
            
        return True

    async def refresh(self, interaction: discord.Interaction):
        # Re-render main embed
        embed = discord.Embed(
            title="💎 Premium Dashboard",
            description=f"Your current active package: **{self.package.upper()}**\nUse the buttons below to configure your advanced features.",
            color=TIFFANY_PINK
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Configure Offers", style=discord.ButtonStyle.primary, emoji="🛒", row=0)
    async def btn_offers(self, interaction: discord.Interaction, button: Button):
        if self.package not in ("offers", "ultimate"):
            return await interaction.response.send_message("❌ This requires the Offers or Ultimate package.", ephemeral=True)
        
        cfg = await get_premium_config(self.guild_id)
        offers_cfg = cfg.get("offers", {})
        view = OffersConfigView(self.guild_id, offers_cfg, self)
        
        embed = discord.Embed(title="🛒 Offers Configuration", color=TIFFANY_PINK)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Configure News", style=discord.ButtonStyle.primary, emoji="📰", row=0)
    async def btn_news(self, interaction: discord.Interaction, button: Button):
        if self.package not in ("news", "ultimate"):
            return await interaction.response.send_message("❌ This requires the News or Ultimate package.", ephemeral=True)
        
        cfg = await get_premium_config(self.guild_id)
        news_cfg = cfg.get("news", {})
        view = NewsConfigView(self.guild_id, news_cfg, self)
        
        embed = discord.Embed(title="📰 News Configuration", color=TIFFANY_PINK)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Configure White-Label", style=discord.ButtonStyle.success, emoji="🎨", row=0)
    async def btn_whitelabel(self, interaction: discord.Interaction, button: Button):
        if self.package != "ultimate":
            return await interaction.response.send_message("❌ White-labeling is exclusive to the Ultimate package.", ephemeral=True)
        
        cfg = await get_premium_config(self.guild_id)
        wl_cfg = cfg.get("white_label", {})
        view = WhiteLabelConfigView(self.guild_id, wl_cfg, self)
        
        embed = discord.Embed(title="🎨 White-Label Configuration", color=TIFFANY_PINK)
        await interaction.response.edit_message(embed=embed, view=view)
