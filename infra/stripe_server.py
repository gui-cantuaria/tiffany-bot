"""
Tiffany Bot — Internal Stripe Webhook Server
=============================================
Embeds an aiohttp.web server into the discord.py event loop to receive
Stripe webhook events without blocking the bot or requiring external infra.

Architecture:
    discord.py bot loop
        └── aiohttp.web.AppRunner (port 8080)
                └── POST /stripe/webhook  →  verify signature  →  update DB  →  invalidate cache

Environment Variables:
    STRIPE_SECRET_KEY       — sk_live_... or sk_test_...
    STRIPE_WEBHOOK_SECRET   — whsec_... (from Stripe Dashboard → Webhooks)
    STRIPE_WEBHOOK_PORT     — Port to listen on (default: 8080)

Supported Stripe Events:
    checkout.session.completed      — New subscription purchased
    customer.subscription.updated   — Plan change, renewal, payment method update
    customer.subscription.deleted   — Subscription cancelled / expired
    invoice.payment_succeeded       — Recurring payment confirmed
    invoice.payment_failed          — Payment failed (grace period)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

from aiohttp import web

log = logging.getLogger("tiffany-bot")

# ---------------------------------------------------------------------------
# Stripe SDK — import or stub
# ---------------------------------------------------------------------------
try:
    import stripe as stripe_sdk
    _HAS_STRIPE = True
except ImportError:
    _HAS_STRIPE = False
    stripe_sdk = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_WEBHOOK_PORT = int(os.getenv("STRIPE_WEBHOOK_PORT", "8080"))

# Map Stripe Price IDs → internal tier names.
# Configure these in .env or hardcode after creating products in Stripe.
PRICE_TO_TIER: dict[str, str] = {}

def _load_price_map() -> None:
    """Load STRIPE_PRICE_MAP from env (JSON dict) or individual vars."""
    global PRICE_TO_TIER
    raw = os.getenv("STRIPE_PRICE_MAP", "").strip()
    if raw:
        try:
            PRICE_TO_TIER = json.loads(raw)
            return
        except json.JSONDecodeError:
            log.warning("STRIPE_PRICE_MAP is not valid JSON, falling back to individual vars")

    # Fallback: individual env vars
    for env_key, tier in [
        ("STRIPE_PRICE_OFFERS", "offers"),
        ("STRIPE_PRICE_NEWS", "news"),
        ("STRIPE_PRICE_ULTIMATE", "ultimate"),
    ]:
        price_id = os.getenv(env_key, "").strip()
        if price_id:
            PRICE_TO_TIER[price_id] = tier


# ---------------------------------------------------------------------------
# Package defaults — applied when a guild upgrades
# ---------------------------------------------------------------------------
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
            "affiliate_override": True,   # 100% commission for premium
        },
        "ai_guardrails": {
            "block_illegal": True,
            "nsfw_mode": "block",
        },
    },
    "news": {
        "news": {
            "custom_rss_urls": [],
            "category_routing": {},
            "auto_translate": False,
            "nsfw_enabled": False,
            "anti_bot_bypass": True,
        },
        "ai_guardrails": {
            "block_illegal": True,
            "nsfw_mode": "block",
        },
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
        "ai_guardrails": {
            "block_illegal": True,
            "nsfw_mode": "block",
        },
        "music": {
            "vip_enabled": True,
            "max_queue": 500,
            "nonstop_24_7": True,
        },
        "ai_limits": {
            "daily_quota": 500,
            "model_tier": "premium",
        },
    },
}


# ---------------------------------------------------------------------------
# Stripe signature verification (no SDK dependency for this part)
# ---------------------------------------------------------------------------
def _verify_stripe_signature(payload: bytes, sig_header: str, secret: str) -> dict:
    """
    Verify Stripe webhook signature and return the parsed event.
    Raises ValueError on failure.
    """
    if _HAS_STRIPE and stripe_sdk:
        stripe_sdk.api_key = STRIPE_SECRET_KEY
        return stripe_sdk.Webhook.construct_event(payload, sig_header, secret)

    # Manual verification fallback (no stripe SDK installed)
    elements = dict(pair.split("=", 1) for pair in sig_header.split(",") if "=" in pair)
    timestamp = elements.get("t", "")
    signatures = [v for k, v in elements.items() if k == "v1"]

    if not timestamp or not signatures:
        raise ValueError("Missing Stripe signature components")

    # Tolerance: 5 minutes
    if abs(time.time() - int(timestamp)) > 300:
        raise ValueError("Stripe webhook timestamp too old")

    signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
    expected = hmac.new(
        secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        raise ValueError("Stripe signature verification failed")

    return json.loads(payload)


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------
async def _is_event_processed(event_id: str) -> bool:
    """Check idempotency — has this event already been handled?"""
    from infra import postgres
    pool = postgres.pool()
    if pool is None:
        return False
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM stripe_events WHERE event_id = $1", event_id
            )
            return row is not None
    except Exception:
        return False


async def _mark_event_processed(event_id: str, event_type: str) -> None:
    """Record event as processed for idempotency."""
    from infra import postgres
    pool = postgres.pool()
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO stripe_events (event_id, event_type)
                   VALUES ($1, $2) ON CONFLICT DO NOTHING""",
                event_id, event_type,
            )
    except Exception as e:
        log.warning("Failed to mark Stripe event %s: %s", event_id, e)


