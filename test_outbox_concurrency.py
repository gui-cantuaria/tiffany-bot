"""Phase XI — outbox lease/claim concurrency tests (in-memory, no production services)."""

from __future__ import annotations

import uuid
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from infra.payments.constants import (
    MAX_OUTBOX_ATTEMPTS,
    OUTBOX_DEAD_LETTER,
    OUTBOX_DELIVERED,
    OUTBOX_PENDING,
    OUTBOX_PROCESSING,
)
from infra.payments import outbox as outbox_mod


def _row(**kwargs: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "delivery_type": "discord_notify",
        "payload": {"kind": "premium_activated", "guild_id": 1},
        "attempt_count": 0,
        "provider_event_id": "evt_1",
        "correlation_id": None,
        "trace_id": "t",
        "status": OUTBOX_PENDING,
        "lease_owner": None,
        "lease_until": None,
        "next_retry_at": datetime.now(timezone.utc),
        "last_error": None,
    }
    defaults.update(kwargs)
    return defaults


class _FakeTx:
    def __init__(self, conn: "_FakeConn") -> None:
        self._conn = conn

    async def __aenter__(self) -> "_FakeConn":
        self._conn.in_tx = True
        return self._conn

    async def __aexit__(self, *a: Any) -> None:
        self._conn.in_tx = False


class _FakeConn:
    """Minimal asyncpg-like conn for outbox lease operations."""

    def __init__(self, rows: dict[uuid.UUID, dict[str, Any]]) -> None:
        self.rows = rows
        self.in_tx = False

    def transaction(self) -> _FakeTx:
        return _FakeTx(self)

    async def fetch(self, sql: str, status: str, limit: int) -> list[dict[str, Any]]:
        assert "FOR UPDATE SKIP LOCKED" in sql
        pending = [
            r for r in self.rows.values()
            if r["status"] == status and r["next_retry_at"] <= datetime.now(timezone.utc)
        ]
        return pending[:limit]

    async def fetchrow(self, sql: str, *args: Any) -> Optional[dict[str, Any]]:
        if "UPDATE payment_outbox" in sql and "RETURNING" in sql:
            row_id, new_status, lease_owner, lease_sec, expected_status = args[:5]
            row = self.rows.get(row_id)
            if row is None or row["status"] != expected_status:
                return None
            row["status"] = new_status
            row["lease_owner"] = lease_owner
            row["lease_until"] = datetime.now(timezone.utc) + timedelta(seconds=int(lease_sec))
            row["attempt_count"] += 1
            return row
        return None

    async def execute(self, sql: str, *args: Any) -> str:
        if "delivered_at = now()" in sql:
            row_id, new_status, proc_status, lease_owner = args[0], args[1], args[2], args[3]
            row = self.rows.get(row_id)
            if row is None or row["status"] != proc_status or row["lease_owner"] != lease_owner:
                return "UPDATE 0"
            row["status"] = new_status
            row["lease_owner"] = None
            row["lease_until"] = None
            return "UPDATE 1"
        if len(args) >= 6 and args[1] == OUTBOX_PENDING:
            row_id, new_status, _err, _next, proc_status, lease_owner = args[:6]
            row = self.rows.get(row_id)
            if row is None or row["status"] != proc_status or row["lease_owner"] != lease_owner:
                return "UPDATE 0"
            row["status"] = new_status
            row["lease_owner"] = None
            row["lease_until"] = None
            return "UPDATE 1"
        if len(args) >= 5 and args[1] == OUTBOX_DEAD_LETTER:
            row_id, dead, _err, proc_status, lease_owner = args[:5]
            row = self.rows.get(row_id)
            if row is None or row["status"] != proc_status or row["lease_owner"] != lease_owner:
                return "UPDATE 0"
            row["status"] = dead
            row["lease_owner"] = None
            row["lease_until"] = None
            return "UPDATE 1"
        if "lease_until < now()" in sql:
            new_status, proc_status, stale_sec = args[:3]
            count = 0
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=int(stale_sec))
            for row in self.rows.values():
                if (
                    row["status"] == proc_status
                    and row["lease_until"] is not None
                    and row["lease_until"] < cutoff
                ):
                    row["status"] = new_status
                    row["lease_owner"] = None
                    row["lease_until"] = None
                    count += 1
            return f"UPDATE {count}"
        return "UPDATE 0"


