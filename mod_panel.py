import discord
from discord.ui import View, Button, Select, ChannelSelect, RoleSelect, UserSelect
import guild_config
from locale_utils import tr, GuildLang, interaction_lang

def build_mod_panel_embed(guild: discord.Guild, lang: GuildLang, *, pink: int) -> discord.Embed:
    config = guild_config.get_guild_config(guild.id)
    none = tr(lang, "mod.none")
    strict_filter = tr(lang, "mod.on") if config.get("strict_filter", True) else tr(lang, "mod.off")
    anti_spam = tr(lang, "mod.on") if config.get("anti_spam", True) else tr(lang, "mod.off")
    dj_role = f"<@&{config['dj_role']}>" if config.get("dj_role") else none
    mod_log = f"<#{config['mod_log_channel']}>" if config.get("mod_log_channel") else none
    blacklist_count = len(config.get("blacklist", []))
    offers_ch = f"<#{config['offers_channel']}>" if config.get("offers_channel") else none
    tags_count = len(config.get("affiliate_tags", {}))

    embed = discord.Embed(
        title=tr(lang, "mod.panel.title"),
        description=tr(lang, "mod.panel.desc"),
        color=pink,
    )
    embed.add_field(name=tr(lang, "mod.field.strict_filter"), value=strict_filter, inline=True)
    embed.add_field(name=tr(lang, "mod.field.anti_spam"), value=anti_spam, inline=True)
    embed.add_field(
        name=tr(lang, "mod.field.blacklist"),
        value=tr(lang, "mod.blacklist_count", count=blacklist_count),
        inline=True,
    )
    embed.add_field(name=tr(lang, "mod.field.dj"), value=dj_role, inline=False)
    embed.add_field(name=tr(lang, "mod.field.mod_log"), value=mod_log, inline=False)
    embed.add_field(name=tr(lang, "mod.field.offers"), value=offers_ch, inline=True)
    embed.add_field(
        name=tr(lang, "mod.field.affiliate_tags"),
        value=tr(lang, "mod.tags_count", count=tags_count),
        inline=True,
    )
    return embed


def _is_panel_admin(interaction: discord.Interaction, *, guild_id: int | None = None) -> bool:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False
    if guild_id is not None and interaction.guild.id != guild_id:
        return False
    return interaction.user.guild_permissions.administrator


async def _deny_panel_admin(interaction: discord.Interaction) -> None:
    msg = tr(interaction_lang(interaction), "mod.deny_admin")
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)


async def _assert_panel_access(interaction: discord.Interaction, guild_id: int) -> bool:
    """Ensure interaction is from the same guild and user is admin."""
    if not interaction.guild or interaction.guild.id != guild_id:
        msg = tr(interaction_lang(interaction), "mod.wrong_guild")
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        return False
    if _is_panel_admin(interaction, guild_id=guild_id):
        return True
    await _deny_panel_admin(interaction)
    return False


