"""
Tiffany Payments — durable ledger with state machine and transactional outbox.

All financial side effects run inside PostgreSQL transactions.
External APIs (Discord) are deferred via payment_outbox.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from infra.payments import audit, outbox
from infra.payments.constants import (
    OUTBOX_DISCORD_NOTIFY,
    REVOKE_SUBSCRIPTION_STATUSES,
    STALE_PROCESSING_SEC,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_RECEIVED,
    STATUS_RETRY_PENDING,
    STATUS_VALIDATED,
    TERMINAL_STATUSES,
)
from infra.payments.metrics import inc
from infra.payments.tiers import UnknownPriceError, UnknownTierError, resolve_tier, validate_discord_metadata

log = logging.getLogger("tiffany.payments.ledger")

ClaimResult = str  # new | duplicate | in_flight | retry


def payload_hash(event: dict) -> str:
    raw = json.dumps(event, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def claim_event(
    conn: Any,
    *,
    event_id: str,
    event_type: str,
    correlation_id: uuid.UUID,
    trace_id: str,
    phash: str,
) -> ClaimResult:
    row = await conn.fetchrow(
        """
        INSERT INTO stripe_events (
            event_id, event_type, status, correlation_id, trace_id,
            payload_hash, received_at, processed_at
        ) VALUES ($1, $2, $3, $4, $5, $6, now(), now())
        ON CONFLICT (event_id) DO NOTHING
        RETURNING event_id
        """,
        event_id,
        event_type,
        STATUS_RECEIVED,
        correlation_id,
        trace_id,
        phash,
    )
    if row:
        return "new"

    existing = await conn.fetchrow(
        "SELECT status, received_at, attempt_count FROM stripe_events WHERE event_id = $1",
        event_id,
    )
    if not existing:
        return "duplicate"

    status = existing["status"]
    if status == STATUS_COMPLETED:
        inc("webhook_duplicate")
        return "duplicate"

    if status == STATUS_PROCESSING:
        received_at = existing["received_at"]
        if received_at and (datetime.now(timezone.utc) - received_at).total_seconds() > STALE_PROCESSING_SEC:
            await conn.execute(
                """
                UPDATE stripe_events
                SET status = $2, attempt_count = attempt_count + 1, last_error = 'stale processing recovered'
                WHERE event_id = $1
                """,
                event_id,
                STATUS_RETRY_PENDING,
            )
            inc("stale_processing_recovered")
            return "retry"
        inc("webhook_idempotency_collision")
        return "in_flight"

    if status in (STATUS_FAILED, STATUS_RETRY_PENDING):
        await conn.execute(
            """
            UPDATE stripe_events
            SET status = $2, attempt_count = attempt_count + 1, received_at = now()
            WHERE event_id = $1
            """,
            event_id,
            STATUS_RETRY_PENDING,
        )
        return "retry"

    inc("webhook_duplicate")
    return "duplicate"


async def mark_completed(conn: Any, event_id: str) -> None:
    await conn.execute(
        """
        UPDATE stripe_events
        SET status = $2, completed_at = now(), last_error = NULL
        WHERE event_id = $1
        """,
        event_id,
        STATUS_COMPLETED,
    )


async def mark_failed(event_id: str, error: str) -> None:
    from infra import postgres

    pool = postgres.pool()
    if pool is None:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE stripe_events
            SET status = $2, last_error = $3
            WHERE event_id = $1 AND status != $4
            """,
            event_id,
            STATUS_FAILED,
            error[:500],
            STATUS_COMPLETED,
        )


async def _upsert_subscription_tx(
    conn: Any,
    *,
    subject_type: str,
    subject_id: int,
    tier: str,
    stripe_customer_id: str,
    stripe_subscription_id: str,
    stripe_price_id: str,
) -> dict:
    prev = await conn.fetchrow(
        """
        SELECT tier, cancelled_at, stripe_subscription_id
        FROM subscriptions
        WHERE subject_type = $1 AND subject_id = $2 AND source = 'stripe'
        """,
        subject_type,
        subject_id,
    )
    previous_state = dict(prev) if prev else {}

    await conn.execute(
        """
        INSERT INTO subscriptions (
            subject_type, subject_id, tier, source, external_id,
            stripe_customer_id, stripe_subscription_id, stripe_price_id, expires_at
        ) VALUES ($1, $2, $3, 'stripe', $4, $5, $6, $7, NULL)
        ON CONFLICT (subject_type, subject_id, source)
        DO UPDATE SET
            tier = EXCLUDED.tier,
            stripe_customer_id = EXCLUDED.stripe_customer_id,
            stripe_subscription_id = EXCLUDED.stripe_subscription_id,
            stripe_price_id = EXCLUDED.stripe_price_id,
            expires_at = NULL,
            cancelled_at = NULL,
            updated_at = now()
        """,
        subject_type,
        subject_id,
        tier,
        stripe_subscription_id,
        stripe_customer_id,
        stripe_subscription_id,
        stripe_price_id,
    )
    new_state = {
        "tier": tier,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "stripe_subscription_id": stripe_subscription_id,
    }
    return {"previous_state": previous_state, "new_state": new_state}


