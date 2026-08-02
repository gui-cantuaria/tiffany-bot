"""Outbox worker subprocess — used by multiprocess integration tests."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

# Repo root on sys.path — subprocess cwd may be ROOT but script dir is on sys.path[0].
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


async def _main(worker_id: str, mode: str, batch_limit: int) -> dict:
    from infra import postgres
    from infra.payments import outbox as outbox_mod
    from infra.payments.constants import OUTBOX_LEASE_SEC

    await postgres.init_db()
    pool = postgres.pool()
    if pool is None:
        raise RuntimeError("PostgreSQL pool unavailable")

    if mode == "recover":
        async with pool.acquire() as conn:
            n = await outbox_mod.recover_stale_leases(conn, stale_sec=0)
        await postgres.close_db()
        return {"worker_id": worker_id, "recovered": n}

    # Short lease so killed/hung workers become stale quickly in integration tests.
    lease_sec = 1 if mode == "claim_and_hang" else OUTBOX_LEASE_SEC
    claimed_ids: list[str] = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await outbox_mod.claim_batch(
                conn,
                worker_id=worker_id,
                limit=batch_limit,
                lease_sec=lease_sec,
            )
            for row in rows:
                claimed_ids.append(str(row["id"]))

    if mode == "claim_and_hang" and claimed_ids:
        await asyncio.sleep(3600)

    if mode == "claim_and_deliver" and claimed_ids:
        for row_id in claimed_ids:
            async with pool.acquire() as conn:
                await outbox_mod.mark_delivered(
                    conn, uuid.UUID(row_id), lease_owner=worker_id,
                )

    await postgres.close_db()
    return {"worker_id": worker_id, "claimed": claimed_ids, "count": len(claimed_ids)}


if __name__ == "__main__":
    worker = sys.argv[1] if len(sys.argv) > 1 else "worker-0"
    run_mode = sys.argv[2] if len(sys.argv) > 2 else "claim"
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 50
    os.environ.setdefault(
        "DATABASE_URL",
        os.environ.get(
            "INTEGRATION_DATABASE_URL",
            "postgresql://tiffany_test:tiffany_test@127.0.0.1:5433/tiffany_test?ssl=disable",
        ),
    )
    result = asyncio.run(_main(worker, run_mode, limit))
    print(json.dumps(result))
