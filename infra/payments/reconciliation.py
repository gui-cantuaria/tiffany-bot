"""Automatic reconciliation — Stripe vs PostgreSQL entitlements."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from infra.payments import audit
from infra.payments.metrics import inc

log = logging.getLogger("tiffany.payments.reconciliation")


async def run_reconciliation(*, stripe_sdk: Any = None, stripe_secret_key: str = "") -> dict:
    """
    Compare active Stripe subscriptions with local DB rows.
    Records drift in payment_reconciliation_runs and payment_audit_log.
    Does not auto-mutate Stripe — corrections are DB-side only when safe.
    """
    from infra import postgres

    pool = postgres.pool()
    if pool is None:
        return {"status": "skipped", "reason": "no_database"}

    run_id = uuid.uuid4()
    drift: list[dict] = []
    corrections: list[dict] = []

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO payment_reconciliation_runs (id, status)
            VALUES ($1, 'running')
            """,
            run_id,
        )

        local_rows = await conn.fetch(
            """
            SELECT subject_type, subject_id, tier, stripe_subscription_id, cancelled_at
            FROM subscriptions
            WHERE source = 'stripe' AND stripe_subscription_id IS NOT NULL
            """
        )
        local_by_sub = {
            r["stripe_subscription_id"]: dict(r)
            for r in local_rows
            if r["stripe_subscription_id"]
        }

        stripe_active: dict[str, str] = {}
        if stripe_sdk and stripe_secret_key:
            try:
                stripe_sdk.api_key = stripe_secret_key
                subs = stripe_sdk.Subscription.list(status="active", limit=100)
                for sub in subs.auto_paging_iter():
                    stripe_active[sub["id"]] = sub.get("status", "")
            except Exception as exc:
                log.warning("Stripe reconciliation API failed: %s", exc)
                await conn.execute(
                    """
                    UPDATE payment_reconciliation_runs
                    SET status = 'failed', completed_at = now(), summary = $2::jsonb
                    WHERE id = $1
                    """,
                    run_id,
                    json.dumps({"error": str(exc)[:200]}),
                )
                return {"status": "failed", "error": str(exc)[:200]}

        for sub_id, local in local_by_sub.items():
            if local.get("cancelled_at"):
                continue
            if sub_id not in stripe_active:
                drift.append({"type": "orphan_local_active", "stripe_subscription_id": sub_id, "local": local})
                inc("reconciliation_drift")

        for sub_id in stripe_active:
            if sub_id not in local_by_sub:
                drift.append({"type": "missing_local", "stripe_subscription_id": sub_id})
                inc("reconciliation_drift")

        await audit.append_audit(
            conn,
            actor="reconciliation",
            action="reconciliation_completed",
            correlation_id=run_id,
            reason=f"drift_count={len(drift)}",
            metadata={"drift": drift[:50]},
        )

        await conn.execute(
            """
            UPDATE payment_reconciliation_runs
            SET status = 'completed', completed_at = now(),
                drift_count = $2, corrections = $3::jsonb,
                summary = $4::jsonb
            WHERE id = $1
            """,
            run_id,
            len(drift),
            json.dumps(corrections),
            json.dumps({"drift_sample": drift[:10], "local_count": len(local_by_sub), "stripe_active_count": len(stripe_active)}),
        )

    if drift:
        log.warning("Payment reconciliation found %d drift items", len(drift))
    else:
        log.info("Payment reconciliation: no drift detected")

    return {"status": "completed", "drift_count": len(drift), "run_id": str(run_id)}