class ModPanelMainView(View):
    def __init__(self, guild: discord.Guild, lang: GuildLang, *, pink: int):
        super().__init__(timeout=300)
        self.guild = guild
        self.lang = lang
        self.pink = pink
        self.config = guild_config.get_guild_config(guild.id)

        btn_filter = Button(
            label=tr(lang, "mod.btn.strict_filter"),
            style=discord.ButtonStyle.success if self.config.get("strict_filter", True) else discord.ButtonStyle.danger,
            row=0,
        )
        btn_filter.callback = self.toggle_filter
        self.add_item(btn_filter)

        btn_spam = Button(
            label=tr(lang, "mod.btn.anti_spam"),
            style=discord.ButtonStyle.success if self.config.get("anti_spam", True) else discord.ButtonStyle.danger,
            row=0,
        )
        btn_spam.callback = self.toggle_spam
        self.add_item(btn_spam)

        btn_dj = Button(label=tr(lang, "mod.btn.dj"), style=discord.ButtonStyle.secondary, row=1)
        btn_dj.callback = self.config_dj
        self.add_item(btn_dj)

        btn_logs = Button(label=tr(lang, "mod.btn.logs"), style=discord.ButtonStyle.secondary, row=1)
        btn_logs.callback = self.config_logs
        self.add_item(btn_logs)

        btn_bl = Button(label=tr(lang, "mod.btn.blacklist"), style=discord.ButtonStyle.secondary, row=2)
        btn_bl.callback = self.config_blacklist
        self.add_item(btn_bl)

        btn_offers = Button(label=tr(lang, "mod.btn.offers"), style=discord.ButtonStyle.primary, row=3)
        btn_offers.callback = self.config_offers
        self.add_item(btn_offers)

        btn_affiliates = Button(label=tr(lang, "mod.btn.affiliates"), style=discord.ButtonStyle.success, row=3)
        btn_affiliates.callback = self.config_affiliates
        self.add_item(btn_affiliates)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _assert_panel_access(interaction, self.guild.id)

    async def _update(self, interaction: discord.Interaction) -> None:
        guild_config.save_guild_config(self.guild.id, self.config)
        embed = build_mod_panel_embed(self.guild, self.lang, pink=self.pink)
        new_view = ModPanelMainView(self.guild, self.lang, pink=self.pink)
        panel_msg = getattr(self, "message", None) or interaction.message
        if panel_msg:
            await panel_msg.edit(embed=embed, view=new_view)

    async def toggle_filter(self, interaction: discord.Interaction):
        self.config["strict_filter"] = not self.config.get("strict_filter", True)
        await interaction.response.defer()
        await self._update(interaction)

    async def toggle_spam(self, interaction: discord.Interaction):
        self.config["anti_spam"] = not self.config.get("anti_spam", True)
        await interaction.response.defer()
        await self._update(interaction)

    async def config_dj(self, interaction: discord.Interaction):
        view = RoleSelectView(self)
        await interaction.response.send_message(tr(self.lang, "mod.prompt.dj"), view=view, ephemeral=True)

    async def config_logs(self, interaction: discord.Interaction):
        view = ChannelSelectView(self)
        await interaction.response.send_message(tr(self.lang, "mod.prompt.logs"), view=view, ephemeral=True)

    async def config_blacklist(self, interaction: discord.Interaction):
        view = BlacklistView(self)
        await interaction.response.send_message(tr(self.lang, "mod.prompt.blacklist"), view=view, ephemeral=True)

    async def config_offers(self, interaction: discord.Interaction):
        view = OffersChannelSelectView(self)
        await interaction.response.send_message(tr(self.lang, "mod.prompt.offers"), view=view, ephemeral=True)

    async def config_affiliates(self, interaction: discord.Interaction):
        modal = AffiliateModal(self)
        await interaction.response.send_modal(modal)


class RoleSelectView(View):
    def __init__(self, parent_view: ModPanelMainView):
        super().__init__(timeout=120)
        self.parent = parent_view

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _assert_panel_access(interaction, self.parent.guild.id)

    @discord.ui.select(cls=RoleSelect, placeholder="DJ role")
    async def select_role(self, interaction: discord.Interaction, select: RoleSelect):
        role = select.values[0]
        self.parent.config["dj_role"] = role.id
        await interaction.response.send_message(
            tr(self.parent.lang, "mod.dj_set", role=role.mention), ephemeral=True,
        )
        await self.parent._update(interaction)

    @discord.ui.button(label="Clear", style=discord.ButtonStyle.danger)
    async def clear_role(self, interaction: discord.Interaction, button: Button):
        self.parent.config["dj_role"] = None
        await interaction.response.send_message(tr(self.parent.lang, "mod.dj_cleared"), ephemeral=True)
        await self.parent._update(interaction)


