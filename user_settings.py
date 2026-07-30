"""Per-user Tiffany preferences (feature opt-out, JSON persistence)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger("tiffany-bot")

_USER_FEATURE_KEYS = ("chat", "imagine", "roleplay", "games", "summary")

_SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_settings.json")
_cache: dict[str, dict[str, Any]] = {}
_loaded = False

_DEFAULT_USER_FEATURES = {key: True for key in _USER_FEATURE_KEYS}


def user_feature_keys() -> tuple[str, ...]:
    return _USER_FEATURE_KEYS


def _load() -> None:
    global _loaded, _cache
    if _loaded:
        return
    if os.path.exists(_SETTINGS_FILE):
        try:
            with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                _cache = json.load(f)
        except Exception as e:
            log.error("Failed to load user_settings.json: %s", e)
            _cache = {}
    _loaded = True


def _save() -> None:
    try:
        from infra.utils.json_utils import atomic_json_dump
        atomic_json_dump(_cache, _SETTINGS_FILE, indent=2)
    except Exception as e:
        log.error("Failed to save user_settings.json: %s", e)


def _ensure_features(raw: dict[str, Any] | None) -> dict[str, bool]:
    merged = dict(_DEFAULT_USER_FEATURES)
    if raw:
        for key in _USER_FEATURE_KEYS:
            if key in raw:
                merged[key] = bool(raw[key])
    return merged


def get_user_settings(user_id: int) -> dict[str, Any]:
    _load()
    uid = str(user_id)
    if uid not in _cache:
        _cache[uid] = {"features": dict(_DEFAULT_USER_FEATURES)}
    cfg = _cache[uid]
    cfg["features"] = _ensure_features(cfg.get("features"))
    return cfg


def save_user_settings(user_id: int, settings: dict[str, Any]) -> None:
    _load()
    settings["features"] = _ensure_features(settings.get("features"))
    _cache[str(user_id)] = settings
    _save()


def get_user_features(user_id: int) -> dict[str, bool]:
    return get_user_settings(user_id)["features"]


def is_feature_enabled(user_id: int, feature: str) -> bool:
    if feature not in _USER_FEATURE_KEYS:
        return True
    return bool(get_user_features(user_id).get(feature, True))


def set_feature_enabled(user_id: int, feature: str, enabled: bool) -> None:
    if feature not in _USER_FEATURE_KEYS:
        return
    cfg = get_user_settings(user_id)
    cfg["features"][feature] = bool(enabled)
    save_user_settings(user_id, cfg)


def toggle_feature(user_id: int, feature: str) -> bool:
    current = is_feature_enabled(user_id, feature)
    set_feature_enabled(user_id, feature, not current)
    return not current
