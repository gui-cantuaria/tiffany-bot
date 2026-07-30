"""
Tiffany Bot — Premium Commands Cog
==================================
Handles the /premium command, Stripe checkout link generation,
and the dynamic discount system for large servers.
"""

from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from brand_colors import TIFFANY_PINK, TIFFANY_RED
from premium_panel import PremiumDashboardView
from infra.premium import has_premium

log = logging.getLogger("tiffany-bot")

# Stripe Checkout Base URLs (You will replace these with real Payment Links or Checkout API URLs)
CHECKOUT_URLS = {
    "plus": "https://buy.stripe.com/test_plus",
    "offers": "https://buy.stripe.com/test_offers",
    "news": "https://buy.stripe.com/test_news",
    "ultimate": "https://buy.stripe.com/test_ultimate"
}

class PremiumCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="premium", description="Manage your Tiffany Premium subscription & configure features.")
    async def premium_cmd(self, interaction: discord.Interaction):
        # 1. Check if the Guild already has premium
        # We assume 'ultimate' is the top tier. You could check for others.
        guild_has_premium = await has_premium(interaction.guild_id, subject_type="guild")
        
        if guild_has_premium:
            # They have premium! Show them the Dashboard.
            # In a real scenario, we'd fetch the exact package name they bought from the DB.
            # For this example, we assume 'ultimate' to show all buttons.
            view = PremiumDashboardView(interaction.guild_id, package="ultimate")
            embed = discord.Embed(
                title="💎 Premium Dashboard",
                description="Your server is already upgraded! Use the buttons below to configure your advanced features.",
                color=TIFFANY_PINK
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return

        # 2. They don't have premium. Show sales pitch & discount logic.
        discount_msg = ""
        checkout_url = CHECKOUT_URLS["ultimate"]
        
        # 3. Marketing Discount System for Large Servers
        if interaction.guild:
            from infra.services.subscription import SubscriptionService
            promo_code = await SubscriptionService.check_discount_eligibility(interaction.guild)
            if promo_code:
                checkout_url = f"{checkout_url}?prefilled_promo_code={promo_code}"
                discount_msg = (
                    "\n\n🎉 **MEMBER MILESTONE REWARD!** 🎉\n"
                    f"Because **{interaction.guild.name}** is an active, large community, you've unlocked an exclusive **50% OFF** discount for 6 months!\n"
                    f"Your promo code `{promo_code}` has been automatically applied to the link below."
                )

        embed = discord.Embed(
            title="💎 Upgrade to Tiffany Premium",
            description=(
                "Unlock the full potential of your server and monetize like a pro.\n"
                "• **100% Affiliate Commissions** (Keep all the profit!)\n"
                "• **Unlimited AI & 24/7 Music**\n"
                "• **Custom RSS & White-labeling**"
                f"{discount_msg}"
            ),
            color=TIFFANY_PINK
        )
        
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Upgrade to Ultimate", style=discord.ButtonStyle.link, url=checkout_url, emoji="💎"))
        view.add_item(discord.ui.Button(label="View All Packages", style=discord.ButtonStyle.link, url="https://tiffanybot.com/premium"))
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PremiumCog(bot))