class ChannelSelectView(View):
    def __init__(self, parent_view: ModPanelMainView):
        super().__init__(timeout=120)
        self.parent = parent_view

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _assert_panel_access(interaction, self.parent.guild.id)

    @discord.ui.select(cls=ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Log channel")
    async def select_channel(self, interaction: discord.Interaction, select: ChannelSelect):
        channel = select.values[0]
        self.parent.config["mod_log_channel"] = channel.id
        await interaction.response.send_message(
            tr(self.parent.lang, "mod.logs_set", channel=channel.mention), ephemeral=True,
        )
        await self.parent._update(interaction)

    @discord.ui.button(label="Disable", style=discord.ButtonStyle.danger)
    async def clear_channel(self, interaction: discord.Interaction, button: Button):
        self.parent.config["mod_log_channel"] = None
        await interaction.response.send_message(tr(self.parent.lang, "mod.logs_disabled"), ephemeral=True)
        await self.parent._update(interaction)


class BlacklistView(View):
    def __init__(self, parent_view: ModPanelMainView):
        super().__init__(timeout=120)
        self.parent = parent_view

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _assert_panel_access(interaction, self.parent.guild.id)

    @discord.ui.select(cls=UserSelect, placeholder="Users", max_values=5)
    async def select_users(self, interaction: discord.Interaction, select: UserSelect):
        added = []
        removed = []
        bl = self.parent.config.get("blacklist", [])
        for user in select.values:
            if user.id in bl:
                bl.remove(user.id)
                removed.append(user.display_name)
            else:
                bl.append(user.id)
                added.append(user.display_name)
        self.parent.config["blacklist"] = bl
        msg = tr(self.parent.lang, "mod.blacklist_updated")
        if added:
            msg += "\n" + tr(self.parent.lang, "mod.blacklist_added", names=", ".join(added))
        if removed:
            msg += "\n" + tr(self.parent.lang, "mod.blacklist_removed", names=", ".join(removed))
        await interaction.response.send_message(msg, ephemeral=True)
        await self.parent._update(interaction)


class OffersChannelSelectView(View):
    def __init__(self, parent_view: ModPanelMainView):
        super().__init__(timeout=120)
        self.parent = parent_view

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _assert_panel_access(interaction, self.parent.guild.id)

    @discord.ui.select(cls=ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Offers channel")
    async def select_channel(self, interaction: discord.Interaction, select: ChannelSelect):
        channel = select.values[0]
        self.parent.config["offers_channel"] = channel.id
        await interaction.response.send_message(
            tr(self.parent.lang, "mod.offers_set", channel=channel.mention), ephemeral=True,
        )
        await self.parent._update(interaction)

    @discord.ui.button(label="Disable", style=discord.ButtonStyle.danger)
    async def clear_channel(self, interaction: discord.Interaction, button: Button):
        self.parent.config["offers_channel"] = None
        await interaction.response.send_message(tr(self.parent.lang, "mod.offers_disabled"), ephemeral=True)
        await self.parent._update(interaction)


class AffiliateModal(discord.ui.Modal):
    amazon = discord.ui.TextInput(label="Amazon Tag", placeholder="suatag-20", required=False)
    ml_id = discord.ui.TextInput(label="Mercado Livre (Label/Word)", placeholder="seunome", required=False)
    ml_tool = discord.ui.TextInput(label="Mercado Livre (Tool ID NUMÉRICO)", placeholder="12345678", required=False)
    aliexpress = discord.ui.TextInput(label="AliExpress ID", placeholder="12345678_1234", required=False)
    shopee = discord.ui.TextInput(label="Shopee ID", placeholder="123456", required=False)

    def __init__(self, parent_view: ModPanelMainView):
        super().__init__(title=tr(parent_view.lang, "mod.modal.affiliate_title"))
        self.parent = parent_view
        tags = self.parent.config.get("affiliate_tags", {})
        self.amazon.default = tags.get("amazon_tag", "")
        self.ml_id.default = tags.get("mercadolivre_id", "")
        self.ml_tool.default = tags.get("mercadolivre_tool_id", "")
        self.aliexpress.default = tags.get("aliexpress_id", "")
        self.shopee.default = tags.get("shopee_id", "")

    async def on_submit(self, interaction: discord.Interaction):
        if not await _assert_panel_access(interaction, self.parent.guild.id):
            return
        tags = self.parent.config.get("affiliate_tags", {})

        def _set(key, val):
            if val:
                tags[key] = val.strip()
            else:
                tags.pop(key, None)

        _set("amazon_tag", self.amazon.value)
        _set("mercadolivre_id", self.ml_id.value)
        _set("mercadolivre_tool_id", self.ml_tool.value)
        _set("aliexpress_id", self.aliexpress.value)
        _set("shopee_id", self.shopee.value)

        self.parent.config["affiliate_tags"] = tags
        await interaction.response.send_message(tr(self.parent.lang, "mod.affiliate_saved"), ephemeral=True)
        await self.parent._update(interaction)
