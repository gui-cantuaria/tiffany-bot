"""
Tiffany OS — Targeted Behavioral Verification Suite for Stripe Webhook Rate Limiter
====================================================================================
Validates all 5 mandatory failure modes:
1. Proxy Spoofing Defense & Trusted Proxy Parsing (Test A)
2. Ingress Rate Limiting & HTTP 429 Isolation (Test B)
3. Redis Outage Fail-Open Resilience (Test C)
4. Concurrent Increment Atomicity (Test D)
5. Fixed TTL Window Expiration Bounds (Test E)
"""

import os
import sys
import unittest
import asyncio
import time
from unittest.mock import MagicMock, patch

from aiohttp import web
from infra.stripe_server import get_client_ip, _stripe_webhook_handler_inner, STRIPE_TRUSTED_PROXIES
from infra import redis_client


class TestStripeRateLimitingBehavior(unittest.TestCase):

    # ---------------------------------------------------------------------------
    # TEST A: PROXY SPOOFING DEFENSE
    # ---------------------------------------------------------------------------
    def test_proxy_spoofing_untrusted_remote(self):
        """Forged X-Forwarded-For header from untrusted peer must be ignored."""
        req = MagicMock()
        req.remote = "198.51.100.42"
        req.headers = {"X-Forwarded-For": "203.0.113.199, 10.0.0.1"}
        client_ip = get_client_ip(req)
        self.assertEqual(client_ip, "198.51.100.42", "Security Failure: Spoofed X-Forwarded-For header was trusted!")

    def test_proxy_spoofing_trusted_proxy_single_ip(self):
        """X-Forwarded-For header from trusted proxy must return forwarded client IP."""
        req = MagicMock()
        req.remote = "127.0.0.1"
        req.headers = {"X-Forwarded-For": "203.0.113.199"}
        client_ip = get_client_ip(req)
        self.assertEqual(client_ip, "203.0.113.199")

    def test_proxy_spoofing_trusted_proxy_multiple_ips(self):
        """X-Forwarded-For with chain of IPs from trusted proxy must extract leftmost client IP."""
        req = MagicMock()
        req.remote = "127.0.0.1"
        req.headers = {"X-Forwarded-For": "203.0.113.199, 10.0.0.1, 172.16.0.1"}
        client_ip = get_client_ip(req)
        self.assertEqual(client_ip, "203.0.113.199", "Failed to extract leftmost client IP from chain")

    # ---------------------------------------------------------------------------
    # TEST B: RATE LIMIT BEHAVIOR & HTTP 429 ISOLATION
    # ---------------------------------------------------------------------------
    def test_rate_limit_behavior_threshold_and_isolation(self):
        """Verify requests below limit pass, requests above limit return HTTP 429, and limits are IP-isolated."""
        async def run_test():
            test_ip_1 = f"203.0.113.{int(time.time()) % 200 + 1}"
            test_ip_2 = f"203.0.113.{int(time.time()) % 200 + 20}"

            # 1. First 2 requests for test_ip_1 are accepted
            c1 = await redis_client.cache_incr(f"ratelimit:webhook:{test_ip_1}", ttl_sec=60)
            c2 = await redis_client.cache_incr(f"ratelimit:webhook:{test_ip_1}", ttl_sec=60)
            self.assertEqual(c1, 1)
            self.assertEqual(c2, 2)

            # 2. Verify IP isolation: test_ip_2 counter starts independently at 1
            c_ip2 = await redis_client.cache_incr(f"ratelimit:webhook:{test_ip_2}", ttl_sec=60)
            self.assertEqual(c_ip2, 1, "Rate limit counter was not isolated per IP!")

            # 3. Simulate HTTP 429 response when threshold is exceeded in handler
            with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_test", "STRIPE_WEBHOOK_RATE_LIMIT": "2"}):
                req = MagicMock()
                req.remote = "127.0.0.1"
                req.headers = {"X-Forwarded-For": test_ip_1}
                resp = await _stripe_webhook_handler_inner(req)
                self.assertEqual(resp.status, 429, "Exceeded rate limit did not return HTTP 429!")

        asyncio.run(run_test())

    # ---------------------------------------------------------------------------
    # TEST C: REDIS FAILURE / FAIL-OPEN RESILIENCE
    # ---------------------------------------------------------------------------
    def test_redis_failure_fail_open(self):
        """Simulate Redis outage during rate limit check: request must Fail Open (not crash or return 429)."""
        async def run_test():
            with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_test"}):
                with patch.object(redis_client, "cache_incr", side_effect=RuntimeError("Redis connection lost")):
                    req = MagicMock()
                    req.remote = "127.0.0.1"
                    req.headers = {}
                    resp = await _stripe_webhook_handler_inner(req)
                    self.assertNotEqual(resp.status, 429, "Redis error caused rate limiter to block request!")
                    self.assertIn(resp.status, (400, 503, 500), "Fail open did not proceed to webhook verification")

        asyncio.run(run_test())

    # ---------------------------------------------------------------------------
    # TEST D: ATOMICITY & CONCURRENCY
    # ---------------------------------------------------------------------------
    def test_concurrency_atomicity(self):
        """Verify 50 concurrent cache_incr calls increment counter accurately without lost updates."""
        async def run_concurrent():
            import uuid
            key = f"ratelimit:concurrency_test:{uuid.uuid4().hex}"
            tasks = [redis_client.cache_incr(key, ttl_sec=60) for _ in range(50)]
            results = await asyncio.gather(*tasks)
            final_count = await redis_client.cache_get(key)
            return results, int(final_count or 0)

        results, final_val = asyncio.run(run_concurrent())
        self.assertEqual(final_val, 50, f"Concurrency update lost! Expected 50, got {final_val}")
        self.assertEqual(max(results), 50)

    # ---------------------------------------------------------------------------
    # TEST E: FIXED TTL WINDOW BOUNDS
    # ---------------------------------------------------------------------------
    def test_fixed_ttl_window_not_extended(self):
        """Verify repeated increments preserve the original expiration timestamp and do not extend TTL."""
        async def run_ttl_test():
            import uuid
            key = f"ratelimit:ttl_test:{uuid.uuid4().hex}"
            
            # Initial increment with 10s TTL
            await redis_client.cache_incr(key, ttl_sec=10)
            initial_exp = redis_client._memory[key][1]

            # Perform 20 fast increments
            for _ in range(20):
                await redis_client.cache_incr(key, ttl_sec=10)

            subsequent_exp = redis_client._memory[key][1]
            self.assertEqual(initial_exp, subsequent_exp, "Defect: Repeated increments extended the TTL window!")

        asyncio.run(run_ttl_test())


if __name__ == "__main__":
    unittest.main()
