-- ============================================================================
-- Tiffany Bot — AI Quota Tracking
-- Migration 003: ai_quota.sql
-- Apply via infra.postgres.run_migrations() on bot startup.
-- ============================================================================

-- Add the 'quota_used' column to track dynamic AI Quota Units based on models
DO $$
BEGIN
    ALTER TABLE ai_usage_daily ADD COLUMN quota_used BIGINT NOT NULL DEFAULT 0;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- Telemetry AI usage table
CREATE TABLE IF NOT EXISTS telemetry_ai_usage (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    guild_id    TEXT,
    model       TEXT NOT NULL,
    tokens      BIGINT NOT NULL DEFAULT 0,
    latency_ms  BIGINT NOT NULL DEFAULT 0,
    quota_used  BIGINT NOT NULL DEFAULT 0,
    cache_hit   BOOLEAN NOT NULL DEFAULT FALSE,
    success     BOOLEAN NOT NULL DEFAULT TRUE,
    error_msg   TEXT DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_telemetry_created_at ON telemetry_ai_usage (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_user_id ON telemetry_ai_usage (user_id);
