"""Real Redis validation — Phase XII (requires Docker)."""

from __future__ import annotations

import pytest

from infra import premium
from infra import redis_client as rc
from tests.integration.conftest import run_async


@pytest.mark.integration
class TestRedisBasics:
    def test_ping_and_version(self, redis_client):
        assert redis_client

    def test_cache_set_get_delete(self, pg_pool, redis_client, event_loop):
        async def _run():
            await rc.cache_setex("phase12:probe", 30, "ok")
            val = await rc.cache_get("phase12:probe")
            assert val == "ok"
            await rc.cache_delete("phase12:probe")
            assert await rc.cache_get("phase12:probe") is None

        run_async(event_loop, _run())

    def test_entitlement_invalidation_real_redis(self, pg_pool, redis_client, event_loop):
        async def _run():
            key = "ent:g:999001"
            await rc.cache_setex(key, 300, '{"tier":"ultimate"}')
            assert await rc.cache_get(key) is not None
            await premium.invalidate_entitlement(guild_id=999001)
            assert await rc.cache_get(key) is None
            await premium.invalidate_entitlement(guild_id=999001)

        run_async(event_loop, _run())

    def test_reconnect_after_client_close(self, redis_client, event_loop):
        async def _run():
            await rc.cache_setex("phase12:reconnect", 30, "v1")
            await rc.close_redis()
            await rc.init_redis()
            assert rc._redis is not None
            val = await rc.cache_get("phase12:reconnect")
            assert val == "v1"
            await rc.cache_delete("phase12:reconnect")

        run_async(event_loop, _run())

    def test_memory_fallback_disabled_when_redis_up(self, redis_client):
        assert rc._USE_MEMORY is False
