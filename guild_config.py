import os
import json
import logging
from typing import Dict, Any, List, Optional
import discord

log = logging.getLogger("tiffany-bot")

_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guild_config.json")
_cache: Dict[str, Dict[str, Any]] = {}
_loaded = False

def _load() -> None:
    global _loaded, _cache
    if _loaded:
        return
    if os.path.exists(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                _cache = json.load(f)
        except Exception as e:
            log.error("Failed to load guild_config.json: %s", e)
            _cache = {}
    _loaded = True

def _save() -> None:
    try:
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(_cache, f, indent=4)
    except Exception as e:
        log.error("Failed to save guild_config.json: %s", e)

def get_guild_config(guild_id: int) -> Dict[str, Any]:
    _load()
    gid = str(guild_id)
    if gid not in _cache:
        _cache[gid] = {
            "strict_filter": True,
            "anti_spam": True,
            "dj_role": None,
            "mod_log_channel": None,
            "blacklist": [],
            "offers_channel": None,
            "allowed_categories": ["hardware", "jogos", "periféricos", "acessórios", "monitores", "outros"],
            "affiliate_tags": {}
        }
    return _cache[gid]

def save_guild_config(guild_id: int, config: Dict[str, Any]) -> None:
    _load()
    _cache[str(guild_id)] = config
    _save()

def get_all_guilds_config() -> Dict[str, Dict[str, Any]]:
    _load()
    return dict(_cache)

def is_strict_filter_enabled(guild_id: int) -> bool:
    return get_guild_config(guild_id).get("strict_filter", True)

def is_anti_spam_enabled(guild_id: int) -> bool:
    return get_guild_config(guild_id).get("anti_spam", True)

def get_dj_role(guild_id: int) -> Optional[int]:
    return get_guild_config(guild_id).get("dj_role")

def get_mod_log_channel(guild_id: int) -> Optional[int]:
    return get_guild_config(guild_id).get("mod_log_channel")

def get_blacklist(guild_id: int) -> List[int]:
    return get_guild_config(guild_id).get("blacklist", [])

def is_blacklisted(guild_id: int, user_id: int) -> bool:
    return user_id in get_blacklist(guild_id)


def is_user_blacklisted_anywhere(user_id: int) -> bool:
    """True if user_id appears on any guild blacklist (used for DM / cross-guild checks)."""
    _load()
    uid = int(user_id)
    for cfg in _cache.values():
        if uid in cfg.get("blacklist", []):
            return True
    return False

def get_offers_channel(guild_id: int) -> Optional[int]:
    return get_guild_config(guild_id).get("offers_channel")

def get_allowed_categories(guild_id: int) -> List[str]:
    return get_guild_config(guild_id).get("allowed_categories", [])

def get_affiliate_tags(guild_id: int) -> Dict[str, str]:
    return get_guild_config(guild_id).get("affiliate_tags", {})

async def log_mod_action(guild: discord.Guild, embed: discord.Embed) -> None:
    channel_id = get_mod_log_channel(guild.id)
    if not channel_id:
        return
    channel = guild.get_channel(channel_id)
    if channel and isinstance(channel, discord.TextChannel):
        try:
            await channel.send(embed=embed)
        except Exception:
            pass
