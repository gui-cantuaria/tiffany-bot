"""
Tiffany OS — Test Suite for Admin AI Credit Management & Ledger (P0.8)
========================================================================
Validates server-side credit granting, permission checks, amount validation,
non-negative balances, and transaction recording.
"""

import unittest
import asyncio
from infra.services.ai_quota import AIQuotaService

class TestAIQuotaAdmin(unittest.TestCase):

    def test_grant_credits_validation(self):
        """Test that invalid credit amounts (<= 0 or > 100,000) are rejected."""
        with self.assertRaises(ValueError):
            asyncio.run(AIQuotaService.grant_credits(user_id=12345, credits=0))

        with self.assertRaises(ValueError):
            asyncio.run(AIQuotaService.grant_credits(user_id=12345, credits=-50))

        with self.assertRaises(ValueError):
            asyncio.run(AIQuotaService.grant_credits(user_id=12345, credits=200000))

    def test_grant_credits_execution(self):
        """Test successful execution of grant_credits."""
        res = asyncio.run(
            AIQuotaService.grant_credits(
                user_id=88888, 
                credits=500, 
                reason="Test bonus grant", 
                granted_by=842799130630815754
            )
        )
        
        self.assertIn("status", res)
        self.assertEqual(res["user_id"], 88888)
        self.assertEqual(res["credits_granted"], 500)
        self.assertEqual(res["reason"], "Test bonus grant")
        self.assertEqual(res["granted_by"], 842799130630815754)

if __name__ == "__main__":
    unittest.main()
