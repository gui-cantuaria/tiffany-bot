"""Payment processing constants — state machine, valid tiers, and decoupled financial bounds."""

from __future__ import annotations
import os

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
OUTBOX_PROCESSING = "processing"
OUTBOX_DELIVERED = "delivered"
OUTBOX_FAILED = "failed"
OUTBOX_DEAD_LETTER = "dead_letter"

STALE_PROCESSING_SEC = 600
OUTBOX_LEASE_SEC = 120
OUTBOX_STALE_LEASE_SEC = 300
MAX_OUTBOX_ATTEMPTS = 8

# Decoupled Independent Financial Rule Constants (Kantuaria Financial Model)
# Each business rule possesses its own semantic constant to prevent accidental coupling.
MIN_DEPOSIT_BRL = float(os.getenv("MIN_DEPOSIT_BRL", "10.00"))
MIN_WITHDRAWAL_BRL = float(os.getenv("MIN_WITHDRAWAL_BRL", "20.00"))
MAX_DAILY_WITHDRAWAL_BRL = float(os.getenv("MAX_DAILY_WITHDRAWAL_BRL", "5000.00"))
REFERRAL_QUALIFY_MIN_BRL = float(os.getenv("REFERRAL_QUALIFY_MIN_BRL", "15.00"))
BONUS_THRESHOLD_MIN_BRL = float(os.getenv("BONUS_THRESHOLD_MIN_BRL", "50.00"))
FEE_THRESHOLD_MIN_BRL = float(os.getenv("FEE_THRESHOLD_MIN_BRL", "100.00"))