async def _upsert_subscription(
    *,
    subject_type: str,
    subject_id: int,
    tier: str,
    stripe_customer_id: str,
    stripe_subscription_id: str,
    stripe_price_id: str,
    expires_at: Optional[datetime] = None,
) -> None:
    """Create or update a subscription row from a Stripe event."""
    from infra import postgres, premium
    pool = postgres.pool()
    if pool is None:
        log.warning("No DB pool — cannot upsert Stripe subscription")
        return

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO subscriptions
                    (subject_type, subject_id, tier, source, external_id,
                     stripe_customer_id, stripe_subscription_id, stripe_price_id,
                     expires_at)
                VALUES ($1, $2, $3, 'stripe', $4, $5, $6, $7, $8)
                ON CONFLICT (subject_type, subject_id, source)
                DO UPDATE SET
                    tier = EXCLUDED.tier,
                    stripe_customer_id = EXCLUDED.stripe_customer_id,
                    stripe_subscription_id = EXCLUDED.stripe_subscription_id,
                    stripe_price_id = EXCLUDED.stripe_price_id,
                    expires_at = EXCLUDED.expires_at,
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
                expires_at,
            )
        log.info(
            "Stripe subscription upserted: %s %d → tier=%s (sub=%s)",
            subject_type, subject_id, tier, stripe_subscription_id,
        )
    except Exception as e:
        log.exception("Failed to upsert Stripe subscription: %s", e)
        return

    # Invalidate cache so next premium check reads fresh from DB
    if subject_type == "guild":
        await premium.invalidate_entitlement(guild_id=subject_id)
    else:
        await premium.invalidate_entitlement(user_id=subject_id)


async def _cancel_subscription(stripe_subscription_id: str) -> None:
    """Mark a subscription as cancelled."""
    from infra import postgres, premium
    pool = postgres.pool()
    if pool is None:
        return

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE subscriptions
                SET cancelled_at = now(), tier = 'free', updated_at = now()
                WHERE stripe_subscription_id = $1
                RETURNING subject_type, subject_id
                """,
                stripe_subscription_id,
            )
            if row:
                if row["subject_type"] == "guild":
                    await premium.invalidate_entitlement(guild_id=row["subject_id"])
                else:
                    await premium.invalidate_entitlement(user_id=row["subject_id"])
                log.info(
                    "Stripe subscription cancelled: %s %d (sub=%s)",
                    row["subject_type"], row["subject_id"], stripe_subscription_id,
                )
            else:
                log.warning("Stripe cancel: subscription %s not found in DB", stripe_subscription_id)
    except Exception as e:
        log.exception("Failed to cancel Stripe subscription: %s", e)


async def _provision_guild_config(guild_id: int, purchaser_id: int, package: str) -> None:
    """Create or update the guild_premium_config row with package defaults."""
    from infra import postgres
    pool = postgres.pool()
    if pool is None:
        return

    defaults = PACKAGE_DEFAULTS.get(package, {})
    try:
        async with pool.acquire() as conn:
            # Merge with existing config (don't overwrite user customizations)
            existing = await conn.fetchval(
                "SELECT config FROM guild_premium_config WHERE guild_id = $1",
                guild_id,
            )
            if existing:
                # Deep merge: keep existing keys, add missing defaults
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
                    config = $4::jsonb,
                    updated_at = now()
                """,
                guild_id,
                purchaser_id,
                package,
                json.dumps(merged),
            )
        log.info("Guild %d provisioned with package '%s'", guild_id, package)
    except Exception as e:
        log.exception("Failed to provision guild config: %s", e)


