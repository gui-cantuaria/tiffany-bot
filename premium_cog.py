"""
Tiffany Bot — Premium Commands Cog
Handles /premium with Stripe Checkout Sessions (metadata for webhook ledger).
"""

from __future__ import annotations

import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

from brand_colors import TIFFANY_PINK
from infra.premium import has_premium
from premium_panel import PremiumDashboardView

log = logging.getLogger("tiffany-bot")

# Env-driven price IDs — never hardcode live Stripe price IDs in source.
PACKAGE_PRICE_ENV = {
    "offers": "STRIPE_PRICE_OFFERS",
    "news": "STRIPE_PRICE_NEWS",
    "ultimate": "STRIPE_PRICE_ULTIMATE",
}


def _price_id_for_package(package: str) -> str | None:
    env_key = PACKAGE_PRICE_ENV.get(package)
    if not env_key:
        return None
    return os.getenv(env_key, "").strip() or None


class PremiumCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="premium", description="Manage your Tiffany Premium subscription & configure features.")
    async def premium_cmd(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=discord.Embed(description="Premium guild plans require a server.", color=TIFFANY_PINK),
                ephemeral=True,
            )
            return

        guild_has_premium = await has_premium(interaction.guild_id, subject_type="guild")
        if guild_has_premium:
            view = PremiumDashboardView(interaction.guild_id, package="ultimate")
            embed = discord.Embed(
                title="💎 Premium Dashboard",
                description="Your server is upgraded. Configure advanced features below.",
                color=TIFFANY_PINK,
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return

        package = "ultimate"
        price_id = _price_id_for_package(package)
        checkout_url = None

        if price_id and os.getenv("STRIPE_SECRET_KEY", "").strip():
            from infra import stripe_server

            checkout_url = await stripe_server.create_checkout_url(
                price_id=price_id,
                package=package,
                discord_user_id=interaction.user.id,
                discord_guild_id=interaction.guild.id,
            )

        discount_msg = ""
        if interaction.guild:
            from infra.services.subscription import SubscriptionService
            promo_code = await SubscriptionService.check_discount_eligibility(interaction.guild)
            if promo_code and checkout_url:
                checkout_url = f"{checkout_url}&prefilled_promo_code={promo_code}"
                discount_msg = (
                    "\n\n🎉 **MEMBER MILESTONE REWARD!** 🎉\n"
                    f"Promo `{promo_code}` will apply at checkout."
                )

        if not checkout_url:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="💎 Tiffany Premium",
                    description=(
                        "Premium checkout is not configured on this bot instance.\n"
                        "Contact the bot operator or visit **tiffanybot.com/premium**."
                    ),
                    color=TIFFANY_PINK,
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="💎 Upgrade to Tiffany Premium",
            description=(
                "Unlock the full potential of your server.\n"
                "• **100% Affiliate Commissions**\n"
                "• **Higher AI quotas & 24/7 Music**\n"
                "• **Custom RSS & advanced modules**"
                f"{discount_msg}"
            ),
            color=TIFFANY_PINK,
        )
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="Upgrade to Ultimate",
                style=discord.ButtonStyle.link,
                url=checkout_url,
                emoji="💎",
            )
        )
        view.add_item(
            discord.ui.Button(
                label="View All Packages",
                style=discord.ButtonStyle.link,
                url="https://tiffanybot.com/premium",
            )
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PremiumCog(bot))
