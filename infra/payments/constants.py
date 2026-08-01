"""Payment processing constants — state machine and valid tiers."""

from __future__ import annotations

# Stripe event processing lifecycle (persisted on stripe_events.status)
STATUS_RECEIVED = "received"
STATUS_VALIDATED = "validated"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_RETRY_PENDING = "retry_pending"
STATUS_DEAD_LETTER = "dead_letter"

TERMINAL_STATUSES = frozenset({STATUS_COMPLETED, STATUS_DEAD_LETTER})

# Internal subscription tiers — never grant unknown tiers.
VALID_TIERS = frozenset({
    "free",
    "premium",
    "premium_plus",
    "plus",
    "pro",
    "offers",
    "news",
    "ultimate",
})

# Paid package tiers mapped from Stripe products
PAID_PACKAGE_TIERS = frozenset({"offers", "news", "ultimate", "premium", "premium_plus"})

# Subscription statuses that revoke entitlements (past_due excluded — Stripe dunning grace)
REVOKE_SUBSCRIPTION_STATUSES = frozenset({"canceled", "unpaid", "incomplete_expired"})

OUTBOX_DISCORD_NOTIFY = "discord_notify"
OUTBOX_ANALYTICS = "analytics"

OUTBOX_PENDING = "pending"
OUTBOX_DELIVERED = "delivered"
OUTBOX_FAILED = "failed"
OUTBOX_DEAD_LETTER = "dead_letter"

STALE_PROCESSING_SEC = 600
MAX_OUTBOX_ATTEMPTS = 8