# ---------------------------------------------------------------------------
# Extract Discord metadata from Stripe checkout session
# ---------------------------------------------------------------------------
def _extract_discord_metadata(session: dict) -> tuple[str, int, int]:
    """
    Pull subject_type, subject_id, and guild_id from checkout metadata.
    The /premium command embeds these when creating the Stripe Checkout URL.

    Expected metadata keys:
        discord_user_id: str (the buyer)
        discord_guild_id: str (target guild)
        subject_type: "guild" | "user" (default "guild")
    """
    meta = session.get("metadata", {}) or {}
    subject_type = meta.get("subject_type", "guild")
    guild_id = int(meta.get("discord_guild_id", "0"))
    user_id = int(meta.get("discord_user_id", "0"))

    if subject_type == "guild" and guild_id:
        return "guild", guild_id, user_id
    elif user_id:
        return "user", user_id, user_id
    else:
        raise ValueError(f"Missing discord metadata in checkout session: {meta}")


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------
async def _handle_checkout_completed(event: dict) -> None:
    """checkout.session.completed — A new subscription was purchased."""
    session = event.get("data", {}).get("object", {})
    if session.get("mode") != "subscription":
        log.debug("Ignoring non-subscription checkout: %s", session.get("mode"))
        return

    stripe_sub_id = session.get("subscription", "")
    stripe_cust_id = session.get("customer", "")

    subject_type, subject_id, purchaser_id = _extract_discord_metadata(session)

    # Resolve tier from line items or metadata
    tier = "premium"  # fallback
    meta = session.get("metadata", {}) or {}
    if "package" in meta:
        tier = meta["package"]
    # If Stripe SDK is available, fetch the actual price to resolve tier
    elif _HAS_STRIPE and stripe_sub_id:
        try:
            stripe_sdk.api_key = STRIPE_SECRET_KEY
            sub_obj = stripe_sdk.Subscription.retrieve(stripe_sub_id)
            if sub_obj.get("items", {}).get("data"):
                price_id = sub_obj["items"]["data"][0]["price"]["id"]
                tier = PRICE_TO_TIER.get(price_id, tier)
        except Exception as e:
            log.warning("Could not fetch Stripe subscription details: %s", e)

    await _upsert_subscription(
        subject_type=subject_type,
        subject_id=subject_id,
        tier=tier,
        stripe_customer_id=stripe_cust_id,
        stripe_subscription_id=stripe_sub_id,
        stripe_price_id=meta.get("price_id", ""),
        expires_at=None,  # Active sub — no expiry
    )

    # Provision guild config with package defaults
    if subject_type == "guild":
        await _provision_guild_config(subject_id, purchaser_id, tier)


async def _handle_subscription_updated(event: dict) -> None:
    """customer.subscription.updated — Plan change or renewal."""
    sub = event.get("data", {}).get("object", {})
    stripe_sub_id = sub.get("id", "")
    status = sub.get("status", "")

    if status in ("active", "trialing"):
        # Resolve new tier from price
        tier = "premium"
        if sub.get("items", {}).get("data"):
            price_id = sub["items"]["data"][0].get("price", {}).get("id", "")
            tier = PRICE_TO_TIER.get(price_id, tier)

        # We need to find the existing row to get discord IDs
        from infra import postgres
        pool = postgres.pool()
        if pool:
            try:
                async with pool.acquire() as conn:
                    row = await conn.fetchrow(
                        """SELECT subject_type, subject_id FROM subscriptions
                           WHERE stripe_subscription_id = $1""",
                        stripe_sub_id,
                    )
                    if row:
                        await _upsert_subscription(
                            subject_type=row["subject_type"],
                            subject_id=row["subject_id"],
                            tier=tier,
                            stripe_customer_id=sub.get("customer", ""),
                            stripe_subscription_id=stripe_sub_id,
                            stripe_price_id=sub["items"]["data"][0]["price"]["id"] if sub.get("items", {}).get("data") else "",
                        )
            except Exception as e:
                log.warning("subscription.updated handler error: %s", e)

    elif status in ("canceled", "unpaid", "past_due"):
        await _cancel_subscription(stripe_sub_id)


async def _handle_subscription_deleted(event: dict) -> None:
    """customer.subscription.deleted — Subscription cancelled or expired."""
    sub = event.get("data", {}).get("object", {})
    stripe_sub_id = sub.get("id", "")
    await _cancel_subscription(stripe_sub_id)


async def _handle_invoice_payment_failed(event: dict) -> None:
    """invoice.payment_failed — Payment failed; log but don't revoke immediately."""
    invoice = event.get("data", {}).get("object", {})
    stripe_sub_id = invoice.get("subscription", "")
    attempt = invoice.get("attempt_count", 0)
    log.warning(
        "Stripe payment failed for sub=%s (attempt %d). "
        "Stripe will retry automatically. No action taken yet.",
        stripe_sub_id, attempt,
    )