class TestOutboxClaimConcurrency(unittest.IsolatedAsyncioTestCase):
    async def test_two_workers_only_one_claims(self):
        rid = uuid.uuid4()
        store = {rid: _row(id=rid)}
        conn_a = _FakeConn(store)
        conn_b = _FakeConn(store)

        async with conn_a.transaction():
            claimed_a = await outbox_mod.claim_batch(conn_a, worker_id="worker-a", limit=1)
        async with conn_b.transaction():
            claimed_b = await outbox_mod.claim_batch(conn_b, worker_id="worker-b", limit=1)

        self.assertEqual(len(claimed_a), 1)
        self.assertEqual(len(claimed_b), 0)
        self.assertEqual(store[rid]["status"], OUTBOX_PROCESSING)
        self.assertEqual(store[rid]["lease_owner"], "worker-a")

    async def test_wrong_owner_cannot_mark_delivered(self):
        rid = uuid.uuid4()
        store = {rid: _row(id=rid)}
        conn = _FakeConn(store)
        async with conn.transaction():
            await outbox_mod.claim_batch(conn, worker_id="worker-a", limit=1)

        ok_wrong = await outbox_mod.mark_delivered(conn, rid, lease_owner="worker-b")
        ok_right = await outbox_mod.mark_delivered(conn, rid, lease_owner="worker-a")
        self.assertFalse(ok_wrong)
        self.assertTrue(ok_right)
        self.assertEqual(store[rid]["status"], OUTBOX_DELIVERED)

    async def test_stale_lease_reclaimed_and_second_worker_claims(self):
        rid = uuid.uuid4()
        expired = datetime.now(timezone.utc) - timedelta(minutes=10)
        store = {
            rid: _row(
                id=rid,
                status=OUTBOX_PROCESSING,
                lease_owner="worker-dead",
                lease_until=expired,
                attempt_count=1,
            )
        }
        conn = _FakeConn(store)
        reclaimed = await outbox_mod.recover_stale_leases(conn, stale_sec=0)
        self.assertEqual(reclaimed, 1)
        self.assertEqual(store[rid]["status"], OUTBOX_PENDING)

        async with conn.transaction():
            claimed = await outbox_mod.claim_batch(conn, worker_id="worker-b", limit=1)
        self.assertEqual(len(claimed), 1)
        self.assertEqual(store[rid]["lease_owner"], "worker-b")

    async def test_side_effect_failure_retries(self):
        rid = uuid.uuid4()
        store = {rid: _row(id=rid, attempt_count=0)}
        conn = _FakeConn(store)
        async with conn.transaction():
            claimed = await outbox_mod.claim_batch(conn, worker_id="worker-a", limit=1)
        self.assertEqual(claimed[0]["attempt_count"], 1)

        ok = await outbox_mod.mark_failed(
            conn, rid, lease_owner="worker-a", error="redis down", attempt_count=1,
        )
        self.assertTrue(ok)
        self.assertEqual(store[rid]["status"], OUTBOX_PENDING)

    async def test_max_attempts_dead_letter(self):
        rid = uuid.uuid4()
        store = {rid: _row(id=rid, attempt_count=MAX_OUTBOX_ATTEMPTS - 1)}
        conn = _FakeConn(store)
        async with conn.transaction():
            claimed = await outbox_mod.claim_batch(conn, worker_id="worker-a", limit=1)
        self.assertEqual(claimed[0]["attempt_count"], MAX_OUTBOX_ATTEMPTS)

        ok = await outbox_mod.mark_failed(
            conn, rid, lease_owner="worker-a", error="final",
            attempt_count=MAX_OUTBOX_ATTEMPTS,
        )
        self.assertTrue(ok)
        self.assertEqual(store[rid]["status"], OUTBOX_DEAD_LETTER)

    async def test_worker_deliver_outside_claim_tx(self):
        import infra.payments.worker as worker

        calls: list[str] = []

        class PoolConn:
            in_tx = False

            def transaction(self):
                return _FakeTx(self)

            async def fetchval(self, *a, **k):
                return 0

        row = _row()
        claimed_row = {
            "id": row["id"],
            "delivery_type": row["delivery_type"],
            "payload": row["payload"],
            "attempt_count": 1,
            "lease_owner": "worker-x",
        }

        async def _claim(conn, *, worker_id, limit=20):
            calls.append("claim")
            assert conn.in_tx
            return [claimed_row]

        async def _deliver(payload):
            calls.append("deliver")

        async def _mark(conn, outbox_id, *, lease_owner):
            calls.append("mark")
            return True

        class _Acquire:
            def __init__(self, conn):
                self._conn = conn

            async def __aenter__(self):
                return self._conn

            async def __aexit__(self, *a):
                pass

        fake_pool = MagicMock()
        fake_pool.fetchval = AsyncMock(return_value=0)
        fake_pool.acquire = MagicMock(return_value=_Acquire(PoolConn()))

        with patch("infra.postgres.pool", return_value=fake_pool):
            with patch("infra.payments.metrics.set_gauge"):
                with patch.object(worker.outbox_mod, "claim_batch", side_effect=_claim):
                    with patch.object(worker, "_deliver_discord_notify", side_effect=_deliver):
                        with patch.object(worker.outbox_mod, "mark_delivered", side_effect=_mark):
                            n = await worker.process_outbox_batch()
        self.assertEqual(n, 1)
        self.assertEqual(calls, ["claim", "deliver", "mark"])


if __name__ == "__main__":
    unittest.main()
