"""Append-only payment audit trail."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

log = logging.getLogger("tiffany.payments.audit")


async def append_audit(
    conn: Any,
    *,
    actor: str,
    action: str,
    provider_event_id: Optional[str] = None,
    correlation_id: Optional[uuid.UUID] = None,
    trace_id: Optional[str] = None,
    guild_id: Optional[int] = None,
    user_id: Optional[int] = None,
    stripe_subscription_id: Optional[str] = None,
    previous_state: Optional[dict] = None,
    new_state: Optional[dict] = None,
    reason: Optional[str] = None,
    result: str = "ok",
    metadata: Optional[dict] = None,
) -> None:
    """Persist immutable audit record inside caller's transaction."""
    await conn.execute(
        """
        INSERT INTO payment_audit_log (
            actor, provider_event_id, correlation_id, trace_id,
            guild_id, user_id, stripe_subscription_id,
            action, previous_state, new_state, reason, result, metadata
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8,
            $9::jsonb, $10::jsonb, $11, $12, $13::jsonb
        )
        """,
        actor,
        provider_event_id,
        correlation_id,
        trace_id,
        guild_id,
        user_id,
        stripe_subscription_id,
        action,
        json.dumps(previous_state or {}),
        json.dumps(new_state or {}),
        reason,
        result,
        json.dumps(metadata or {}),
    )