# Event dispatcher
_EVENT_HANDLERS: dict[str, Any] = {
    "checkout.session.completed": _handle_checkout_completed,
    "customer.subscription.updated": _handle_subscription_updated,
    "customer.subscription.deleted": _handle_subscription_deleted,
    "invoice.payment_failed": _handle_invoice_payment_failed,
    # invoice.payment_succeeded is implicit via subscription.updated → status=active
}


# ---------------------------------------------------------------------------
# aiohttp.web webhook endpoint
# ---------------------------------------------------------------------------
async def _stripe_webhook_handler(request: web.Request) -> web.Response:
    """POST /stripe/webhook — receives and processes Stripe events."""
    if not STRIPE_WEBHOOK_SECRET:
        return web.json_response({"error": "Webhook secret not configured"}, status=500)

    # Read raw body for signature verification
    payload = await request.read()
    sig_header = request.headers.get("Stripe-Signature", "")

    if not sig_header:
        return web.json_response({"error": "Missing Stripe-Signature header"}, status=400)

    try:
        event = _verify_stripe_signature(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError as e:
        log.warning("Stripe signature verification failed: %s", e)
        return web.json_response({"error": "Invalid signature"}, status=400)
    except Exception as e:
        log.exception("Unexpected error verifying Stripe webhook: %s", e)
        return web.json_response({"error": "Verification error"}, status=400)

    event_id = event.get("id", "")
    event_type = event.get("type", "")
    log.info("Stripe webhook received: %s (event=%s)", event_type, event_id)

    # Idempotency check
    if await _is_event_processed(event_id):
        log.debug("Stripe event %s already processed — skipping", event_id)
        return web.json_response({"status": "already_processed"})

    # Dispatch to handler
    handler = _EVENT_HANDLERS.get(event_type)
    if handler:
        try:
            await handler(event)
            await _mark_event_processed(event_id, event_type)
        except Exception as e:
            log.exception("Error handling Stripe event %s (%s): %s", event_id, event_type, e)
            # Return 500 so Stripe retries
            return web.json_response({"error": "Processing failed"}, status=500)
    else:
        log.debug("Unhandled Stripe event type: %s", event_type)

    return web.json_response({"status": "ok"})


async def _health_handler(request: web.Request) -> web.Response:
    """GET /health — Simple health check for monitoring."""
    return web.json_response({"status": "healthy", "service": "tiffany-stripe-webhook"})


# ---------------------------------------------------------------------------
# Server lifecycle — attach to discord.py bot loop
# ---------------------------------------------------------------------------
_runner: Optional[web.AppRunner] = None


async def start_stripe_server(bot: Any) -> None:
    """
    Start the internal aiohttp web server for Stripe webhooks.
    Call this from on_ready() or setup_hook() of the discord.py bot.

    Usage:
        from infra.stripe_server import start_stripe_server
        await start_stripe_server(bot)
    """
    global _runner

    if not STRIPE_SECRET_KEY or not STRIPE_WEBHOOK_SECRET:
        log.info("Stripe not configured (STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET missing) — webhook server disabled")
        return

    if _runner is not None:
        log.debug("Stripe webhook server already running")
        return

    _load_price_map()

    if _HAS_STRIPE:
        stripe_sdk.api_key = STRIPE_SECRET_KEY

    app = web.Application()
    app.router.add_post("/stripe/webhook", _stripe_webhook_handler)
    app.router.add_get("/health", _health_handler)

    _runner = web.AppRunner(app)
    await _runner.setup()

    site = web.TCPSite(_runner, "0.0.0.0", STRIPE_WEBHOOK_PORT)
    await site.start()

    log.info("🔗 Stripe webhook server started on port %d", STRIPE_WEBHOOK_PORT)


async def stop_stripe_server() -> None:
    """Gracefully shut down the webhook server. Call from on_close()."""
    global _runner
    if _runner is not None:
        await _runner.cleanup()
        _runner = None
        log.info("Stripe webhook server stopped")


# ---------------------------------------------------------------------------
# Utility: Create Stripe Checkout URL (used by /premium command in Phase 2)
# ---------------------------------------------------------------------------
async def create_checkout_url(
    *,
    price_id: str,
    package: str,
    discord_user_id: int,
    discord_guild_id: int,
    success_url: str = "https://discord.com/channels/@me",
    cancel_url: str = "https://discord.com/channels/@me",
) -> Optional[str]:
    """
    Generate a Stripe Checkout Session URL for a guild subscription.
    Returns the URL string or None if Stripe is not configured.
    """
    if not _HAS_STRIPE or not STRIPE_SECRET_KEY:
        log.warning("Cannot create checkout URL — Stripe SDK not available or key missing")
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
    except Exception as e:
        log.exception("Failed to create Stripe checkout session: %s", e)
        return None
