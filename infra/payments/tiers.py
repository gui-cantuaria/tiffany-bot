"""Tier resolution — fail closed, no premium fallback grants."""

from __future__ import annotations

import logging
from typing import Optional

from infra.payments.constants import PAID_PACKAGE_TIERS, VALID_TIERS
from infra.payments.metrics import inc

log = logging.getLogger("tiffany.payments.tiers")


class UnknownTierError(ValueError):
    """Raised when Stripe price or metadata cannot map to a known tier."""


class UnknownPriceError(ValueError):
    """Raised when price_id is not in STRIPE_PRICE_MAP."""


def resolve_tier(
    *,
    price_id: Optional[str],
    metadata_package: Optional[str],
    price_to_tier: dict[str, str],
) -> str:
    """
    Resolve internal tier from checkout metadata or configured price map.
    Never falls back to a generic premium grant.
    Prioritizes verified Stripe price_id to prevent metadata spoofing.
    """
    pid = (price_id or "").strip()
    if pid and pid in price_to_tier:
        tier = price_to_tier[pid]
        if tier not in VALID_TIERS:
            inc("tier_rejected_unknown")
            raise UnknownPriceError(f"Mapped tier '{tier}' not in VALID_TIERS")
        pkg = (metadata_package or "").strip().lower()
        if pkg and pkg in VALID_TIERS and pkg != tier:
            log.warning("Metadata package '%s' contradicts price_id tier '%s' — enforcing paid price tier", pkg, tier)
        return tier

    pkg = (metadata_package or "").strip().lower()
    if pkg:
        if pkg not in VALID_TIERS:
            inc("tier_rejected_unknown")
            raise UnknownTierError(f"Unknown metadata package: {pkg}")
        return pkg

    if not pid:
        inc("tier_rejected_unknown")
        raise UnknownPriceError("Missing price_id and package metadata")

    tier = price_to_tier.get(pid)
    if not tier or tier not in VALID_TIERS:
        inc("tier_rejected_unknown")
        raise UnknownPriceError(f"Unknown Stripe price_id (not in STRIPE_PRICE_MAP)")
    return tier


def validate_discord_metadata(meta: dict) -> tuple[str, int, int]:
    """Validate and parse Discord subject from Stripe checkout metadata."""
    subject_type = str(meta.get("subject_type", "guild")).strip().lower()
    if subject_type not in ("guild", "user"):
        inc("metadata_rejected")
        raise ValueError("Invalid subject_type in checkout metadata")

    try:
        guild_id = int(str(meta.get("discord_guild_id", "0")).strip() or "0")
        user_id = int(str(meta.get("discord_user_id", "0")).strip() or "0")
    except (TypeError, ValueError) as exc:
        inc("metadata_rejected")
        raise ValueError("Invalid discord id in checkout metadata") from exc

    if subject_type == "guild":
        if guild_id <= 0:
            inc("metadata_rejected")
            raise ValueError("Missing discord_guild_id in checkout metadata")
        if user_id <= 0:
            inc("metadata_rejected")
            raise ValueError("Missing discord_user_id in checkout metadata")
        return "guild", guild_id, user_id

    if user_id <= 0:
        inc("metadata_rejected")
        raise ValueError("Missing discord_user_id in checkout metadata")
    return "user", user_id, user_id
