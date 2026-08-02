"""Stripe ledger idempotency against real PostgreSQL — Phase XII."""

from __future__ import annotations

import uuid

import pytest

from infra.payments.ledger import claim_event, payload_hash
from tests.integration.conftest import run_async


@pytest.mark.integration
class TestStripeIdempotencyPostgres:
    def test_duplicate_event_id_returns_duplicate(self, pg_pool, event_loop):
        pool, _ = pg_pool
        event_id = f"evt_test_{uuid.uuid4().hex[:12]}"
        correlation = uuid.uuid4()
        phash = payload_hash({"id": event_id, "type": "customer.subscription.updated"})

        async def _run():
            async with pool.acquire() as conn:
                async with conn.transaction():
                    first = await claim_event(
                        conn,
                        event_id=event_id,
                        event_type="customer.subscription.updated",
                        correlation_id=correlation,
                        trace_id="phase12",
                        phash=phash,
                    )
                    second = await claim_event(
                        conn,
                        event_id=event_id,
                        event_type="customer.subscription.updated",
                        correlation_id=correlation,
                        trace_id="phase12",
                        phash=phash,
                    )
            return first, second

        first, second = run_async(event_loop, _run())
        assert first == "new"
        assert second == "duplicate"

    def test_concurrent_claim_one_wins(self, pg_pool, event_loop):
        pool, _ = pg_pool
        event_id = f"evt_concurrent_{uuid.uuid4().hex[:12]}"
        correlation = uuid.uuid4()
        phash = payload_hash({"id": event_id})

        async def _claim_once(label: str) -> str:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    return await claim_event(
                        conn,
                        event_id=event_id,
                        event_type="checkout.session.completed",
                        correlation_id=correlation,
                        trace_id=label,
                        phash=phash,
                    )

        async def _run():
            import asyncio as aio
            results = await aio.gather(_claim_once("a"), _claim_once("b"))
            status = await pool.fetchval(
                "SELECT status FROM stripe_events WHERE event_id = $1", event_id,
            )
            return results, status

        results, status = run_async(event_loop, _run())
        assert sorted(results) == ["duplicate", "new"]
        assert status is not None