async def _cancel_subscription_tx(conn: Any, stripe_subscription_id: str) -> Optional[dict]:
    row = await conn.fetchrow(
        """
        UPDATE subscriptions
        SET cancelled_at = now(), tier = 'free', updated_at = now()
        WHERE stripe_subscription_id = $1 AND cancelled_at IS NULL
        RETURNING subject_type, subject_id, tier
        """,
        stripe_subscription_id,
    )
    if not row:
        return None
    return {
        "previous_state": {"stripe_subscription_id": stripe_subscription_id},
        "new_state": {"tier": "free", "subject_type": row["subject_type"], "subject_id": row["subject_id"]},
        "subject_type": row["subject_type"],
        "subject_id": row["subject_id"],
    }


async def _provision_guild_config_tx(
    conn: Any,
    guild_id: int,
    purchaser_id: int,
    package: str,
    package_defaults: dict[str, dict],
) -> None:
    defaults = package_defaults.get(package, {})
    existing = await conn.fetchval(
        "SELECT config FROM guild_premium_config WHERE guild_id = $1",
        guild_id,
    )
    if existing:
        merged = json.loads(existing) if isinstance(existing, str) else dict(existing)
        for section, section_defaults in defaults.items():
            if section not in merged:
                merged[section] = section_defaults
            elif isinstance(section_defaults, dict):
                for k, v in section_defaults.items():
                    if k not in merged[section]:
                        merged[section][k] = v
    else:
        merged = defaults

    await conn.execute(
        """
        INSERT INTO guild_premium_config (guild_id, purchaser_id, package, config)
        VALUES ($1, $2, $3, $4::jsonb)
        ON CONFLICT (guild_id) DO UPDATE SET
            purchaser_id = EXCLUDED.purchaser_id,
            package = EXCLUDED.package,
            config = EXCLUDED.config,
            updated_at = now()
        """,
        guild_id,
        purchaser_id,
        package,
        json.dumps(merged),
    )


async def _apply_checkout_completed(
    conn: Any,
    event: dict,
    *,
    correlation_id: uuid.UUID,
    trace_id: str,
    price_to_tier: dict[str, str],
    package_defaults: dict[str, dict],
    stripe_sdk: Any,
    stripe_secret_key: str,
) -> None:
    session = event.get("data", {}).get("object", {})
    if session.get("mode") != "subscription":
        return

    payment_status = session.get("payment_status", "")
    if payment_status and payment_status != "paid":
        raise ValueError(f"checkout not paid: {payment_status}")

    stripe_sub_id = session.get("subscription") or ""
    if not stripe_sub_id:
        raise ValueError("checkout missing subscription id")

    meta = session.get("metadata", {}) or {}
    subject_type, subject_id, purchaser_id = validate_discord_metadata(meta)

    price_id = str(meta.get("price_id", "") or "").strip()
    if not price_id and stripe_sdk and stripe_secret_key:
        try:
            stripe_sdk.api_key = stripe_secret_key
            sub_obj = stripe_sdk.Subscription.retrieve(stripe_sub_id)
            items = sub_obj.get("items", {}).get("data") or []
            if items:
                price_id = items[0].get("price", {}).get("id", "")
        except Exception as exc:
            log.warning("Stripe subscription retrieve failed during checkout: %s", exc)

    tier = resolve_tier(
        price_id=price_id,
        metadata_package=str(meta.get("package", "") or ""),
        price_to_tier=price_to_tier,
    )

    transition = await _upsert_subscription_tx(
        conn,
        subject_type=subject_type,
        subject_id=subject_id,
        tier=tier,
        stripe_customer_id=str(session.get("customer", "") or ""),
        stripe_subscription_id=stripe_sub_id,
        stripe_price_id=price_id,
    )

    guild_id = subject_id if subject_type == "guild" else None
    user_id = purchaser_id if subject_type == "guild" else subject_id

    if subject_type == "guild":
        await _provision_guild_config_tx(conn, subject_id, purchaser_id, tier, package_defaults)

    await audit.append_audit(
        conn,
        actor="stripe_webhook",
        action="premium_activated",
        provider_event_id=event.get("id"),
        correlation_id=correlation_id,
        trace_id=trace_id,
        guild_id=guild_id,
        user_id=user_id,
        stripe_subscription_id=stripe_sub_id,
        previous_state=transition["previous_state"],
        new_state=transition["new_state"],
        reason="checkout.session.completed",
    )

    await outbox.enqueue(
        conn,
        delivery_type=OUTBOX_DISCORD_NOTIFY,
        payload={
            "kind": "premium_activated",
            "guild_id": guild_id,
            "user_id": user_id,
            "tier": tier,
            "stripe_subscription_id": stripe_sub_id,
        },
        provider_event_id=event.get("id"),
        correlation_id=correlation_id,
        trace_id=trace_id,
    )


