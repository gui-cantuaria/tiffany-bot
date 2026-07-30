"""Per-user roleplay personality profiles and isolated chat history for /roleplay and t!rp."""

from __future__ import annotations

import json
import logging
import os
import random
import time
from typing import Any, Optional

import discord
from discord import ui

from locale_utils import GuildLang, roleplay_system_prompt, tr

log = logging.getLogger("tiffany-bot")

_PROFILES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "roleplay_profiles.json")
_HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "roleplay_history.json")
_cache: dict[str, dict[str, Any]] = {}
_history_cache: dict[str, dict[str, Any]] = {}
_loaded = False
_history_loaded = False

RP_MAX_TURNS = 8
RP_TTL_SEC = 7200
RP_MAX_USERS = 500

INTENSITY_LEVELS = ("low", "medium", "high")
DEFAULT_INTENSITY = "medium"

INTENSITY_PROMPTS: dict[str, str] = {
    "low": (
        "PERSONALITY INTENSITY: LOW — express the preset traits subtly. "
        "Stay close to default Tiffany; tone/humor/energy should only lightly tint replies."
    ),
    "medium": (
        "PERSONALITY INTENSITY: MEDIUM — apply tone, humor, and energy at a balanced level. "
        "Traits should be clearly noticeable without dominating every sentence."
    ),
    "high": (
        "PERSONALITY INTENSITY: HIGH — strongly embody every trait in each reply. "
        "Let tone, humor, and energy drive word choice, jokes, rhythm, reactions, and emoji use. "
        "The personality must feel unmistakable while staying natural."
    ),
}

PRESETS: tuple[dict[str, str], ...] = (
    {
        "tone": "playful",
        "humor": "high",
        "energy": "bubbly",
        "note": "loves memes and games",
        "intensity": "high",
    },
    {
        "tone": "chill",
        "humor": "medium",
        "energy": "calm",
        "note": "laid-back friend vibes",
        "intensity": "low",
    },
    {
        "tone": "witty",
        "humor": "high",
        "energy": "sharp",
        "note": "dry humor, quick comebacks",
        "intensity": "high",
    },
    {
        "tone": "warm",
        "humor": "low",
        "energy": "gentle",
        "note": "supportive and kind",
        "intensity": "medium",
    },
    {
        "tone": "nerdy",
        "humor": "medium",
        "energy": "enthusiastic",
        "note": "tech and gaming geek",
        "intensity": "high",
    },
)


def normalize_intensity(raw: Any) -> str:
    """Map user input to low | medium | high (default medium)."""
    val = str(raw or DEFAULT_INTENSITY).strip().lower()
    aliases = {
        "low": "low",
        "baixo": "low",
        "bajo": "low",
        "faible": "low",
        "niedrig": "low",
        "subtle": "low",
        "medium": "medium",
        "med": "medium",
        "medio": "medium",
        "médio": "medium",
        "moyen": "medium",
        "mittel": "medium",
        "high": "high",
        "alto": "high",
        "alta": "high",
        "élevé": "high",
        "eleve": "high",
        "hoch": "high",
        "strong": "high",
    }
    return aliases.get(val, DEFAULT_INTENSITY)


