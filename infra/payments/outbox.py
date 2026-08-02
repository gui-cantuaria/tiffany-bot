"""Transactional outbox for Discord and other async side effects."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from infra.payments.constants import (
    MAX_OUTBOX_ATTEMPTS,
    OUTBOX_DEAD_LETTER,
    OUTBOX_DELIVERED,
    OUTBOX_PENDING,
    OUTBOX_PROCESSING,
    OUTBOX_LEASE_SEC,
)
from infra.payments.metrics import inc

log = logging.getLogger("tiffany.payments.outbox")


async def enqueue(
    conn: Any,
    *,
    delivery_type: str,
    payload: dict,
    provider_event_id: Optional[str] = None,
    correlation_id: Optional[uuid.UUID] = None,
    trace_id: Optional[str] = None,
) -> uuid.UUID:
    """Insert outbox row in the same DB transaction as business state."""
    row = await conn.fetchrow(
        """
        INSERT INTO payment_outbox (
            provider_event_id, correlation_id, trace_id,
            delivery_type, payload, status
        ) VALUES ($1, $2, $3, $4, $5::jsonb, $6)
        RETURNING id
        """,
        provider_event_id,
        correlation_id,
        trace_id,
        delivery_type,
        json.dumps(payload),
        OUTBOX_PENDING,
    )
    inc("outbox_enqueued")
    return row["id"]


async def claim_batch(
    conn: Any,
    *,
    worker_id: str,
    limit: int = 20,
    lease_sec: int = OUTBOX_LEASE_SEC,
) -> list[Any]:
    """Atomically claim pending rows inside the caller's transaction.

    Each row transitions pending → processing with a unique lease_owner.
    attempt_count is incremented at claim time (one delivery attempt).
    """
    candidates = await conn.fetch(
        """
        SELECT id, delivery_type, payload, attempt_count,
               provider_event_id, correlation_id, trace_id
        FROM payment_outbox
        WHERE status = $1 AND next_retry_at <= now()
        ORDER BY created_at
        LIMIT $2
        FOR UPDATE SKIP LOCKED
        """,
        OUTBOX_PENDING,
        limit,
    )
    claimed: list[Any] = []
    for row in candidates:
        updated = await conn.fetchrow(
            """
            UPDATE payment_outbox
            SET status = $2,
                lease_owner = $3,
                lease_until = now() + ($4 || ' seconds')::interval,
                attempt_count = attempt_count + 1
            WHERE id = $1 AND status = $5
            RETURNING id, delivery_type, payload, attempt_count,
                      provider_event_id, correlation_id, trace_id,
                      lease_owner, lease_until
            """,
            row["id"],
            OUTBOX_PROCESSING,
            worker_id,
            str(lease_sec),
            OUTBOX_PENDING,
        )
        if updated:
            claimed.append(updated)
    if claimed:
        inc("outbox_claimed", len(claimed))
    return claimed


async def fetch_pending_batch(conn: Any, *, limit: int = 20) -> list[Any]:
    """Read-only peek at pending rows — not for delivery (use claim_batch)."""
    return await conn.fetch(
        """
        SELECT id, delivery_type, payload, attempt_count,
               provider_event_id, correlation_id, trace_id
        FROM payment_outbox
        WHERE status = $1 AND next_retry_at <= now()
        ORDER BY created_at
        LIMIT $2
        """,
        OUTBOX_PENDING,
        limit,
    )


async def mark_delivered(
    conn: Any,
    outbox_id: uuid.UUID,
    *,
    lease_owner: str,
) -> bool:
    """Mark delivered only if this worker still owns the lease."""
    result = await conn.execute(
        """
        UPDATE payment_outbox
        SET status = $2,
            delivered_at = now(),
            last_error = NULL,
            lease_owner = NULL,
            lease_until = NULL
        WHERE id = $1
          AND status = $3
          AND lease_owner = $4
        """,
        outbox_id,
        OUTBOX_DELIVERED,
        OUTBOX_PROCESSING,
        lease_owner,
    )
    if str(result).endswith("1"):
        inc("outbox_delivered")
        return True
    return False


async def mark_failed(
    conn: Any,
    outbox_id: uuid.UUID,
    *,
    lease_owner: str,
    error: str,
    attempt_count: int,
) -> bool:
    """Release lease and retry or dead-letter. Only the lease owner may update."""
    if attempt_count >= MAX_OUTBOX_ATTEMPTS:
        result = await conn.execute(
            """
            UPDATE payment_outbox
            SET status = $2,
                last_error = $3,
                lease_owner = NULL,
                lease_until = NULL
            WHERE id = $1
              AND status = $4
              AND lease_owner = $5
            """,
            outbox_id,
            OUTBOX_DEAD_LETTER,
            error[:500],
            OUTBOX_PROCESSING,
            lease_owner,
        )
        if str(result).endswith("1"):
            inc("outbox_dead_letter")
            return True
        return False

    backoff_sec = min(3600, 2 ** attempt_count * 5)
    next_retry = datetime.now(timezone.utc) + timedelta(seconds=backoff_sec)
    result = await conn.execute(
        """
        UPDATE payment_outbox
        SET status = $2,
            last_error = $3,
            next_retry_at = $4,
            lease_owner = NULL,
            lease_until = NULL
        WHERE id = $1
          AND status = $5
          AND lease_owner = $6
        """,
        outbox_id,
        OUTBOX_PENDING,
        error[:500],
        next_retry,
        OUTBOX_PROCESSING,
        lease_owner,
    )
    if str(result).endswith("1"):
        inc("outbox_failed")
        return True
    return False


async def recover_stale_leases(conn: Any, *, stale_sec: int) -> int:
    """Reclaim processing rows whose lease expired (worker crash / hang)."""
    result = await conn.execute(
        """
        UPDATE payment_outbox
        SET status = $1,
            lease_owner = NULL,
            lease_until = NULL,
            last_error = COALESCE(last_error, '') || ' [stale lease reclaimed]'
        WHERE status = $2
          AND lease_until IS NOT NULL
          AND lease_until < now() - ($3 || ' seconds')::interval
        """,
        OUTBOX_PENDING,
        OUTBOX_PROCESSING,
        str(stale_sec),
    )
    try:
        count = int(str(result).split()[-1])
    except (ValueError, IndexError):
        count = 0
    if count:
        inc("outbox_stale_leases_recovered", count)
        log.warning("Reclaimed %d stale outbox lease(s)", count)
    return count
