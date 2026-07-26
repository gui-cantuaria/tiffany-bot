"""Guild and user feature toggles — maps commands to feature keys."""

from __future__ import annotations

from typing import Optional

import guild_config
import user_settings
from locale_utils import GuildLang, tr

# All toggleable modules (defaults ON for backward compatibility).
GUILD_FEATURE_KEYS: tuple[str, ...] = (
    "music",
    "chat",
    "imagine",
    "roleplay",
    "games",
    "summary",
    "giveaways",
    "embeds",
    "offers",
    "dice",
    "voice_stt",
)

USER_FEATURE_KEYS: tuple[str, ...] = user_settings.user_feature_keys()

_MUSIC_COMMANDS = frozenset({
    "play", "p", "skip", "s", "pause", "pa", "resume", "re", "clear", "cl",
    "loop", "l", "lo", "shuffle", "sh", "replay", "rpl", "queue", "q", "np",
    "random", "r", "playlist", "pl", "seek", "ff", "volume", "v", "vol",
    "autoplay", "ap", "lyrics", "ly", "247", "nonstop", "clip", "cp",
})

_COMMAND_TO_FEATURE: dict[str, str] = {}
for _cmd in _MUSIC_COMMANDS:
    _COMMAND_TO_FEATURE[_cmd] = "music"
for _cmd in ("chat", "c"):
    _COMMAND_TO_FEATURE[_cmd] = "chat"
for _cmd in ("imagine", "img"):
    _COMMAND_TO_FEATURE[_cmd] = "imagine"
for _cmd in ("roleplay", "rp"):
    _COMMAND_TO_FEATURE[_cmd] = "roleplay"
for _cmd in ("game", "g", "games"):
    _COMMAND_TO_FEATURE[_cmd] = "games"
for _cmd in ("su", "summary"):
    _COMMAND_TO_FEATURE[_cmd] = "summary"
for _cmd in ("giveaway", "gw"):
    _COMMAND_TO_FEATURE[_cmd] = "giveaways"
for _cmd in ("embed", "emb"):
    _COMMAND_TO_FEATURE[_cmd] = "embeds"


def feature_for_command(name: str | None) -> Optional[str]:
    if not name:
        return None
    return _COMMAND_TO_FEATURE.get(name.strip().lower())


def feature_label(lang: GuildLang, feature: str) -> str:
    key = f"feat.{feature}"
    label = tr(lang, key)
    return label if label != key else feature.replace("_", " ").title()


def is_feature_allowed(
    *,
    guild_id: int | None,
    user_id: int,
    feature: str,
) -> bool:
    if guild_id is not None and not guild_config.is_feature_enabled(guild_id, feature):
        return False
    if feature in USER_FEATURE_KEYS and not user_settings.is_feature_enabled(user_id, feature):
        return False
    return True


def feature_denial_message(
    lang: GuildLang,
    feature: str,
    *,
    guild_id: int | None,
    user_id: int,
) -> str:
    label = feature_label(lang, feature)
    if guild_id is not None and not guild_config.is_feature_enabled(guild_id, feature):
        return tr(lang, "err.feature_disabled_guild", feature=label)
    if feature in USER_FEATURE_KEYS and not user_settings.is_feature_enabled(user_id, feature):
        return tr(lang, "err.feature_disabled_user", feature=label)
    return tr(lang, "err.feature_disabled_guild", feature=label)
