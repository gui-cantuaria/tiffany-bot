"""User settings panel — personal feature toggles."""

from __future__ import annotations

import discord
from discord.ui import Button, Select, View

import user_settings
from feature_flags import USER_FEATURE_KEYS, feature_label
from locale_utils import GuildLang, tr


def build_settings_embed(user_id: int, lang: GuildLang, *, pink: int) -> discord.Embed:
    features = user_settings.get_user_features(user_id)
    lines = []
    for key in USER_FEATURE_KEYS:
        state = tr(lang, "mod.on") if features.get(key, True) else tr(lang, "mod.off")
        lines.append(f"**{feature_label(lang, key)}** — {state}")

    embed = discord.Embed(
        title=tr(lang, "settings.panel.title"),
        description=tr(lang, "settings.panel.desc"),
        color=pink,
    )
    embed.add_field(
        name=tr(lang, "settings.field.features"),
        value="\n".join(lines) or tr(lang, "mod.none"),
        inline=False,
    )
    embed.set_footer(text=tr(lang, "settings.panel.footer"))
    return embed


class SettingsMainView(View):
    def __init__(self, user_id: int, lang: GuildLang, *, pink: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.lang = lang
        self.pink = pink

        btn = Button(label=tr(lang, "settings.btn.toggle"), style=discord.ButtonStyle.primary, row=0)
        btn.callback = self.open_toggle
        self.add_item(btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            msg = tr(self.lang, "settings.deny_other")
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return False
        return True

    async def open_toggle(self, interaction: discord.Interaction) -> None:
        view = UserFeatureSelectView(self)
        await interaction.response.send_message(
            tr(self.lang, "settings.prompt.toggle"),
            view=view,
            ephemeral=True,
        )

    async def refresh_panel(self, interaction: discord.Interaction) -> None:
        embed = build_settings_embed(self.user_id, self.lang, pink=self.pink)
        new_view = SettingsMainView(self.user_id, self.lang, pink=self.pink)
        panel_msg = getattr(self, "message", None) or interaction.message
        if panel_msg:
            await panel_msg.edit(embed=embed, view=new_view)


class UserFeatureSelectView(View):
    def __init__(self, parent: SettingsMainView):
        super().__init__(timeout=120)
        self.parent = parent
        self._build_select()

    def _build_select(self) -> None:
        lang = self.parent.lang
        features = user_settings.get_user_features(self.parent.user_id)
        options = []
        for key in USER_FEATURE_KEYS:
            enabled = features.get(key, True)
            emoji = "✅" if enabled else "❌"
            options.append(
                discord.SelectOption(
                    label=feature_label(lang, key)[:100],
                    value=key,
                    emoji=emoji,
                    description=tr(lang, "mod.on") if enabled else tr(lang, "mod.off"),
                )
            )
        select = Select(
            placeholder=tr(lang, "settings.select.placeholder"),
            options=options[:25],
            min_values=1,
            max_values=1,
        )
        select.callback = self.on_select
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.parent.user_id

    async def on_select(self, interaction: discord.Interaction) -> None:
        select = interaction.data.get("values", [])
        if not select:
            await interaction.response.defer()
            return
        key = select[0]
        new_state = user_settings.toggle_feature(self.parent.user_id, key)
        label = feature_label(self.parent.lang, key)
        state = tr(self.parent.lang, "mod.on") if new_state else tr(self.parent.lang, "mod.off")
        await interaction.response.send_message(
            tr(self.parent.lang, "settings.feature_toggled", feature=label, state=state),
            ephemeral=True,
        )
        await self.parent.refresh_panel(interaction)
