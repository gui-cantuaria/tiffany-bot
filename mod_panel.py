import discord
from discord.ui import View, Button, Select, ChannelSelect, RoleSelect, UserSelect
import guild_config
from locale_utils import tr, GuildLang

def build_mod_panel_embed(guild: discord.Guild, lang: GuildLang, *, pink: int) -> discord.Embed:
    config = guild_config.get_guild_config(guild.id)
    
    strict_filter = "🟢 ON" if config.get("strict_filter", True) else "🔴 OFF"
    anti_spam = "🟢 ON" if config.get("anti_spam", True) else "🔴 OFF"
    dj_role = f"<@&{config['dj_role']}>" if config.get("dj_role") else "Nenhum"
    mod_log = f"<#{config['mod_log_channel']}>" if config.get("mod_log_channel") else "Nenhum"
    blacklist_count = len(config.get("blacklist", []))
    offers_ch = f"<#{config['offers_channel']}>" if config.get("offers_channel") else "Nenhum"
    tags_count = len(config.get("affiliate_tags", {}))
    
    embed = discord.Embed(
        title="🛡️ Painel de Moderação - Tiffany",
        description="Configure as opções de segurança e moderação do servidor.",
        color=pink
    )
    embed.add_field(name="Filtro Restrito (Conteúdo)", value=strict_filter, inline=True)
    embed.add_field(name="Anti-Spam", value=anti_spam, inline=True)
    embed.add_field(name="Blacklist", value=f"{blacklist_count} usuário(s)", inline=True)
    embed.add_field(name="Cargo DJ (Apenas DJs controlam música)", value=dj_role, inline=False)
    embed.add_field(name="Canal de Logs de Moderação", value=mod_log, inline=False)
    embed.add_field(name="Canal de Ofertas (Afiliados)", value=offers_ch, inline=True)
    embed.add_field(name="Tags de Afiliado (Servidor)", value=f"{tags_count} configuradas", inline=True)
    
    return embed

class ModPanelMainView(View):
    def __init__(self, guild: discord.Guild, lang: GuildLang, *, pink: int):
        super().__init__(timeout=300)
        self.guild = guild
        self.lang = lang
        self.pink = pink
        self.config = guild_config.get_guild_config(guild.id)
        
        btn_filter = Button(label="Filtro Restrito", style=discord.ButtonStyle.success if self.config.get("strict_filter", True) else discord.ButtonStyle.danger, row=0)
        btn_filter.callback = self.toggle_filter
        self.add_item(btn_filter)
        
        btn_spam = Button(label="Anti-Spam", style=discord.ButtonStyle.success if self.config.get("anti_spam", True) else discord.ButtonStyle.danger, row=0)
        btn_spam.callback = self.toggle_spam
        self.add_item(btn_spam)
        
        btn_dj = Button(label="Configurar Cargo DJ", style=discord.ButtonStyle.secondary, row=1)
        btn_dj.callback = self.config_dj
        self.add_item(btn_dj)
        
        btn_logs = Button(label="Configurar Logs", style=discord.ButtonStyle.secondary, row=1)
        btn_logs.callback = self.config_logs
        self.add_item(btn_logs)
        
        btn_bl = Button(label="Gerenciar Blacklist", style=discord.ButtonStyle.secondary, row=2)
        btn_bl.callback = self.config_blacklist
        self.add_item(btn_bl)

        btn_offers = Button(label="Canal de Ofertas", style=discord.ButtonStyle.primary, row=3)
        btn_offers.callback = self.config_offers
        self.add_item(btn_offers)

        btn_affiliates = Button(label="Tags de Afiliado", style=discord.ButtonStyle.success, row=3)
        btn_affiliates.callback = self.config_affiliates
        self.add_item(btn_affiliates)

    async def _update(self, interaction: discord.Interaction):
        guild_config.save_guild_config(self.guild.id, self.config)
        embed = build_mod_panel_embed(self.guild, self.lang, pink=self.pink)
        new_view = ModPanelMainView(self.guild, self.lang, pink=self.pink)
        new_view.message = self.message
        await interaction.response.edit_message(embed=embed, view=new_view)

    async def toggle_filter(self, interaction: discord.Interaction):
        self.config["strict_filter"] = not self.config.get("strict_filter", True)
        await self._update(interaction)
        
    async def toggle_spam(self, interaction: discord.Interaction):
        self.config["anti_spam"] = not self.config.get("anti_spam", True)
        await self._update(interaction)

    async def config_dj(self, interaction: discord.Interaction):
        view = RoleSelectView(self)
        await interaction.response.send_message("Selecione o cargo de DJ (ou cancele/limpe):", view=view, ephemeral=True)
        
    async def config_logs(self, interaction: discord.Interaction):
        view = ChannelSelectView(self)
        await interaction.response.send_message("Selecione o canal para Logs de Moderação:", view=view, ephemeral=True)
        
    async def config_blacklist(self, interaction: discord.Interaction):
        view = BlacklistView(self)
        await interaction.response.send_message("Selecione usuários para adicionar ou remover da blacklist:", view=view, ephemeral=True)

    async def config_offers(self, interaction: discord.Interaction):
        view = OffersChannelSelectView(self)
        await interaction.response.send_message("Selecione o canal para postar as ofertas diárias:", view=view, ephemeral=True)

    async def config_affiliates(self, interaction: discord.Interaction):
        modal = AffiliateModal(self)
        await interaction.response.send_modal(modal)

