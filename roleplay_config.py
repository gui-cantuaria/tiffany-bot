"""Per-user roleplay personality profiles for /roleplay and t!rp."""

from __future__ import annotations

import json
import logging
import os
import random
from typing import Any, Optional

import discord
from discord import ui

from locale_utils import GuildLang, roleplay_system_prompt, tr

log = logging.getLogger("tiffany-bot")

_PROFILES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "roleplay_profiles.json")
_cache: dict[str, dict[str, Any]] = {}
_loaded = False

PRESETS: tuple[dict[str, str], ...] = (
    {"tone": "playful", "humor": "high", "energy": "bubbly", "note": "loves memes and games"},
    {"tone": "chill", "humor": "medium", "energy": "calm", "note": "laid-back friend vibes"},
    {"tone": "witty", "humor": "high", "energy": "sharp", "note": "dry humor, quick comebacks"},
    {"tone": "warm", "humor": "low", "energy": "gentle", "note": "supportive and kind"},
    {"tone": "nerdy", "humor": "medium", "energy": "enthusiastic", "note": "tech and gaming geek"},
)


def _load() -> None:
    global _loaded, _cache
    if _loaded:
        return
    if os.path.exists(_PROFILES_FILE):
        try:
            with open(_PROFILES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _cache = data if isinstance(data, dict) else {}
        except Exception as e:
            log.error("Failed to load roleplay_profiles.json: %s", e)
            _cache = {}
    _loaded = True


def _save() -> None:
    try:
        with open(_PROFILES_FILE, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error("Failed to save roleplay_profiles.json: %s", e)


def get_profile(user_id: int) -> Optional[dict[str, Any]]:
    _load()
    raw = _cache.get(str(user_id))
    return dict(raw) if isinstance(raw, dict) else None


def set_profile(user_id: int, profile: dict[str, Any]) -> None:
    _load()
    _cache[str(user_id)] = profile
    _save()


def random_profile() -> dict[str, Any]:
    p = dict(random.choice(PRESETS))
    p["source"] = "random"
    return p


def build_roleplay_prompt(lang: GuildLang, profile: Optional[dict[str, Any]] = None) -> str:
    base = roleplay_system_prompt(lang)
    if not profile:
        return base
    tone = profile.get("tone") or "casual"
    humor = profile.get("humor") or "medium"
    energy = profile.get("energy") or "balanced"
    note = (profile.get("note") or "").strip()[:200]
    extra = (
        f"\nUSER PERSONALITY PRESET:\n"
        f"- Tone: {tone}\n"
        f"- Humor level: {humor}\n"
        f"- Energy: {energy}\n"
    )
    if note:
        extra += f"- User note: {note}\n"
    extra += "- Match the user's message language (never switch unless they do).\n"
    return base + extra


class RoleplayConfigModal(ui.Modal, title="Roleplay personality"):
    tone = ui.TextInput(
        label="Tone (playful, chill, witty…)",
        placeholder="playful",
        max_length=40,
        required=False,
    )
    humor = ui.TextInput(
        label="Humor (low, medium, high)",
        placeholder="medium",
        max_length=20,
        required=False,
    )
    energy = ui.TextInput(
        label="Energy (calm, bubbly, sharp…)",
        placeholder="bubbly",
        max_length=40,
        required=False,
    )
    note = ui.TextInput(
        label="Extra (optional)",
        style=discord.TextStyle.paragraph,
        placeholder="e.g. talk like a gamer friend who loves RPGs",
        max_length=200,
        required=False,
    )

    def __init__(self, user_id: int, lang: GuildLang):
        super().__init__()
        self.user_id = user_id
        self.lang = lang

    async def on_submit(self, interaction: discord.Interaction) -> None:
        profile = {
            "tone": (self.tone.value or "casual").strip()[:40],
            "humor": (self.humor.value or "medium").strip()[:20],
            "energy": (self.energy.value or "balanced").strip()[:40],
            "note": (self.note.value or "").strip()[:200],
            "source": "custom",
        }
        set_profile(self.user_id, profile)
        await interaction.response.send_message(tr(self.lang, "roleplay.profile.saved"), ephemeral=True)


class RoleplaySetupView(ui.View):
    def __init__(self, user_id: int, lang: GuildLang, *, pink: int):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.lang = lang
        self.pink = pink

    @ui.button(label="Configure", style=discord.ButtonStyle.primary, emoji="⚙️")
    async def configure(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(tr(self.lang, "roleplay.profile.not_you"), ephemeral=True)
            return
        await interaction.response.send_modal(RoleplayConfigModal(self.user_id, self.lang))

    @ui.button(label="Skip — random", style=discord.ButtonStyle.secondary, emoji="🎲")
    async def skip_random(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(tr(self.lang, "roleplay.profile.not_you"), ephemeral=True)
            return
        set_profile(self.user_id, random_profile())
        await interaction.response.send_message(tr(self.lang, "roleplay.profile.random"), ephemeral=True)

    @ui.button(label="Reset profile", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def reset(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(tr(self.lang, "roleplay.profile.not_you"), ephemeral=True)
            return
        _load()
        _cache.pop(str(self.user_id), None)
        _save()
        await interaction.response.send_message(tr(self.lang, "roleplay.profile.reset"), ephemeral=True)


def setup_embed(lang: GuildLang, *, pink: int) -> discord.Embed:
    return discord.Embed(
        title=tr(lang, "roleplay.setup.title"),
        description=tr(lang, "roleplay.setup.body"),
        color=pink,
    )