async def _apply_subscription_updated(
    conn: Any,
    event: dict,
    *,
    correlation_id: uuid.UUID,
    trace_id: str,
    price_to_tier: dict[str, str],
) -> None:
    sub = event.get("data", {}).get("object", {})
    stripe_sub_id = sub.get("id", "")
    status = sub.get("status", "")

    if status in ("active", "trialing"):
        items = sub.get("items", {}).get("data") or []
        price_id = items[0].get("price", {}).get("id", "") if items else ""
        tier = resolve_tier(price_id=price_id, metadata_package=None, price_to_tier=price_to_tier)

        row = await conn.fetchrow(
            "SELECT subject_type, subject_id FROM subscriptions WHERE stripe_subscription_id = $1",
            stripe_sub_id,
        )
        if not row:
            log.warning("subscription.updated for unknown sub=%s — skipping", stripe_sub_id)
            return

        transition = await _upsert_subscription_tx(
            conn,
            subject_type=row["subject_type"],
            subject_id=row["subject_id"],
            tier=tier,
            stripe_customer_id=str(sub.get("customer", "") or ""),
            stripe_subscription_id=stripe_sub_id,
            stripe_price_id=price_id,
        )
        await audit.append_audit(
            conn,
            actor="stripe_webhook",
            action="subscription_updated",
            provider_event_id=event.get("id"),
            correlation_id=correlation_id,
            trace_id=trace_id,
            guild_id=row["subject_id"] if row["subject_type"] == "guild" else None,
            user_id=row["subject_id"] if row["subject_type"] == "user" else None,
            stripe_subscription_id=stripe_sub_id,
            previous_state=transition["previous_state"],
            new_state=transition["new_state"],
            reason=f"status={status}",
        )
        return

    if status in REVOKE_SUBSCRIPTION_STATUSES:
        result = await _cancel_subscription_tx(conn, stripe_sub_id)
        if result:
            await audit.append_audit(
                conn,
                actor="stripe_webhook",
                action="subscription_revoked",
                provider_event_id=event.get("id"),
                correlation_id=correlation_id,
                trace_id=trace_id,
                guild_id=result["subject_id"] if result["subject_type"] == "guild" else None,
                user_id=result["subject_id"] if result["subject_type"] == "user" else None,
                stripe_subscription_id=stripe_sub_id,
                previous_state=result["previous_state"],
                new_state=result["new_state"],
                reason=f"status={status}",
            )
            await outbox.enqueue(
                conn,
                delivery_type=OUTBOX_DISCORD_NOTIFY,
                payload={
                    "kind": "subscription_revoked",
                    "subject_type": result["subject_type"],
                    "subject_id": result["subject_id"],
                    "stripe_subscription_id": stripe_sub_id,
                },
                provider_event_id=event.get("id"),
                correlation_id=correlation_id,
                trace_id=trace_id,
            )


async def _apply_subscription_deleted(
    conn: Any,
    event: dict,
    *,
    correlation_id: uuid.UUID,
    trace_id: str,
) -> None:
    sub = event.get("data", {}).get("object", {})
    stripe_sub_id = sub.get("id", "")
    result = await _cancel_subscription_tx(conn, stripe_sub_id)
    if result:
        await audit.append_audit(
            conn,
            actor="stripe_webhook",
            action="subscription_deleted",
            provider_event_id=event.get("id"),
            correlation_id=correlation_id,
            trace_id=trace_id,
            guild_id=result["subject_id"] if result["subject_type"] == "guild" else None,
            user_id=result["subject_id"] if result["subject_type"] == "user" else None,
            stripe_subscription_id=stripe_sub_id,
            previous_state=result["previous_state"],
            new_state=result["new_state"],
            reason="customer.subscription.deleted",
        )


async def _apply_invoice_payment_failed(
    conn: Any,
    event: dict,
    *,
    correlation_id: uuid.UUID,
    trace_id: str,
) -> None:
    invoice = event.get("data", {}).get("object", {})
    stripe_sub_id = invoice.get("subscription", "")
    attempt = invoice.get("attempt_count", 0)
    await audit.append_audit(
        conn,
        actor="stripe_webhook",
        action="payment_failed",
        provider_event_id=event.get("id"),
        correlation_id=correlation_id,
        trace_id=trace_id,
        stripe_subscription_id=stripe_sub_id,
        reason=f"attempt={attempt}",
        result="logged",
        metadata={"attempt_count": attempt},
    )


