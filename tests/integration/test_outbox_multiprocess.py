"""Real outbox multiprocess concurrency — Phase XII."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from infra.payments import outbox as outbox_mod
from infra.payments.constants import OUTBOX_DELIVERED, OUTBOX_PENDING, OUTBOX_PROCESSING
from tests.integration.conftest import run_async

ROOT = Path(__file__).resolve().parents[2]
WORKER_SCRIPT = ROOT / "scripts" / "integration_outbox_worker.py"


def _run_worker(worker_id: str, mode: str = "claim", limit: int = 50) -> dict:
    env = os.environ.copy()
    env["DATABASE_URL"] = env.get("INTEGRATION_DATABASE_URL", env["DATABASE_URL"])
    proc = subprocess.run(
        [sys.executable, str(WORKER_SCRIPT), worker_id, mode, str(limit)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        cwd=str(ROOT),
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Worker {worker_id} failed rc={proc.returncode} stderr={proc.stderr[:500]}"
        )
    line = proc.stdout.strip().splitlines()[-1]
    return json.loads(line)


@pytest.mark.integration
class TestOutboxMultiprocess:
    def test_three_workers_claim_30_rows_exclusively(self, pg_pool, event_loop):
        pool, _ = pg_pool

        async def _seed():
            async with pool.acquire() as conn:
                for _ in range(30):
                    await conn.execute(
                        """
                        INSERT INTO payment_outbox (id, delivery_type, payload, status)
                        VALUES ($1, 'discord_notify', '{"kind":"premium_activated"}'::jsonb, $2)
                        """,
                        uuid.uuid4(),
                        OUTBOX_PENDING,
                    )

        run_async(event_loop, _seed())

        results = [
            _run_worker("proc-a", limit=15),
            _run_worker("proc-b", limit=15),
            _run_worker("proc-c", limit=15),
        ]
        all_claimed: list[str] = []
        for r in results:
            all_claimed.extend(r["claimed"])
        assert len(all_claimed) == len(set(all_claimed)), "duplicate claim detected"
        assert len(all_claimed) == 30

        async def _verify():
            processing = await pool.fetchval(
                "SELECT count(*)::int FROM payment_outbox WHERE status = $1",
                OUTBOX_PROCESSING,
            )
            pending = await pool.fetchval(
                "SELECT count(*)::int FROM payment_outbox WHERE status = $1",
                OUTBOX_PENDING,
            )
            return processing, pending

        processing, pending = run_async(event_loop, _verify())
        assert processing == 30
        assert pending == 0

    def test_crash_hang_then_stale_reclaim(self, pg_pool, event_loop):
        pool, _ = pg_pool
        row_id = uuid.uuid4()

        async def _seed():
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO payment_outbox (id, delivery_type, payload, status)
                    VALUES ($1, 'discord_notify', '{}'::jsonb, $2)
                    """,
                    row_id,
                    OUTBOX_PENDING,
                )

        run_async(event_loop, _seed())

        env = os.environ.copy()
        env["DATABASE_URL"] = env.get("INTEGRATION_DATABASE_URL", env["DATABASE_URL"])
        hang = subprocess.Popen(
            [sys.executable, str(WORKER_SCRIPT), "hang-worker", "claim_and_hang", "1"],
            env=env,
            cwd=str(ROOT),
        )
        try:
            time.sleep(2)
            async def _status():
                return await pool.fetchval(
                    "SELECT status FROM payment_outbox WHERE id = $1", row_id,
                )

            status = run_async(event_loop, _status())
            assert status == OUTBOX_PROCESSING
            hang.kill()
            hang.wait(timeout=5)
            recovered = _run_worker("recover-worker", mode="recover")
            assert recovered.get("recovered", 0) >= 1
            second = _run_worker("proc-b", limit=1)
            assert str(row_id) in second["claimed"]

            async def _deliver():
                async with pool.acquire() as conn:
                    return await outbox_mod.mark_delivered(
                        conn, row_id, lease_owner="proc-b",
                    )

            assert run_async(event_loop, _deliver()) is True
        finally:
            if hang.poll() is None:
                hang.kill()

        async def _final():
            return await pool.fetchval(
                "SELECT status FROM payment_outbox WHERE id = $1", row_id,
            )

        final = run_async(event_loop, _final())
        assert final == OUTBOX_DELIVERED

    def test_original_owner_cannot_mark_after_reclaim(self, pg_pool, event_loop):
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
                    await outbox_mod.claim_batch(conn, worker_id="original", limit=1)
                await conn.execute(
                    "UPDATE payment_outbox SET lease_until = now() - interval '1 hour' WHERE id = $1",
                    row_id,
                )
            async with pool.acquire() as conn:
                await outbox_mod.recover_stale_leases(conn, stale_sec=0)
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await outbox_mod.claim_batch(conn, worker_id="new-owner", limit=1)
            async with pool.acquire() as conn:
                bad = await outbox_mod.mark_delivered(conn, row_id, lease_owner="original")
                good = await outbox_mod.mark_delivered(conn, row_id, lease_owner="new-owner")
            return bad, good

        bad, good = run_async(event_loop, _run())
        assert bad is False
        assert good is True