def set_intensity(user_id: int, intensity: str) -> None:
    """Set trait intensity while preserving other profile fields."""
    level = normalize_intensity(intensity)
    profile = get_profile(user_id) or {
        "tone": "casual",
        "humor": "medium",
        "energy": "balanced",
        "note": "",
        "source": "custom",
    }
    profile["intensity"] = level
    _merge_profile(user_id, profile)


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
        from infra.utils.json_utils import atomic_json_dump
        atomic_json_dump(_cache, _PROFILES_FILE, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error("Failed to save roleplay_profiles.json: %s", e)


def _load_history() -> None:
    global _history_loaded, _history_cache
    if _history_loaded:
        return
    if os.path.exists(_HISTORY_FILE):
        try:
            with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _history_cache = data if isinstance(data, dict) else {}
        except Exception as e:
            log.error("Failed to load roleplay_history.json: %s", e)
            _history_cache = {}
    _history_loaded = True


def _save_history() -> None:
    try:
        from infra.utils.json_utils import atomic_json_dump
        atomic_json_dump(_history_cache, _HISTORY_FILE, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error("Failed to save roleplay_history.json: %s", e)


def get_history_messages(user_id: int) -> list[dict[str, str]]:
    """OpenAI-format turns for roleplay — isolated from t!c chat memory."""
    _load_history()
    entry = _history_cache.get(str(user_id))
    if not entry:
        return []
    if (time.time() - entry.get("updated", 0)) > RP_TTL_SEC:
        _history_cache.pop(str(user_id), None)
        _save_history()
        return []
    messages: list[dict[str, str]] = []
    for turn in entry.get("turns") or []:
        q = (turn.get("q") or "")[:500]
        a = (turn.get("a") or "")[:600]
        if q:
            messages.append({"role": "user", "content": q})
        if a:
            messages.append({"role": "assistant", "content": a})
    return messages


def add_history_turn(user_id: int, user_msg: str, assistant_msg: str) -> None:
    _load_history()
    key = str(user_id)
    entry = _history_cache.get(key)
    if not entry:
        entry = {"turns": [], "updated": time.time()}
        _history_cache[key] = entry
    entry["updated"] = time.time()
    entry.setdefault("turns", []).append({
        "q": (user_msg or "")[:500],
        "a": (assistant_msg or "")[:600],
        "ts": int(time.time()),
    })
    turns = entry["turns"]
    if len(turns) > RP_MAX_TURNS:
        del turns[: len(turns) - RP_MAX_TURNS]
    if len(_history_cache) > RP_MAX_USERS:
        oldest = min(_history_cache, key=lambda uid: _history_cache[uid].get("updated", 0))
        _history_cache.pop(oldest, None)
    _save_history()


def clear_history(user_id: int) -> None:
    _load_history()
    if _history_cache.pop(str(user_id), None) is not None:
        _save_history()


def get_profile(user_id: int) -> Optional[dict[str, Any]]:
    _load()
    raw = _cache.get(str(user_id))
    return dict(raw) if isinstance(raw, dict) else None


def set_profile(user_id: int, profile: dict[str, Any]) -> None:
    _load()
    _cache[str(user_id)] = profile
    _save()


def get_visibility(user_id: int) -> Optional[str]:
    """Guild roleplay visibility: 'public' (channel) or 'private' (ephemeral/DM). None = not chosen."""
    profile = get_profile(user_id)
    if not profile:
        return None
    vis = profile.get("visibility")
    return vis if vis in ("public", "private") else None


def set_visibility(user_id: int, visibility: str) -> None:
    if visibility not in ("public", "private"):
        return
    profile = get_profile(user_id) or {}
    profile["visibility"] = visibility
    set_profile(user_id, profile)


def reset_profile(user_id: int) -> None:
    """Clear personality + history (visibility preference is cleared too)."""
    _load()
    _cache.pop(str(user_id), None)
    _save()
    clear_history(user_id)


def apply_random_profile(user_id: int) -> None:
    """Set random preset while keeping visibility preference if set."""
    vis = get_visibility(user_id)
    set_profile(user_id, random_profile())
    if vis:
        set_visibility(user_id, vis)


def _merge_profile(user_id: int, profile: dict[str, Any]) -> None:
    vis = get_visibility(user_id)
    set_profile(user_id, profile)
    if vis:
        set_visibility(user_id, vis)


def random_profile() -> dict[str, Any]:
    p = dict(random.choice(PRESETS))
    p["source"] = "random"
    p["intensity"] = normalize_intensity(p.get("intensity"))
    return p


def build_roleplay_prompt(lang: GuildLang, profile: Optional[dict[str, Any]] = None) -> str:
    base = roleplay_system_prompt(lang)
    if not profile:
        return base
    tone = profile.get("tone") or "casual"
    humor = profile.get("humor") or "medium"
    energy = profile.get("energy") or "balanced"
    note = (profile.get("note") or "").strip()[:200]
    intensity = normalize_intensity(profile.get("intensity"))
    extra = (
        f"\nUSER PERSONALITY PRESET:\n"
        f"- Tone: {tone}\n"
        f"- Humor level: {humor}\n"
        f"- Energy: {energy}\n"
        f"- {INTENSITY_PROMPTS[intensity]}\n"
    )
    if note:
        extra += f"- User note: {note}\n"
    if intensity == "high":
        extra += (
            "- At HIGH intensity, exaggerate the preset: punchy phrasing, vivid reactions, "
            "and personality-first replies (still 1-3 sentences).\n"
        )
    elif intensity == "low":
        extra += (
            "- At LOW intensity, keep replies grounded; personality is a hint, not the main event.\n"
        )
    return base + extra


async def _disable_setup_view(interaction: discord.Interaction) -> None:
    """Remove buttons from the setup embed so expired menus do not fail silently."""
    if not interaction.message:
        return
    try:
        await interaction.message.edit(view=None)
    except discord.HTTPException:
        pass


class RoleplayConfigModal(ui.Modal):
    def __init__(self, user_id: int, lang: GuildLang):
        super().__init__(title=tr(lang, "roleplay.modal.title")[:45])
        self.user_id = user_id
        self.lang = lang
        self.tone = ui.TextInput(
            label=tr(lang, "roleplay.modal.tone")[:45],
            placeholder="playful",
            max_length=40,
            required=False,
        )
        self.humor = ui.TextInput(
            label=tr(lang, "roleplay.modal.humor")[:45],
            placeholder="medium",
            max_length=20,
            required=False,
        )
        self.energy = ui.TextInput(
            label=tr(lang, "roleplay.modal.energy")[:45],
            placeholder="bubbly",
            max_length=40,
            required=False,
        )
        self.note = ui.TextInput(
            label=tr(lang, "roleplay.modal.note")[:45],
            style=discord.TextStyle.paragraph,
            placeholder=tr(lang, "roleplay.modal.note_ph")[:100],
            max_length=200,
            required=False,
        )
        self.add_item(self.tone)
        self.add_item(self.humor)
        self.add_item(self.energy)
        self.add_item(self.note)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        existing = get_profile(self.user_id) or {}
        profile = {
            "tone": (self.tone.value or "casual").strip()[:40],
            "humor": (self.humor.value or "medium").strip()[:20],
            "energy": (self.energy.value or "balanced").strip()[:40],
            "note": (self.note.value or "").strip()[:200],
            "source": "custom",
            "intensity": normalize_intensity(existing.get("intensity")),
        }
        _merge_profile(self.user_id, profile)
        await interaction.response.send_message(tr(self.lang, "roleplay.profile.saved"), ephemeral=True)


class RoleplayVisibilityView(ui.View):
    """Ask guild users whether RP replies are public or private (once, until changed in config)."""

    def __init__(
        self,
        user_id: int,
        lang: GuildLang,
        ctx: Any,
        *,
        pending_message: str = "",
        on_continue: Any = None,
    ):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.lang = lang
        self.ctx = ctx
        self.pending_message = (pending_message or "").strip()
        self.on_continue = on_continue

        pub = ui.Button(
            label=tr(lang, "roleplay.visibility.btn_public")[:80],
            style=discord.ButtonStyle.secondary,
            emoji="👥",
        )
        pub.callback = self._on_public
        self.add_item(pub)

        priv = ui.Button(
            label=tr(lang, "roleplay.visibility.btn_private")[:80],
            style=discord.ButtonStyle.primary,
            emoji="🔒",
        )
        priv.callback = self._on_private
        self.add_item(priv)

    async def _choose(self, interaction: discord.Interaction, visibility: str) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                tr(self.lang, "roleplay.profile.not_you"), ephemeral=True
            )
            return
        set_visibility(self.user_id, visibility)
        key = (
            "roleplay.visibility.saved_public"
            if visibility == "public"
            else "roleplay.visibility.saved_private"
        )
        await interaction.response.send_message(tr(self.lang, key), ephemeral=True)
        if self.on_continue and self.pending_message:
            await self.on_continue(self.ctx, message=self.pending_message)

    async def _on_public(self, interaction: discord.Interaction) -> None:
        await self._choose(interaction, "public")

    async def _on_private(self, interaction: discord.Interaction) -> None:
        await self._choose(interaction, "private")


class RoleplaySetupView(ui.View):
    def __init__(self, user_id: int, lang: GuildLang, *, pink: int, state: str = "main"):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.lang = lang
        self.pink = pink
        self._host_message: Optional[discord.Message] = None
        self.state = state

        if state == "main":
            self._build_main()
        elif state == "visibility":
            self._build_visibility()
        elif state == "intensity":
            self._build_intensity()

    def _build_main(self) -> None:
        cfg = ui.Button(
            label=tr(self.lang, "roleplay.btn.configure")[:80],
            style=discord.ButtonStyle.primary,
            emoji="⚙️",
            row=0,
        )
        cfg.callback = self._on_configure
        self.add_item(cfg)

        rnd = ui.Button(
            label=tr(self.lang, "roleplay.btn.random")[:80],
            style=discord.ButtonStyle.secondary,
            emoji="🎲",
            row=0,
        )
        rnd.callback = self._on_random
        self.add_item(rnd)

        reset = ui.Button(
            label=tr(self.lang, "roleplay.btn.reset")[:80],
            style=discord.ButtonStyle.danger,
            emoji="🗑️",
            row=0,
        )
        reset.callback = self._on_reset
        self.add_item(reset)

        vis = ui.Button(
            label="Visibility",
            style=discord.ButtonStyle.secondary,
            emoji="👁️",
            row=1,
        )
        vis.callback = self._nav_visibility
        self.add_item(vis)

        intensity = ui.Button(
            label="Trait Intensity",
            style=discord.ButtonStyle.secondary,
            emoji="🎚️",
            row=1,
        )
        intensity.callback = self._nav_intensity
        self.add_item(intensity)

    def _build_visibility(self) -> None:
        pub = ui.Button(
            label=tr(self.lang, "roleplay.visibility.btn_public")[:80],
            style=discord.ButtonStyle.secondary,
            emoji="👥",
            row=0,
        )
        pub.callback = self._on_vis_public
        self.add_item(pub)

        priv = ui.Button(
            label=tr(self.lang, "roleplay.visibility.btn_private")[:80],
            style=discord.ButtonStyle.primary,
            emoji="🔒",
            row=0,
        )
        priv.callback = self._on_vis_private
        self.add_item(priv)
        
        back = ui.Button(label="Back", style=discord.ButtonStyle.danger, emoji="🔙", row=1)
        back.callback = self._nav_main
        self.add_item(back)

    def _build_intensity(self) -> None:
        low = ui.Button(
            label=tr(self.lang, "roleplay.btn.intensity_low")[:80],
            style=discord.ButtonStyle.secondary,
            emoji="🌱",
            row=0,
        )
        low.callback = self._on_intensity_low
        self.add_item(low)

        med = ui.Button(
            label=tr(self.lang, "roleplay.btn.intensity_medium")[:80],
            style=discord.ButtonStyle.secondary,
            emoji="⚖️",
            row=0,
        )
        med.callback = self._on_intensity_medium
        self.add_item(med)

        high = ui.Button(
            label=tr(self.lang, "roleplay.btn.intensity_high")[:80],
            style=discord.ButtonStyle.secondary,
            emoji="🔥",
            row=0,
        )
        high.callback = self._on_intensity_high
        self.add_item(high)
        
        back = ui.Button(label="Back", style=discord.ButtonStyle.danger, emoji="🔙", row=1)
        back.callback = self._nav_main
        self.add_item(back)

    def bind_message(self, message: discord.Message) -> None:
        self._host_message = message

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self._host_message:
            try:
                await self._host_message.edit(view=self)
            except discord.HTTPException:
                pass

    async def _switch_state(self, interaction: discord.Interaction, new_state: str) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(tr(self.lang, "roleplay.profile.not_you"), ephemeral=True)
            return
        new_view = RoleplaySetupView(self.user_id, self.lang, pink=self.pink, state=new_state)
        new_view.bind_message(self._host_message)
        await interaction.response.edit_message(view=new_view)

    async def _nav_main(self, interaction: discord.Interaction) -> None:
        await self._switch_state(interaction, "main")

    async def _nav_visibility(self, interaction: discord.Interaction) -> None:
        await self._switch_state(interaction, "visibility")

    async def _nav_intensity(self, interaction: discord.Interaction) -> None:
        await self._switch_state(interaction, "intensity")

    async def _on_configure(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(tr(self.lang, "roleplay.profile.not_you"), ephemeral=True)
            return
        await interaction.response.send_modal(RoleplayConfigModal(self.user_id, self.lang))

    async def _on_random(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(tr(self.lang, "roleplay.profile.not_you"), ephemeral=True)
            return
        apply_random_profile(self.user_id)
        await interaction.response.send_message(tr(self.lang, "roleplay.profile.random"), ephemeral=True)
        await _disable_setup_view(interaction)

    async def _on_reset(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(tr(self.lang, "roleplay.profile.not_you"), ephemeral=True)
            return
        reset_profile(self.user_id)
        await interaction.response.send_message(tr(self.lang, "roleplay.profile.reset"), ephemeral=True)
        await _disable_setup_view(interaction)

    async def _on_vis_public(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(tr(self.lang, "roleplay.profile.not_you"), ephemeral=True)
            return
        set_visibility(self.user_id, "public")
        await interaction.response.send_message(tr(self.lang, "roleplay.visibility.saved_public"), ephemeral=True)

    async def _on_vis_private(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(tr(self.lang, "roleplay.profile.not_you"), ephemeral=True)
            return
        set_visibility(self.user_id, "private")
        await interaction.response.send_message(tr(self.lang, "roleplay.visibility.saved_private"), ephemeral=True)

    async def _on_intensity(self, interaction: discord.Interaction, level: str) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(tr(self.lang, "roleplay.profile.not_you"), ephemeral=True)
            return
        set_intensity(self.user_id, level)
        label = tr(self.lang, f"roleplay.intensity.label_{level}")
        await interaction.response.send_message(
            tr(self.lang, "roleplay.intensity.saved", level=label),
            ephemeral=True,
        )

    async def _on_intensity_low(self, interaction: discord.Interaction) -> None:
        await self._on_intensity(interaction, "low")

    async def _on_intensity_medium(self, interaction: discord.Interaction) -> None:
        await self._on_intensity(interaction, "medium")

    async def _on_intensity_high(self, interaction: discord.Interaction) -> None:
        await self._on_intensity(interaction, "high")


def visibility_prompt_embed(lang: GuildLang, *, pink: int) -> discord.Embed:
    return discord.Embed(
        title=tr(lang, "roleplay.visibility.title"),
        description=tr(lang, "roleplay.visibility.body"),
        color=pink,
    )


def setup_embed(lang: GuildLang, *, pink: int, profile: Optional[dict[str, Any]] = None) -> discord.Embed:
    em = discord.Embed(
        title=tr(lang, "roleplay.setup.title"),
        description=tr(lang, "roleplay.setup.body"),
        color=pink,
    )
    if profile:
        intensity = normalize_intensity(profile.get("intensity"))
        em.add_field(
            name=tr(lang, "roleplay.intensity.field_title"),
            value=tr(lang, f"roleplay.intensity.current_{intensity}"),
            inline=False,
        )
    em.set_footer(text=tr(lang, "roleplay.setup.footer"))
    return em
