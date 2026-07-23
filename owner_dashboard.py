"""Owner-only usage and cost dashboard for /stats and t!stats."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import discord

FUSO_BR = timezone(timedelta(hours=-3))
TIFFANY_PINK = 0xFF69B4

_BASE = os.path.dirname(os.path.abspath(__file__))


def bot_owner_id() -> int:
    return int(os.getenv("BOT_OWNER_ID", "842799130630815754"))


def is_bot_owner(user_id: int) -> bool:
    return int(user_id) == bot_owner_id()


def _read_json(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _offers_counts() -> tuple[int, int]:
    """Return (posted_last_24h, posted_total)."""
    data = _read_json(os.path.join(_BASE, "offers_history.json"))
    deals = data.get("deals") or {}
    if not isinstance(deals, dict):
        return 0, 0
    cutoff = time.time() - 86400
    last_day = sum(1 for v in deals.values() if isinstance(v, dict) and v.get("ts", 0) >= cutoff)
    return last_day, len(deals)


def _estimate_cost_usd(*, chat_calls: int, news_ia_calls: int) -> float:
    """Rough OpenRouter/Gemini Flash Lite estimate (configurable via env)."""
    chat_rate = float(os.getenv("COST_EST_CHAT_USD", "0.00008"))
    news_rate = float(os.getenv("COST_EST_NEWS_IA_USD", "0.00015"))
    return (chat_calls * chat_rate) + (news_ia_calls * news_rate)


def build_owner_stats_embed(client: discord.Client) -> discord.Embed:
    voice = _read_json(os.path.join(_BASE, "voice_stats.json"))
    news = _read_json(os.path.join(_BASE, "notices_metrics.json"))
    offers_day, offers_total = _offers_counts()

    songs = int(voice.get("songs_played") or 0)
    chat = int(voice.get("questions_answered") or 0)
    cmds = int(voice.get("commands_used") or 0)
    rewind_users = len(voice.get("user_songs") or {})

    posts_hoje = int(news.get("posts_hoje") or 0)
    ia_hoje = int(news.get("ia_calls_hoje") or 0)
    ia_ok_hoje = int(news.get("ia_aprovadas_hoje") or 0)
    ia_no_hoje = int(news.get("ia_rejeitadas_hoje") or 0)
    posts_total = int(news.get("posts_total") or 0)
    ia_total = int(news.get("ia_calls_total") or 0)

    cost_hoje = _estimate_cost_usd(chat_calls=0, news_ia_calls=ia_hoje)
    cost_total = _estimate_cost_usd(chat_calls=chat, news_ia_calls=ia_total)

    guilds = len(client.guilds) if client else 0
    members = sum(g.member_count or 0 for g in client.guilds) if client else 0
    agora = datetime.now(FUSO_BR)

    em = discord.Embed(
        title="📊 Tiffany · Painel do dono",
        description="Uso geral e estimativa de gasto com IA (somente você vê isto).",
        color=TIFFANY_PINK,
        timestamp=agora,
    )

    em.add_field(
        name="🎵 Música & comandos (total)",
        value=(
            f"Músicas tocadas: **{songs:,}**\n"
            f"Perguntas IA (chat): **{chat:,}**\n"
            f"Comandos usados: **{cmds:,}**\n"
            f"Usuários no Rewind: **{rewind_users:,}**"
        ),
        inline=True,
    )
    em.add_field(
        name="📰 Notícias · hoje",
        value=(
            f"Posts: **{posts_hoje}**\n"
            f"Chamadas IA: **{ia_hoje}** (✅ {ia_ok_hoje} · ❌ {ia_no_hoje})\n"
            f"Posts acumulados: **{posts_total:,}**"
        ),
        inline=True,
    )
    em.add_field(
        name="🛒 Ofertas",
        value=f"Últimas 24h: **{offers_day}** · Total rastreado: **{offers_total:,}**",
        inline=True,
    )
    em.add_field(
        name="🌐 Alcance",
        value=f"Servidores: **{guilds:,}** · Membros (aprox.): **{members:,}**",
        inline=True,
    )
    em.add_field(
        name="💰 Estimativa IA (USD)",
        value=(
            f"Hoje (notícias IA): **~${cost_hoje:.4f}**\n"
            f"Acumulado (chat + notícias IA): **~${cost_total:.4f}**"
        ),
        inline=True,
    )
    em.add_field(
        name="📡 Bot",
        value=(
            f"Ping: **{max(0, round((client.latency or 0) * 1000))} ms**\n"
            f"Servidores conectados: **{guilds}**"
        ),
        inline=True,
    )
    em.set_footer(text="Valores de IA são estimativas · ajuste COST_EST_* no .env se quiser")
    return em
