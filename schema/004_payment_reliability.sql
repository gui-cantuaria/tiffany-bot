-- ============================================================================
-- Tiffany Payments Phase III — State machine, audit trail, transactional outbox
-- Apply via infra.postgres.run_migrations() on bot startup.
-- ============================================================================

-- Extend stripe_events into a durable processing ledger
DO $$
BEGIN
    ALTER TABLE stripe_events ADD COLUMN status TEXT NOT NULL DEFAULT 'completed';
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE stripe_events ADD COLUMN correlation_id UUID;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE stripe_events ADD COLUMN trace_id TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE stripe_events ADD COLUMN attempt_count INT NOT NULL DEFAULT 1;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE stripe_events ADD COLUMN last_error TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE stripe_events ADD COLUMN received_at TIMESTAMPTZ NOT NULL DEFAULT now();
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE stripe_events ADD COLUMN completed_at TIMESTAMPTZ;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE stripe_events ADD COLUMN payload_hash TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS stripe_events_status_received
    ON stripe_events (status, received_at);

-- Immutable financial audit trail (append-only by convention)
CREATE TABLE IF NOT EXISTS payment_audit_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor               TEXT NOT NULL DEFAULT 'system',
    provider_event_id   TEXT,
    correlation_id      UUID,
    trace_id            TEXT,
    guild_id            BIGINT,
    user_id             BIGINT,
    stripe_subscription_id TEXT,
    action              TEXT NOT NULL,
    previous_state      JSONB,
    new_state           JSONB,
    reason              TEXT,
    result              TEXT NOT NULL DEFAULT 'ok',
    metadata            JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS payment_audit_log_event
    ON payment_audit_log (provider_event_id) WHERE provider_event_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS payment_audit_log_guild
    ON payment_audit_log (guild_id, created_at DESC) WHERE guild_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS payment_audit_log_correlation
    ON payment_audit_log (correlation_id) WHERE correlation_id IS NOT NULL;

-- Transactional outbox for non-transactional side effects (Discord, email, etc.)
CREATE TABLE IF NOT EXISTS payment_outbox (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    provider_event_id   TEXT,
    correlation_id      UUID,
    trace_id            TEXT,
    delivery_type       TEXT NOT NULL,
    payload             JSONB NOT NULL DEFAULT '{}',
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'delivered', 'failed', 'dead_letter')),
    attempt_count       INT NOT NULL DEFAULT 0,
    next_retry_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at        TIMESTAMPTZ,
    last_error          TEXT
);

CREATE INDEX IF NOT EXISTS payment_outbox_pending
    ON payment_outbox (status, next_retry_at) WHERE status = 'pending';

-- Reconciliation run history
CREATE TABLE IF NOT EXISTS payment_reconciliation_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    status              TEXT NOT NULL DEFAULT 'running',
    drift_count         INT NOT NULL DEFAULT 0,
    corrections         JSONB NOT NULL DEFAULT '[]',
    summary             JSONB NOT NULL DEFAULT '{}'
);
