"""
Tiffany OS — Dynamic Runtime Configuration & Enterprise Feature Flag Evaluator
=============================================================================
Provides runtime zero-restart configuration management and granular feature flags
supporting percentage rollouts, canary groups, tier-based entitlements, and full
audit trail history for SOC 2 compliance.
"""

from __future__ import annotations
import asyncio
import hashlib
import logging
import time
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field

log = logging.getLogger("tiffany.core.config.runtime")

@dataclass
class ConfigAuditRecord:
    version: int
    key: str
    old_value: Any
    new_value: Any
    author_id: str
    reason: str
    timestamp_utc: float = field(default_factory=time.time)

class RuntimeConfigManager:
    """
    In-memory dynamic runtime configuration store. Allows adjusting circuit breaker
    thresholds, AI routing weights, and rate limits without process restarts.
    """
    def __init__(self) -> None:
        self._config: Dict[str, Any] = {
            "ai:max_tokens_per_minute": 50000,
            "ai:default_temperature": 0.5,
            "voice:interruption_ducking_level": 0.2,
            "reliability:circuit_breaker_failure_threshold": 5,
            "security:enforce_lgpd_scrubbing": True
        }
        self._audit_history: List[ConfigAuditRecord] = []
        self._version: int = 1
        self._lock = asyncio.Lock()

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    async def update_config(self, key: str, new_value: Any, author_id: str, reason: str) -> int:
        async with self._lock:
            old_value = self._config.get(key)
            if old_value == new_value:
                return self._version

            self._version += 1
            self._config[key] = new_value
            record = ConfigAuditRecord(
                version=self._version,
                key=key,
                old_value=old_value,
                new_value=new_value,
                author_id=author_id,
                reason=reason
            )
            self._audit_history.append(record)
            log.info("[RuntimeConfig] Updated '%s' (%s -> %s) [v%d] by %s: %s", 
                     key, old_value, new_value, self._version, author_id, reason)
            return self._version

    def get_audit_trail(self) -> List[ConfigAuditRecord]:
        return list(self._audit_history)


# =============================================================================
# Enterprise Feature Flag & Experimentation Evaluator
# =============================================================================

@dataclass
class FeatureFlagRule:
    flag_key: str
    enabled: bool = False
    percentage_rollout: int = 0  # 0 to 100
    enterprise_only: bool = False
    canary_guilds: Set[int] = field(default_factory=set)
    target_languages: Set[str] = field(default_factory=set)
    target_regions: Set[str] = field(default_factory=set)

class FeatureFlagEvaluator:
    """
    Evaluates progressive feature flags deterministically using consistent hashing
    over tenant or entity IDs to ensure stable user experiences during canary rollouts.
    """
    def __init__(self) -> None:
        self._flags: Dict[str, FeatureFlagRule] = {}

    def register_flag(self, rule: FeatureFlagRule) -> None:
        self._flags[rule.flag_key] = rule
        log.debug("[FeatureFlag] Registered flag '%s' (Enabled: %s, Rollout: %d%%)", 
                  rule.flag_key, rule.enabled, rule.percentage_rollout)

    def is_enabled(self, flag_key: str, entity_id: int, is_enterprise: bool = False, 
                   language: str = "pt", region: str = "br") -> bool:
        rule = self._flags.get(flag_key)
        if not rule or not rule.enabled:
            return False

        # Enterprise restriction check
        if rule.enterprise_only and not is_enterprise:
            return False

        # Canary explicit allow-list override
        if entity_id in rule.canary_guilds:
            return True

        # Language and region filtering
        if rule.target_languages and language.lower() not in rule.target_languages:
            return False
        if rule.target_regions and region.lower() not in rule.target_regions:
            return False

        # Deterministic percentage rollout via MD5 hashing on (flag_key + entity_id)
        if rule.percentage_rollout < 100:
            if rule.percentage_rollout <= 0:
                return False
            hash_str = f"{flag_key}:{entity_id}"
            digest = int(hashlib.md5(hash_str.encode("utf-8")).hexdigest()[:8], 16)
            bucket = (digest % 100) + 1  # 1 to 100
            return bucket <= rule.percentage_rollout

        return True

runtime_config = RuntimeConfigManager()
flag_evaluator = FeatureFlagEvaluator()
