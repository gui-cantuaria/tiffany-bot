"""Background workers — outbox delivery and stale event recovery."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any, Optional

from infra.payments import outbox as outbox_mod
from infra.payments.constants import (
    OUTBOX_DISCORD_NOTIFY,
    OUTBOX_STALE_LEASE_SEC,
    STATUS_PROCESSING,
    STALE_PROCESSING_SEC,
)
from infra.payments.metrics import inc

log = logging.getLogger("tiffany.payments.worker")

_worker_task: Optional[asyncio.Task] = None
WORKER_ID = f"outbox-{os.getpid()}-{uuid.uuid4().hex[:8]}"


async def _deliver_discord_notify(payload: dict) -> None:
    """Side effect: invalidate premium cache after DB commit (Discord notify deferred)."""
    from infra import premium

    kind = payload.get("kind")
    if kind == "premium_activated":
        guild_id = payload.get("guild_id")
        user_id = payload.get("user_id")
        if guild_id:
            await premium.invalidate_entitlement(guild_id=int(guild_id))
        if user_id:
            await premium.invalidate_entitlement(user_id=int(user_id))
        log.info(
            "Outbox premium_activated delivered: guild=%s user=%s tier=%s",
            guild_id,
            user_id,
            payload.get("tier"),
        )
    elif kind == "subscription_revoked":
        st = payload.get("subject_type")
        sid = payload.get("subject_id")
        if st == "guild" and sid:
            await premium.invalidate_entitlement(guild_id=int(sid))
        elif st == "user" and sid:
            await premium.invalidate_entitlement(user_id=int(sid))
        log.info("Outbox subscription_revoked delivered: %s=%s", st, sid)


async def recover_stale_outbox_leases() -> int:
    from infra import postgres

    pool = postgres.pool()
    if pool is None:
        return 0
    async with pool.acquire() as conn:
        return await outbox_mod.recover_stale_leases(conn, stale_sec=OUTBOX_STALE_LEASE_SEC)


async def process_outbox_batch(*, limit: int = 20) -> int:
    from infra import postgres
    from infra.payments.metrics import set_gauge

    pool = postgres.pool()
    if pool is None:
        return 0

    pending_depth = await pool.fetchval(
        "SELECT count(*)::int FROM payment_outbox WHERE status = 'pending'"
    )
    set_gauge("outbox_pending_depth", int(pending_depth or 0))

    rows: list[Any] = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = list(
                await outbox_mod.claim_batch(conn, worker_id=WORKER_ID, limit=limit)
            )

    processed = 0
    for row in rows:
        delivery_type = row["delivery_type"]
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        outbox_id = row["id"]
        lease_owner = row["lease_owner"]
        try:
            if delivery_type == OUTBOX_DISCORD_NOTIFY:
                await _deliver_discord_notify(payload)
            async with pool.acquire() as conn:
                ok = await outbox_mod.mark_delivered(
                    conn, outbox_id, lease_owner=lease_owner,
                )
            if ok:
                processed += 1
            else:
                log.warning(
                    "Outbox mark_delivered lost lease id=%s worker=%s",
                    outbox_id,
                    WORKER_ID,
                )
        except Exception as exc:
            log.warning("Outbox delivery failed id=%s: %s", outbox_id, exc)
            async with pool.acquire() as conn:
                await outbox_mod.mark_failed(
                    conn,
                    outbox_id,
                    lease_owner=lease_owner,
                    error=str(exc),
                    attempt_count=row["attempt_count"],
                )
    return processed


async def recover_stale_processing_events() -> int:
    from infra import postgres
    from infra.payments.constants import STATUS_RETRY_PENDING

    pool = postgres.pool()
    if pool is None:
        return 0

    result = await pool.execute(
        """
        UPDATE stripe_events
        SET status = $1, last_error = 'stale processing — marked for retry'
        WHERE status = $2
          AND received_at < now() - ($3 || ' seconds')::interval
        """,
        STATUS_RETRY_PENDING,
        STATUS_PROCESSING,
        str(STALE_PROCESSING_SEC),
    )
    try:
        count = int(str(result).split()[-1])
    except (ValueError, IndexError):
        count = 0
    if count:
        inc("stale_processing_recovered", count)
        log.warning("Recovered %d stale stripe_events in processing state", count)
    return count


async def _worker_loop(bot: Any, interval_sec: float) -> None:
    while True:
        try:
            await recover_stale_processing_events()
            await recover_stale_outbox_leases()
            n = await process_outbox_batch()
            if n:
                log.debug("Payment outbox processed %d deliveries", n)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Payment worker loop error")
        await asyncio.sleep(interval_sec)


def start_payment_worker(bot: Any, *, interval_sec: float = 15.0) -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    _worker_task = asyncio.create_task(_worker_loop(bot, interval_sec), name="tiffany-payment-worker")
    log.info("Payment worker started (interval=%ss, id=%s)", interval_sec, WORKER_ID)


async def stop_payment_worker() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
    _worker_task = None