class RoleSelectView(View):
    def __init__(self, parent_view: ModPanelMainView):
        super().__init__(timeout=120)
        self.parent = parent_view
        
    @discord.ui.select(cls=RoleSelect, placeholder="Selecione o cargo de DJ")
    async def select_role(self, interaction: discord.Interaction, select: RoleSelect):
        role = select.values[0]
        self.parent.config["dj_role"] = role.id
        await interaction.response.send_message(f"Cargo DJ definido para {role.mention}!", ephemeral=True)
        await self.parent._update(interaction)

    @discord.ui.button(label="Limpar Cargo", style=discord.ButtonStyle.danger)
    async def clear_role(self, interaction: discord.Interaction, button: Button):
        self.parent.config["dj_role"] = None
        await interaction.response.send_message("Cargo DJ removido.", ephemeral=True)
        await self.parent._update(interaction)

class ChannelSelectView(View):
    def __init__(self, parent_view: ModPanelMainView):
        super().__init__(timeout=120)
        self.parent = parent_view
        
    @discord.ui.select(cls=ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Selecione o canal de logs")
    async def select_channel(self, interaction: discord.Interaction, select: ChannelSelect):
        channel = select.values[0]
        self.parent.config["mod_log_channel"] = channel.id
        await interaction.response.send_message(f"Canal de logs definido para {channel.mention}!", ephemeral=True)
        await self.parent._update(interaction)

    @discord.ui.button(label="Desativar Logs", style=discord.ButtonStyle.danger)
    async def clear_channel(self, interaction: discord.Interaction, button: Button):
        self.parent.config["mod_log_channel"] = None
        await interaction.response.send_message("Logs de moderação desativados.", ephemeral=True)
        await self.parent._update(interaction)

class BlacklistView(View):
    def __init__(self, parent_view: ModPanelMainView):
        super().__init__(timeout=120)
        self.parent = parent_view
        
    @discord.ui.select(cls=UserSelect, placeholder="Selecione usuários para dar/remover blacklist", max_values=5)
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
        msg = "Blacklist atualizada:\\n"
        if added: msg += f"Adicionados: {', '.join(added)}\\n"
        if removed: msg += f"Removidos: {', '.join(removed)}"
        await interaction.response.send_message(msg, ephemeral=True)
        await self.parent._update(interaction)

class OffersChannelSelectView(View):
    def __init__(self, parent_view: ModPanelMainView):
        super().__init__(timeout=120)
        self.parent = parent_view
        
    @discord.ui.select(cls=ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Selecione o canal de Ofertas")
    async def select_channel(self, interaction: discord.Interaction, select: ChannelSelect):
        channel = select.values[0]
        self.parent.config["offers_channel"] = channel.id
        await interaction.response.send_message(f"Canal de Ofertas definido para {channel.mention}!", ephemeral=True)
        await self.parent._update(interaction)

    @discord.ui.button(label="Desativar Ofertas", style=discord.ButtonStyle.danger)
    async def clear_channel(self, interaction: discord.Interaction, button: Button):
        self.parent.config["offers_channel"] = None
        await interaction.response.send_message("Postagem de ofertas desativada neste servidor.", ephemeral=True)
        await self.parent._update(interaction)

class AffiliateModal(discord.ui.Modal, title="Configurar Tags de Afiliado"):
    amazon = discord.ui.TextInput(label="Amazon Tag", placeholder="suatag-20", required=False)
    ml_id = discord.ui.TextInput(label="Mercado Livre (Label/Word)", placeholder="seunome", required=False)
    ml_tool = discord.ui.TextInput(label="Mercado Livre (Tool ID NUMÉRICO)", placeholder="12345678", required=False)
    aliexpress = discord.ui.TextInput(label="AliExpress ID", placeholder="12345678_1234", required=False)
    shopee = discord.ui.TextInput(label="Shopee ID", placeholder="123456", required=False)

    def __init__(self, parent_view: ModPanelMainView):
        super().__init__()
        self.parent = parent_view
        tags = self.parent.config.get("affiliate_tags", {})
        self.amazon.default = tags.get("amazon_tag", "")
        self.ml_id.default = tags.get("mercadolivre_id", "")
        self.ml_tool.default = tags.get("mercadolivre_tool_id", "")
        self.aliexpress.default = tags.get("aliexpress_id", "")
        self.shopee.default = tags.get("shopee_id", "")

    async def on_submit(self, interaction: discord.Interaction):
        tags = self.parent.config.get("affiliate_tags", {})
        
        def _set(key, val):
            if val: tags[key] = val.strip()
            else: tags.pop(key, None)
            
        _set("amazon_tag", self.amazon.value)
        _set("mercadolivre_id", self.ml_id.value)
        _set("mercadolivre_tool_id", self.ml_tool.value)
        _set("aliexpress_id", self.aliexpress.value)
        _set("shopee_id", self.shopee.value)
        
        self.parent.config["affiliate_tags"] = tags
        await interaction.response.send_message(
            "✅ Tags salvas com sucesso!\n"
            "⚠️ O plano atual é 50/50: suas tags têm 50% de chance de serem usadas nos links enviados no seu servidor.",
            ephemeral=True
        )
        await self.parent._update(interaction)
