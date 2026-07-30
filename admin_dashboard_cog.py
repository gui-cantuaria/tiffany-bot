"""
Tiffany Bot — Admin Dashboard Cog
=================================
Hidden owner-only command to view Telemetry and Business metrics.
"""

from __future__ import annotations

import logging
import discord
from discord.ext import commands

from infra import postgres
import owner_dashboard
from brand_colors import TIFFANY_PINK

log = logging.getLogger("tiffany-bot")

class AdminDashboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="metrics", hidden=True, description="Painel exclusivo do criador (Admin)")
    async def metrics_cmd(self, ctx: commands.Context):
        """Displays business and telemetry metrics (Owner Only)."""
        if ctx.author.id != 842799130630815754:
            return await ctx.send("Comando exclusivo do dono da Tiffany.", ephemeral=True)
            
        # Get base JSON metrics
        embed = owner_dashboard.build_owner_stats_embed(self.bot)
        
        # Get DB Telemetry
        pool = postgres.pool()
        if pool:
            try:
                async with pool.acquire() as conn:
                    today = discord.utils.utcnow().strftime("%Y-%m-%d")
                    total_quotas = await conn.fetchval(
                        "SELECT SUM(tokens_used) FROM ai_usage_daily WHERE date = $1", today
                    ) or 0
                    
                    ai_calls = await conn.fetchval(
                        "SELECT COUNT(*) FROM telemetry_ai_usage WHERE created_at > now() - interval '24 hours'"
                    ) or 0
                    
                    errors = await conn.fetchval(
                        "SELECT COUNT(*) FROM telemetry_ai_usage WHERE success = false AND created_at > now() - interval '24 hours'"
                    ) or 0
                    
                embed.add_field(name="💳 Banco de Dados (Postgres)", value=f"Quotas usadas hoje: **{total_quotas:,.0f}**\nChamadas IA 24h: **{ai_calls:,}**\nFalhas IA 24h: **{errors:,}**", inline=False)
            except Exception as e:
                log.warning("AdminDashboard DB error: %s", e)
                embed.add_field(name="💳 Banco de Dados", value="Falha ao carregar telemetria.", inline=False)
        else:
            embed.add_field(name="💳 Banco de Dados", value="Desconectado.", inline=False)
            
        # Send ephemeral if slash, normal if prefix
        ephem = getattr(ctx.interaction, "response", None) is not None
        await ctx.send(embed=embed, ephemeral=ephem)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminDashboardCog(bot))
