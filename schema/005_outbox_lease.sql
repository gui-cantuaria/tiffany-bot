-- Phase XI — outbox lease/claim for safe concurrent delivery
-- At-least-once external side effects; exactly-once internal state transitions per lease.

ALTER TABLE payment_outbox DROP CONSTRAINT IF EXISTS payment_outbox_status_check;
ALTER TABLE payment_outbox ADD CONSTRAINT payment_outbox_status_check
    CHECK (status IN ('pending', 'processing', 'delivered', 'failed', 'dead_letter'));

ALTER TABLE payment_outbox ADD COLUMN IF NOT EXISTS lease_owner TEXT;
ALTER TABLE payment_outbox ADD COLUMN IF NOT EXISTS lease_until TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS payment_outbox_processing_lease
    ON payment_outbox (status, lease_until)
    WHERE status = 'processing';
