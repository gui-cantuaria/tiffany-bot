"""Tiffany Payments Phase III — adversarial and correctness tests (no network)."""

from __future__ import annotations

import unittest

from infra.payments.constants import REVOKE_SUBSCRIPTION_STATUSES, VALID_TIERS
from infra.payments.metrics import inc, payment_metrics_snapshot
from infra.payments.tiers import UnknownPriceError, UnknownTierError, resolve_tier, validate_discord_metadata


class TestTierResolution(unittest.TestCase):
    PRICE_MAP = {"price_offers_123": "offers", "price_ultimate_456": "ultimate"}

    def test_resolve_from_metadata_package(self):
        tier = resolve_tier(
            price_id=None,
            metadata_package="ultimate",
            price_to_tier=self.PRICE_MAP,
        )
        self.assertEqual(tier, "ultimate")

    def test_resolve_from_price_map(self):
        tier = resolve_tier(
            price_id="price_offers_123",
            metadata_package=None,
            price_to_tier=self.PRICE_MAP,
        )
        self.assertEqual(tier, "offers")

    def test_reject_unknown_price(self):
        with self.assertRaises(UnknownPriceError):
            resolve_tier(
                price_id="price_unknown",
                metadata_package=None,
                price_to_tier=self.PRICE_MAP,
            )

    def test_reject_unknown_metadata_package(self):
        with self.assertRaises(UnknownTierError):
            resolve_tier(
                price_id=None,
                metadata_package="super_mega_tier",
                price_to_tier=self.PRICE_MAP,
            )

    def test_no_premium_fallback(self):
        with self.assertRaises(UnknownPriceError):
            resolve_tier(price_id="", metadata_package="", price_to_tier=self.PRICE_MAP)


class TestMetadataValidation(unittest.TestCase):
    def test_valid_guild_metadata(self):
        st, sid, purchaser = validate_discord_metadata({
            "subject_type": "guild",
            "discord_guild_id": "123456789012345678",
            "discord_user_id": "987654321098765432",
        })
        self.assertEqual(st, "guild")
        self.assertEqual(sid, 123456789012345678)

    def test_reject_missing_guild_id(self):
        with self.assertRaises(ValueError):
            validate_discord_metadata({"subject_type": "guild", "discord_user_id": "123"})

    def test_reject_forged_subject_type(self):
        with self.assertRaises(ValueError):
            validate_discord_metadata({"subject_type": "admin", "discord_guild_id": "1"})

    def test_reject_non_numeric_ids(self):
        with self.assertRaises(ValueError):
            validate_discord_metadata({
                "subject_type": "guild",
                "discord_guild_id": "not-a-snowflake",
                "discord_user_id": "123",
            })


class TestSubscriptionRevokePolicy(unittest.TestCase):
    def test_past_due_not_in_revoke_set(self):
        self.assertNotIn("past_due", REVOKE_SUBSCRIPTION_STATUSES)

    def test_canceled_in_revoke_set(self):
        self.assertIn("canceled", REVOKE_SUBSCRIPTION_STATUSES)


class TestMetrics(unittest.TestCase):
    def test_metrics_increment_real_counters(self):
        before = payment_metrics_snapshot().get("tier_rejected_unknown", 0)
        inc("tier_rejected_unknown")
        after = payment_metrics_snapshot().get("tier_rejected_unknown", 0)
        self.assertEqual(after, before + 1)


class TestValidTiers(unittest.TestCase):
    def test_all_paid_packages_in_valid_tiers(self):
        for tier in ("offers", "news", "ultimate", "premium", "premium_plus"):
            self.assertIn(tier, VALID_TIERS)


if __name__ == "__main__":
    unittest.main()
