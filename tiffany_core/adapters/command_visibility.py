"""
Tiffany OS — Dynamic Command Visibility & Debounced Guild Tree Syncer
====================================================================
Automatically conceals (removes from Discord's UI menu) slash commands belonging to features
disabled via the Moderation Panel. Implements debounce coalescing to prevent Discord REST API
rate limit exhaustion if administrators toggle multiple features in rapid succession.
"""

from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict, Set, Optional

from feature_flags import feature_for_command, is_feature_allowed, feature_denial_message
from locale_utils import tr, resolve_lang

log = logging.getLogger("tiffany.core.command_visibility")

class DynamicCommandTreeSyncer:
    """
    Debounced manager responsible for dynamically pruning disabled slash commands
    from specific Discord guild command trees without blocking UI event loops.
    """
    def __init__(self, debounce_sec: float = 3.0) -> None:
        self.debounce_sec = debounce_sec
        self._sync_timers: Dict[int, asyncio.TimerHandle] = {}
        self._in_progress: Set[int] = set()
        self._last_synced_features: Dict[int, Dict[str, bool]] = {}

    def schedule_guild_sync(self, bot: Any, guild: Any, features: Dict[str, bool]) -> None:
        """
        Schedules an asynchronous, debounced command tree synchronization for a guild.
        Multiple successive feature toggles within `debounce_sec` will merge into ONE single sync call.
        """
        if not bot or not hasattr(bot, "tree") or not guild:
            return
            
        guild_id = int(guild.id)
        
        # If identical to previously synced state, skip redundant network call
        if self._last_synced_features.get(guild_id) == features:
            log.debug("[CommandVisibility: Guild %d] State unchanged -> skipping tree sync", guild_id)
            return

        loop = asyncio.get_running_loop()
        
        # Cancel any existing pending debounce timer for this guild
        if guild_id in self._sync_timers:
            self._sync_timers[guild_id].cancel()
            log.debug("[CommandVisibility: Guild %d] Debounce reset for rapid toggle", guild_id)

        # Schedule new execution after debounce window
        handle = loop.call_later(
            self.debounce_sec,
            lambda: loop.create_task(self._execute_sync(bot, guild, features.copy()))
        )
        self._sync_timers[guild_id] = handle

    async def _execute_sync(self, bot: Any, guild: Any, features: Dict[str, bool]) -> None:
        guild_id = int(guild.id)
        self._sync_timers.pop(guild_id, None)
        
        if guild_id in self._in_progress:
            log.warning("[CommandVisibility: Guild %d] Sync already underway; deferring attempt", guild_id)
            return
            
        self._in_progress.add(guild_id)
        try:
            log.info("[CommandVisibility: Guild %d] Synchronizing customized command tree...", guild_id)
            # 1. Fetch all registered application commands in bot's global command repository
            all_commands = bot.tree.get_commands()
            
            # 2. Filter commands whose associated domain module is currently DISABLED
            enabled_commands = []
            for cmd in all_commands:
                feat = feature_for_command(cmd.name)
                if not feat or features.get(feat, True):
                    enabled_commands.append(cmd)
                else:
                    log.debug("[CommandVisibility: Guild %d] Hiding disabled command '/%s' (%s)", guild_id, cmd.name, feat)
            
            # 3. Update Guild-scoped Command Tree and push via REST API to vanish disabled commands
            bot.tree.clear_commands(guild=guild)
            for cmd in enabled_commands:
                bot.tree.add_command(cmd, guild=guild)
                
            await bot.tree.sync(guild=guild)
            self._last_synced_features[guild_id] = features.copy()
            log.info("[CommandVisibility: Guild %d] Successfully pruned menu to %d active slash commands!", 
                     guild_id, len(enabled_commands))
                     
        except Exception as exc:
            log.exception("[CommandVisibility: Guild %d] Failed to sync dynamic tree: %s", guild_id, exc)
        finally:
            self._in_progress.discard(guild_id)

    async def verify_command_access_or_deny(self, ctx_or_interaction: Any, command_name: Optional[str] = None) -> bool:
        """
        Fail-Closed Execution Gatekeeper: Ensures that if an outdated client attempts to call
        a disabled command before Discord's UI refreshes, it receives a localized warning reply.
        """
        cmd_name = command_name
        guild_id = None
        user_id = None
        
        if hasattr(ctx_or_interaction, "command") and ctx_or_interaction.command:
            cmd_name = cmd_name or ctx_or_interaction.command.name
            guild_id = ctx_or_interaction.guild.id if ctx_or_interaction.guild else None
            user_id = ctx_or_interaction.author.id if hasattr(ctx_or_interaction, "author") else ctx_or_interaction.user.id
            lang = getattr(ctx_or_interaction, "_tiffany_lang", None) or "pt"
        else:
            guild = getattr(ctx_or_interaction, "guild", None)
            guild_id = ctx_or_interaction.guild_id if hasattr(ctx_or_interaction, "guild_id") else None
            user_id = ctx_or_interaction.user.id if hasattr(ctx_or_interaction, "user") else 0
            lang = resolve_lang(guild, user_id, discord_locale=getattr(ctx_or_interaction, "locale", None))
            
        feat = feature_for_command(cmd_name)
        if not feat:
            return True
            
        if is_feature_allowed(guild_id=guild_id, user_id=user_id, feature=feat):
            return True
            
        # Feature is disabled -> return immediate localized denial message
        denial_msg = feature_denial_message(lang, feat, guild_id=guild_id, user_id=user_id)
        
        if hasattr(ctx_or_interaction, "response") and not ctx_or_interaction.response.is_done():
            await ctx_or_interaction.response.send_message(denial_msg, ephemeral=True)
        elif hasattr(ctx_or_interaction, "reply"):
            await ctx_or_interaction.reply(denial_msg, ephemeral=True)
        else:
            log.warning("Could not dispatch feature denial message to user %d for command %s", user_id, cmd_name)
            
        return False

# Global command visibility orchestrator
command_visibility_syncer = DynamicCommandTreeSyncer(debounce_sec=2.0)
