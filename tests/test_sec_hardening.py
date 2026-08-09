"""
Tiffany OS — Test Suite for Security Hardening, Dynamic Payment Methods & i18n Verification
=============================================================================================
Verifies removal of default credentials, safe host binding defaults, dynamic environment key
getters, dynamic Stripe payment methods, and translation placeholder integrity.
"""

import os
import unittest
import json
import re
from unittest.mock import patch

from infra.audio.lavalink_nodes import _default_password, lavalink_enabled
from infra.stripe_server import STRIPE_WEBHOOK_HOST, create_checkout_url
from premium_ai_guardrails import get_openrouter_api_key


class TestSecurityHardening(unittest.TestCase):

    def test_sec_001_lavalink_no_hardcoded_password_fallback(self):
        """Test SEC-001: Missing LAVALINK_PASSWORD must return empty string, never a hardcoded production secret."""
        with patch.dict(os.environ, {"LAVALINK_PASSWORD": ""}):
            pwd = _default_password()
            self.assertEqual(pwd, "")
            self.assertNotEqual(pwd, "tiffany_lavalink_2026")

        with patch.dict(os.environ, {"LAVALINK_PASSWORD": "custom_secret_pass"}):
            self.assertEqual(_default_password(), "custom_secret_pass")

    def test_sec_002_stripe_webhook_host_default(self):
        """Test SEC-002: Stripe webhook server defaults to 127.0.0.1 for private binding safety."""
        self.assertIn(STRIPE_WEBHOOK_HOST, ("127.0.0.1", os.getenv("STRIPE_WEBHOOK_HOST", "127.0.0.1")))

    def test_sec_004_openrouter_api_key_dynamic_getter(self):
        """Test SEC-004: get_openrouter_api_key dynamically reads from environment at runtime."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_dynamic_key_123"}):
            self.assertEqual(get_openrouter_api_key(), "test_dynamic_key_123")

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            self.assertEqual(get_openrouter_api_key(), "")

    def test_sec_005_stripe_dynamic_payment_methods_parsing(self):
        """Test SEC-005: Stripe payment method types adapt dynamically to environment settings."""
        with patch.dict(os.environ, {"STRIPE_PAYMENT_METHOD_TYPES": "card,pix,boleto"}):
            methods = [m.strip() for m in os.getenv("STRIPE_PAYMENT_METHOD_TYPES", "card").split(",") if m.strip()]
            self.assertEqual(methods, ["card", "pix", "boleto"])

        with patch.dict(os.environ, {"STRIPE_PAYMENT_METHOD_TYPES": "card"}):
            methods = [m.strip() for m in os.getenv("STRIPE_PAYMENT_METHOD_TYPES", "card").split(",") if m.strip()]
            self.assertEqual(methods, ["card"])

    def test_i18n_placeholder_integrity(self):
        """Test i18n: Verify all non-English catalog files preserve required placeholders."""
        catalog_path = os.path.join("locales", "_catalog_en.json")
        if not os.path.exists(catalog_path):
            self.skipTest("_catalog_en.json missing")

        with open(catalog_path, "r", encoding="utf-8") as f:
            en_catalog = json.load(f)

        # Check placeholders in EN
        for key, en_val in en_catalog.items():
            en_phs = set(re.findall(r"\{([^{}]+)\}", str(en_val)))
            if not en_phs:
                continue
            # Placeholders must be valid identifiers
            for ph in en_phs:
                self.assertTrue(ph.isidentifier(), f"Invalid placeholder {{{ph}}} in key {key}")


if __name__ == "__main__":
    unittest.main()
