"""Real PostgreSQL 16 validation — Phase XII (requires Docker)."""

from __future__ import annotations

import uuid

import pytest

from infra.payments import outbox as outbox_mod
from infra.payments.constants import OUTBOX_DELIVERED, OUTBOX_PENDING, OUTBOX_PROCESSING
from tests.integration.conftest import run_async


@pytest.mark.integration
class TestPostgresBasics:
    def test_pool_and_migrations(self, pg_pool):
        pool, version = pg_pool
        assert pool is not None
        assert "16" in str(version)

    def test_transaction_commit_rollback(self, pg_pool, event_loop):
        pool, _ = pg_pool

        async def _run():
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "CREATE TEMP TABLE IF NOT EXISTS _tx_probe (id int PRIMARY KEY)"
                    )
                    await conn.execute("INSERT INTO _tx_probe VALUES (1)")
                n = await conn.fetchval("SELECT count(*) FROM _tx_probe")
                assert n == 1
            async with pool.acquire() as conn2:
                async with conn2.transaction():
                    await conn2.execute(
                        "CREATE TEMP TABLE IF NOT EXISTS _tx_probe2 (id int PRIMARY KEY)"
                    )
                    await conn2.execute("INSERT INTO _tx_probe2 VALUES (1)")
                    raise RuntimeError("force rollback")

        with pytest.raises(RuntimeError):
            run_async(event_loop, _run())

    def test_skip_locked_two_sessions(self, pg_pool, event_loop):
        pool, _ = pg_pool
        row_id = uuid.uuid4()

        async def _run():
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO payment_outbox (id, delivery_type, payload, status)
                    VALUES ($1, 'discord_notify', '{}'::jsonb, $2)
                    """,
                    row_id,
                    OUTBOX_PENDING,
                )

            async def _claim(worker_id: str) -> int:
                async with pool.acquire() as conn:
                    async with conn.transaction():
                        rows = await outbox_mod.claim_batch(
                            conn, worker_id=worker_id, limit=1,
                        )
                        return len(rows)

            c1 = await _claim("worker-a")
            c2 = await _claim("worker-b")
            status = await pool.fetchval(
                "SELECT status FROM payment_outbox WHERE id = $1", row_id,
            )
            owner = await pool.fetchval(
                "SELECT lease_owner FROM payment_outbox WHERE id = $1", row_id,
            )
            return [c1, c2], status, owner

        claims, status, owner = run_async(event_loop, _run())
        assert sorted(claims) == [0, 1]
        assert status == OUTBOX_PROCESSING
        assert owner in ("worker-a", "worker-b")

    def test_lease_guarded_mark_delivered(self, pg_pool, event_loop):
        pool, _ = pg_pool
        row_id = uuid.uuid4()

        async def _run():
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO payment_outbox (id, delivery_type, payload, status)
                    VALUES ($1, 'discord_notify', '{}'::jsonb, $2)
                    """,
                    row_id,
                    OUTBOX_PENDING,
                )
            async with pool.acquire() as conn:
                async with conn.transaction():
                    claimed = await outbox_mod.claim_batch(
                        conn, worker_id="owner-a", limit=1,
                    )
            assert len(claimed) == 1
            async with pool.acquire() as conn:
                bad = await outbox_mod.mark_delivered(conn, row_id, lease_owner="owner-b")
                good = await outbox_mod.mark_delivered(conn, row_id, lease_owner="owner-a")
            status = await pool.fetchval(
                "SELECT status FROM payment_outbox WHERE id = $1", row_id,
            )
            return bad, good, status

        bad, good, status = run_async(event_loop, _run())
        assert bad is False
        assert good is True
        assert status == OUTBOX_DELIVERED

    def test_stale_lease_recovery(self, pg_pool, event_loop):
        pool, _ = pg_pool
        row_id = uuid.uuid4()

        async def _run():
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO payment_outbox (
                        id, delivery_type, payload, status,
                        lease_owner, lease_until, attempt_count
                    ) VALUES (
                        $1, 'discord_notify', '{}'::jsonb, $2,
                        'dead-worker', now() - interval '10 minutes', 1
                    )
                    """,
                    row_id,
                    OUTBOX_PROCESSING,
                )
                n = await outbox_mod.recover_stale_leases(conn, stale_sec=0)
            status = await pool.fetchval(
                "SELECT status FROM payment_outbox WHERE id = $1", row_id,
            )
            return n, status

        n, status = run_async(event_loop, _run())
        assert n >= 1
        assert status == OUTBOX_PENDING
