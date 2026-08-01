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
    OUTBOX_FAILED,
    OUTBOX_PENDING,
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


async def fetch_pending_batch(conn: Any, *, limit: int = 20) -> list[Any]:
    return await conn.fetch(
        """
        SELECT id, delivery_type, payload, attempt_count, provider_event_id, correlation_id, trace_id
        FROM payment_outbox
        WHERE status = $1 AND next_retry_at <= now()
        ORDER BY created_at
        LIMIT $2
        FOR UPDATE SKIP LOCKED
        """,
        OUTBOX_PENDING,
        limit,
    )


async def mark_delivered(conn: Any, outbox_id: uuid.UUID) -> None:
    await conn.execute(
        """
        UPDATE payment_outbox
        SET status = $2, delivered_at = now(), last_error = NULL
        WHERE id = $1
        """,
        outbox_id,
        OUTBOX_DELIVERED,
    )
    inc("outbox_delivered")


async def mark_failed(conn: Any, outbox_id: uuid.UUID, *, error: str, attempt_count: int) -> None:
    new_attempt = attempt_count + 1
    if new_attempt >= MAX_OUTBOX_ATTEMPTS:
        await conn.execute(
            """
            UPDATE payment_outbox
            SET status = $2, attempt_count = $3, last_error = $4
            WHERE id = $1
            """,
            outbox_id,
            OUTBOX_DEAD_LETTER,
            new_attempt,
            error[:500],
        )
        inc("outbox_dead_letter")
        return

    backoff_sec = min(3600, 2 ** new_attempt * 5)
    next_retry = datetime.now(timezone.utc) + timedelta(seconds=backoff_sec)
    await conn.execute(
        """
        UPDATE payment_outbox
        SET status = $2, attempt_count = $3, last_error = $4, next_retry_at = $5
        WHERE id = $1
        """,
        outbox_id,
        OUTBOX_PENDING,
        new_attempt,
        error[:500],
        next_retry,
    )
    inc("outbox_failed")
