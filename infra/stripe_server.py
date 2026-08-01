"""
Tiffany Bot — Internal Stripe Webhook Server
=============================================
HTTP layer only. Financial processing lives in infra.payments.ledger.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from typing import Any, Optional

from aiohttp import web

from infra.payments.ledger import mark_failed, process_stripe_event
from infra.payments.metrics import payment_metrics_snapshot
from infra.payments.reconciliation import run_reconciliation
from infra.payments.worker import start_payment_worker, stop_payment_worker

log = logging.getLogger("tiffany-bot")

try:
    import stripe as stripe_sdk
    _HAS_STRIPE = True
except ImportError:
    _HAS_STRIPE = False
    stripe_sdk = None  # type: ignore[assignment]

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_WEBHOOK_PORT = int(os.getenv("STRIPE_WEBHOOK_PORT", "8080"))
STRIPE_WEBHOOK_MAX_BODY_BYTES = int(os.getenv("STRIPE_WEBHOOK_MAX_BODY_BYTES", "262144"))
STRIPE_WEBHOOK_TOLERANCE_SEC = int(os.getenv("STRIPE_WEBHOOK_TOLERANCE_SEC", "300"))
STRIPE_RECONCILE_INTERVAL_SEC = int(os.getenv("STRIPE_RECONCILE_INTERVAL_SEC", "3600"))

ALLOWED_STRIPE_EVENT_TYPES = frozenset({
    "checkout.session.completed",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_failed",
    "invoice.payment_succeeded",
})

PRICE_TO_TIER: dict[str, str] = {}

# Package defaults — proprietary billing rules (PRIVATE)
PACKAGE_DEFAULTS: dict[str, dict] = {
    "offers": {
        "offers": {
            "min_discount_pct": 0,
            "categories_whitelist": [],
            "keywords_blacklist": [],
            "embed_layout": {
                "button_position": "bottom",
                "title_max_chars": 256,
                "title_max_words": 0,
                "show_affiliate": True,
            },
            "nsfw_enabled": False,
            "affiliate_override": True,
        },
        "ai_guardrails": {"block_illegal": True, "nsfw_mode": "block"},
    },
    "news": {
        "news": {
            "custom_rss_urls": [],
            "category_routing": {},
            "auto_translate": False,
            "nsfw_enabled": False,
            "anti_bot_bypass": True,
        },
        "ai_guardrails": {"block_illegal": True, "nsfw_mode": "block"},
    },
    "ultimate": {
        "offers": {
            "min_discount_pct": 0,
            "categories_whitelist": [],
            "keywords_blacklist": [],
            "embed_layout": {
                "button_position": "bottom",
                "title_max_chars": 256,
                "title_max_words": 0,
                "show_affiliate": True,
            },
            "nsfw_enabled": False,
            "affiliate_override": True,
        },
        "news": {
            "custom_rss_urls": [],
            "category_routing": {},
            "auto_translate": False,
            "nsfw_enabled": False,
            "anti_bot_bypass": True,
        },
        "ai_guardrails": {"block_illegal": True, "nsfw_mode": "block"},
        "music": {"vip_enabled": True, "max_queue": 500, "nonstop_24_7": True},
        "ai_limits": {"daily_quota": 500, "model_tier": "premium"},
    },
}


def _load_price_map() -> None:
    global PRICE_TO_TIER
    raw = os.getenv("STRIPE_PRICE_MAP", "").strip()
    if raw:
        try:
            PRICE_TO_TIER = json.loads(raw)
            return
        except json.JSONDecodeError:
            log.warning("STRIPE_PRICE_MAP is not valid JSON, falling back to individual vars")
    for env_key, tier in [
        ("STRIPE_PRICE_OFFERS", "offers"),
        ("STRIPE_PRICE_NEWS", "news"),
        ("STRIPE_PRICE_ULTIMATE", "ultimate"),
    ]:
        price_id = os.getenv(env_key, "").strip()
        if price_id:
            PRICE_TO_TIER[price_id] = tier


def _verify_stripe_signature(payload: bytes, sig_header: str, secret: str) -> dict:
    if _HAS_STRIPE and stripe_sdk:
        stripe_sdk.api_key = STRIPE_SECRET_KEY
        return stripe_sdk.Webhook.construct_event(payload, sig_header, secret)

    elements = dict(pair.split("=", 1) for pair in sig_header.split(",") if "=" in pair)
    timestamp = elements.get("t", "")
    signatures = [v for k, v in elements.items() if k == "v1"]
    if not timestamp or not signatures:
        raise ValueError("Missing Stripe signature components")
    if abs(time.time() - int(timestamp)) > STRIPE_WEBHOOK_TOLERANCE_SEC:
        raise ValueError("Stripe webhook timestamp too old")

    signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
    expected = hmac.new(
        secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        raise ValueError("Stripe signature verification failed")

    event = json.loads(payload)
    if not isinstance(event, dict) or not event.get("id") or not event.get("type"):
        raise ValueError("Malformed Stripe event payload")
    return event


def _stripe_db_required() -> None:
    from infra import postgres
    if postgres.pool() is None:
        raise RuntimeError(
            "DATABASE_URL is required when Stripe webhooks are enabled "
            "(payment ledger requires PostgreSQL)"
        )


async def _stripe_webhook_handler(request: web.Request) -> web.Response:
    from infra.payments.metrics import webhook_timer

    with webhook_timer():
        return await _stripe_webhook_handler_inner(request)


async def _stripe_webhook_handler_inner(request: web.Request) -> web.Response:
    from infra.payments.metrics import inc

    if not STRIPE_WEBHOOK_SECRET:
        return web.json_response({"error": "Webhook secret not configured"}, status=500)

    try:
        _stripe_db_required()
    except RuntimeError as exc:
        log.error("Stripe webhook rejected — %s", exc)
        inc("webhook_rejected")
        return web.json_response({"error": "Payment backend unavailable"}, status=503)

    if request.content_length and request.content_length > STRIPE_WEBHOOK_MAX_BODY_BYTES:
        return web.json_response({"error": "Payload too large"}, status=413)

    payload = await request.read()
    if len(payload) > STRIPE_WEBHOOK_MAX_BODY_BYTES:
        return web.json_response({"error": "Payload too large"}, status=413)

    sig_header = request.headers.get("Stripe-Signature", "")
    if not sig_header:
        return web.json_response({"error": "Missing Stripe-Signature header"}, status=400)

    try:
        event = _verify_stripe_signature(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError as exc:
        log.warning("Stripe signature verification failed: %s", exc)
        inc("webhook_invalid_signature")
        return web.json_response({"error": "Invalid signature"}, status=400)
    except json.JSONDecodeError:
        inc("webhook_invalid_signature")
        return web.json_response({"error": "Invalid payload"}, status=400)
    except Exception:
        log.exception("Unexpected error verifying Stripe webhook")
        inc("webhook_invalid_signature")
        return web.json_response({"error": "Verification error"}, status=400)

    event_id = str(event.get("id", "")).strip()
    event_type = str(event.get("type", "")).strip()
    if not event_id or not event_type:
        return web.json_response({"error": "Malformed event"}, status=400)

    if event_type not in ALLOWED_STRIPE_EVENT_TYPES:
        log.warning("Stripe event type not allowlisted: %s (event=%s)", event_type, event_id)
        inc("webhook_rejected")
        return web.json_response({"error": "Event type not accepted"}, status=400)

    trace_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    log.info("Stripe webhook received: type=%s event_id=%s trace=%s", event_type, event_id, trace_id)

    if event_type == "invoice.payment_succeeded":
        return web.json_response({"status": "ignored"})

    try:
        result = await process_stripe_event(
            event,
            trace_id=trace_id,
            price_to_tier=PRICE_TO_TIER,
            package_defaults=PACKAGE_DEFAULTS,
            stripe_sdk=stripe_sdk if _HAS_STRIPE else None,
            stripe_secret_key=STRIPE_SECRET_KEY,
        )
    except Exception:
        log.exception("Payment ledger error event_id=%s type=%s", event_id, event_type)
        await mark_failed(event_id, "ledger processing exception")
        inc("webhook_failed")
        return web.json_response({"error": "Processing failed"}, status=500)

    if result == "duplicate":
        return web.json_response({"status": "already_processed"})
    if result == "in_flight":
        return web.json_response({"status": "in_flight"})
    if result == "ignored":
        return web.json_response({"status": "ignored"})
    return web.json_response({"status": "ok"})


async def _health_handler(request: web.Request) -> web.Response:
    from infra import postgres
    return web.json_response({
        "status": "healthy",
        "service": "tiffany-stripe-webhook",
        "database": postgres.db_enabled() and postgres.pool() is not None,
        "metrics": payment_metrics_snapshot(),
    })


async def _metrics_handler(request: web.Request) -> web.Response:
    return web.json_response(payment_metrics_snapshot())


_runner: Optional[web.AppRunner] = None
_reconcile_task: Optional[Any] = None


async def _reconciliation_loop() -> None:
    import asyncio
    while True:
        try:
            await asyncio.sleep(STRIPE_RECONCILE_INTERVAL_SEC)
            await run_reconciliation(
                stripe_sdk=stripe_sdk if _HAS_STRIPE else None,
                stripe_secret_key=STRIPE_SECRET_KEY,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Reconciliation loop error")


async def start_stripe_server(bot: Any) -> None:
    global _runner, _reconcile_task

    if not STRIPE_SECRET_KEY or not STRIPE_WEBHOOK_SECRET:
        log.info("Stripe not configured — webhook server disabled")
        return

    from infra import postgres
    if not postgres.db_enabled() or postgres.pool() is None:
        log.error("Stripe configured but DATABASE_URL/pool unavailable — refusing webhook server")
        return

    if _runner is not None:
        return

    _load_price_map()
    if not PRICE_TO_TIER:
        log.warning("STRIPE_PRICE_MAP empty — unknown prices will be rejected (fail-closed)")

    if _HAS_STRIPE:
        stripe_sdk.api_key = STRIPE_SECRET_KEY

    app = web.Application()
    app.router.add_post("/stripe/webhook", _stripe_webhook_handler)
    app.router.add_get("/health", _health_handler)
    app.router.add_get("/metrics", _metrics_handler)

    _runner = web.AppRunner(app)
    await _runner.setup()
    site = web.TCPSite(_runner, "0.0.0.0", STRIPE_WEBHOOK_PORT)
    await site.start()

    start_payment_worker(bot)
    import asyncio
    _reconcile_task = asyncio.create_task(_reconciliation_loop(), name="tiffany-payment-reconcile")

    log.info("Stripe webhook server started on port %d (Phase III ledger)", STRIPE_WEBHOOK_PORT)


async def stop_stripe_server() -> None:
    global _runner, _reconcile_task

    if _reconcile_task and not _reconcile_task.done():
        _reconcile_task.cancel()
        try:
            await _reconcile_task
        except Exception:
            pass
    _reconcile_task = None

    await stop_payment_worker()

    if _runner is not None:
        await _runner.cleanup()
        _runner = None
        log.info("Stripe webhook server stopped")


async def create_checkout_url(
    *,
    price_id: str,
    package: str,
    discord_user_id: int,
    discord_guild_id: int,
    success_url: str = "https://discord.com/channels/@me",
    cancel_url: str = "https://discord.com/channels/@me",
) -> Optional[str]:
    if not _HAS_STRIPE or not STRIPE_SECRET_KEY:
        log.warning("Cannot create checkout URL — Stripe not configured")
        return None
    if package not in PACKAGE_DEFAULTS and package not in ("plus", "pro", "offers", "news", "ultimate"):
        log.warning("Unknown checkout package: %s", package)
        return None

    stripe_sdk.api_key = STRIPE_SECRET_KEY
    try:
        session = stripe_sdk.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            metadata={
                "discord_user_id": str(discord_user_id),
                "discord_guild_id": str(discord_guild_id),
                "subject_type": "guild",
                "package": package,
                "price_id": price_id,
            },
            success_url=success_url,
            cancel_url=cancel_url,
            allow_promotion_codes=True,
        )
        return session.url
    except Exception:
        log.exception("Failed to create Stripe checkout session")
        return None
