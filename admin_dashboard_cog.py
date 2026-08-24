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
import tiffany_voice
log = logging.getLogger("tiffany-bot")

class AdminDashboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="metrics", hidden=True, description="Creator business and telemetry metrics (Admin Only)")
    async def metrics_cmd(self, ctx: commands.Context):
        """Displays business and telemetry metrics (Owner Only)."""
        is_owner = (
            ctx.author.id == 842799130630815754
            or owner_dashboard.is_bot_owner(ctx.author.id)
            or await self.bot.is_owner(ctx.author)
        )
        if not is_owner:
            return await tiffany_voice.hybrid_ctx_reply(ctx, "Comando exclusivo do dono da Tiffany.", ephemeral=True)
            
        # Get base JSON metrics
        embed = owner_dashboard.build_owner_stats_embed(self.bot)
        
        # Get DB Telemetry
        pool = postgres.pool()
        if pool:
            try:
                async with pool.acquire() as conn:
                    today = discord.utils.utcnow().date()
                    total_quotas = await conn.fetchval(
                        "SELECT SUM(quota_used) FROM ai_usage_daily WHERE day = $1", today
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

    @commands.hybrid_command(name="grant_credits", hidden=True, description="Grant AI quota credits to a user (Admin Only)")
    async def grant_credits_cmd(
        self, 
        ctx: commands.Context, 
        target_user: discord.User, 
        credits: int, 
        reason: str = "Admin grant"
    ):
        """Securely grants AI quota credits to a specified user (Admin Only)."""
        is_owner = (
            ctx.author.id == 842799130630815754
            or owner_dashboard.is_bot_owner(ctx.author.id)
            or await self.bot.is_owner(ctx.author)
        )
        if not is_owner:
            return await tiffany_voice.hybrid_ctx_reply(ctx, "Comando exclusivo do dono da Tiffany.", ephemeral=True)

        if credits <= 0 or credits > 100000:
            return await tiffany_voice.hybrid_ctx_reply(ctx, "⚠️ A quantidade de créditos deve ser entre 1 e 100.000.", ephemeral=True)

        from infra.services.ai_quota import AIQuotaService
        try:
            res = await AIQuotaService.grant_credits(
                user_id=target_user.id,
                credits=credits,
                reason=reason,
                granted_by=ctx.author.id
            )
            embed = discord.Embed(
                title="💳 Créditos de IA Concedidos",
                description=f"Foram adicionados **{credits:,}** créditos de IA para {target_user.mention}.",
                color=TIFFANY_PINK,
            )
            embed.add_field(name="Usuário", value=f"{target_user} (`{target_user.id}`)", inline=True)
            embed.add_field(name="Motivo", value=reason, inline=True)
            embed.add_field(name="Novo Saldo Restante", value=f"**{res['new_remaining']:,}** cotas", inline=False)
            embed.set_footer(text="Transação registrada no Ledger Audit de Segurança")
            
            ephem = getattr(ctx.interaction, "response", None) is not None
            await ctx.send(embed=embed, ephemeral=ephem)
        except Exception as e:
            log.exception("Error in grant_credits_cmd: %s", e)
            await tiffany_voice.hybrid_ctx_reply(ctx, f"❌ Erro ao conceder créditos: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminDashboardCog(bot))