_HANDLERS: dict[str, Callable[..., Any]] = {
    "checkout.session.completed": _apply_checkout_completed,
    "customer.subscription.updated": _apply_subscription_updated,
    "customer.subscription.deleted": _apply_subscription_deleted,
    "invoice.payment_failed": _apply_invoice_payment_failed,
}


async def process_stripe_event(
    event: dict,
    *,
    trace_id: str,
    price_to_tier: dict[str, str],
    package_defaults: dict[str, dict],
    stripe_sdk: Any = None,
    stripe_secret_key: str = "",
) -> str:
    """
    Process a verified Stripe event exactly-once (with PG).
    Returns: ok | duplicate | in_flight | ignored
    """
    from infra import postgres

    event_id = str(event.get("id", ""))
    event_type = str(event.get("type", ""))
    correlation_id = uuid.uuid4()
    phash = payload_hash(event)

    pool = postgres.pool()
    if pool is None:
        raise RuntimeError("DATABASE_URL required for payment processing")

    handler = _HANDLERS.get(event_type)
    if handler is None:
        return "ignored"

    inc("webhook_received")

    async with pool.acquire() as conn:
        async with conn.transaction():
            claim = await claim_event(
                conn,
                event_id=event_id,
                event_type=event_type,
                correlation_id=correlation_id,
                trace_id=trace_id,
                phash=phash,
            )
            if claim == "duplicate":
                return "duplicate"
            if claim == "in_flight":
                return "in_flight"

            await conn.execute(
                "UPDATE stripe_events SET status = $2 WHERE event_id = $1",
                event_id,
                STATUS_VALIDATED,
            )
            await audit.append_audit(
                conn,
                actor="stripe_webhook",
                action="event_validated",
                provider_event_id=event_id,
                correlation_id=correlation_id,
                trace_id=trace_id,
                metadata={"event_type": event_type, "claim": claim},
            )

            await conn.execute(
                "UPDATE stripe_events SET status = $2 WHERE event_id = $1",
                event_id,
                STATUS_PROCESSING,
            )

            if event_type == "checkout.session.completed":
                await handler(
                    conn,
                    event,
                    correlation_id=correlation_id,
                    trace_id=trace_id,
                    price_to_tier=price_to_tier,
                    package_defaults=package_defaults,
                    stripe_sdk=stripe_sdk,
                    stripe_secret_key=stripe_secret_key,
                )
            elif event_type in ("customer.subscription.updated",):
                await handler(
                    conn,
                    event,
                    correlation_id=correlation_id,
                    trace_id=trace_id,
                    price_to_tier=price_to_tier,
                )
            elif event_type == "invoice.payment_failed":
                await handler(conn, event, correlation_id=correlation_id, trace_id=trace_id)
            else:
                await handler(conn, event, correlation_id=correlation_id, trace_id=trace_id)

            await mark_completed(conn, event_id)
            await audit.append_audit(
                conn,
                actor="stripe_webhook",
                action="event_completed",
                provider_event_id=event_id,
                correlation_id=correlation_id,
                trace_id=trace_id,
                metadata={"event_type": event_type},
            )

    inc("webhook_completed")
    return "ok"


async def verify_withdrawable_funds(conn: Any, user_id: int, requested_amount_brl: float) -> tuple[bool, str]:
    """
    Kantuaria Financial Model: Verifies settled funds vs requested withdrawal amount.
    Enforces MIN_WITHDRAWAL_BRL and MAX_DAILY_WITHDRAWAL_BRL bounds.
    Returns (allowed: bool, reason: str).
    """
    from infra.payments.constants import MIN_WITHDRAWAL_BRL, MAX_DAILY_WITHDRAWAL_BRL, STATUS_COMPLETED

    if requested_amount_brl < MIN_WITHDRAWAL_BRL:
        return False, f"Requested amount R$ {requested_amount_brl:.2f} is below minimum withdrawal threshold R$ {MIN_WITHDRAWAL_BRL:.2f}"
    if requested_amount_brl > MAX_DAILY_WITHDRAWAL_BRL:
        return False, f"Requested amount R$ {requested_amount_brl:.2f} exceeds daily limit R$ {MAX_DAILY_WITHDRAWAL_BRL:.2f}"

    settled_credits = await conn.fetchval(
        """
        SELECT COALESCE(SUM((data->'object'->>'amount_total')::numeric / 100.0), 0)
        FROM stripe_events
        WHERE status = $1 AND (payload_hash IS NOT NULL)
        """,
        STATUS_COMPLETED,
    )
    settled_val = float(settled_credits or 0)
    if requested_amount_brl > settled_val:
        return False, f"Withdrawal request (R$ {requested_amount_brl:.2f}) exceeds settled platform funds (R$ {settled_val:.2f})"

    return True, "withdrawable_funds_verified"
