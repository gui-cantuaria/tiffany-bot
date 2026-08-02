"""Integration test gate — FAIL (never skip) if real infra is unavailable."""

from __future__ import annotations

import asyncio
import os
from typing import Any, AsyncIterator, Callable, Coroutine, TypeVar

import pytest

T = TypeVar("T")

DEFAULT_PG_URL = (
    "postgresql://tiffany_test:tiffany_test@127.0.0.1:5433/tiffany_test?ssl=disable"
)
DEFAULT_REDIS_URL = "redis://127.0.0.1:6380/0"


def _integration_enabled() -> bool:
    return os.getenv("TIFFANY_INTEGRATION_TESTS", "").strip().lower() in ("1", "true", "yes")


def run_async(loop: asyncio.AbstractEventLoop, coro: Coroutine[Any, Any, T]) -> T:
    """Run coroutine on the session event loop (asyncpg pool is loop-bound)."""
    return loop.run_until_complete(coro)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: real PostgreSQL/Redis infrastructure tests (Phase XII)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not _integration_enabled():
        for item in items:
            if "integration" in str(item.fspath):
                item.add_marker(
                    pytest.mark.skip(
                        reason="Set TIFFANY_INTEGRATION_TESTS=1 to run integration tests",
                    )
                )


@pytest.fixture(scope="session")
def event_loop() -> AsyncIterator[asyncio.AbstractEventLoop]:
    """Single session event loop — required for asyncpg pool + Redis client."""
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.run_until_complete(_shutdown_all())
    loop.close()


@pytest.fixture(scope="session")
def integration_env(event_loop: asyncio.AbstractEventLoop) -> dict[str, str]:
    if not _integration_enabled():
        pytest.fail(
            "TIFFANY_INTEGRATION_TESTS=1 required. Start infra: "
            "docker compose -f docker-compose.integration.yml up -d"
        )
    pg_url = os.getenv("INTEGRATION_DATABASE_URL", DEFAULT_PG_URL)
    redis_url = os.getenv("INTEGRATION_REDIS_URL", DEFAULT_REDIS_URL)
    os.environ["DATABASE_URL"] = pg_url
    os.environ["REDIS_URL"] = redis_url
    os.environ["INTEGRATION_DATABASE_URL"] = pg_url
    os.environ["INTEGRATION_REDIS_URL"] = redis_url
    return {"pg_url": pg_url, "redis_url": redis_url}


@pytest.fixture(scope="session")
def pg_pool(integration_env: dict[str, str], event_loop: asyncio.AbstractEventLoop):
    async def _boot():
        from infra import postgres

        await postgres.init_db()
        pool = postgres.pool()
        if pool is None:
            raise RuntimeError("PostgreSQL pool failed to initialize — is Docker running?")
        await pool.fetchval("SELECT 1")
        await postgres.run_migrations()
        ver = await pool.fetchval("SHOW server_version")
        return pool, ver

    try:
        pool, version = run_async(event_loop, _boot())
    except Exception as exc:
        pytest.fail(f"Real PostgreSQL unavailable: {exc}")
    yield pool, version


@pytest.fixture(scope="session")
def redis_client(integration_env: dict[str, str], event_loop: asyncio.AbstractEventLoop):
    async def _boot():
        from infra import redis_client as rc

        await rc.init_redis()
        if rc._redis is None:
            raise RuntimeError(
                "Redis client not connected — memory fallback active; "
                "integration tests require real Redis",
            )
        pong = await rc._redis.ping()
        info = await rc._redis.info("server")
        return pong, info.get("redis_version", "?")

    try:
        pong, version = run_async(event_loop, _boot())
    except Exception as exc:
        pytest.fail(f"Real Redis unavailable: {exc}")
    assert pong is True
    yield version


@pytest.fixture(autouse=True)
def clean_payment_tables(pg_pool, event_loop: asyncio.AbstractEventLoop):
    pool, _ = pg_pool

    async def _truncate():
        await pool.execute("TRUNCATE payment_outbox")
        await pool.execute("TRUNCATE stripe_events CASCADE")

    run_async(event_loop, _truncate())
    yield
    run_async(event_loop, _truncate())


async def _shutdown_all() -> None:
    from infra import postgres
    from infra import redis_client as rc

    try:
        await rc.close_redis()
    except Exception:
        pass
    try:
        await postgres.close_db()
    except Exception:
        pass
