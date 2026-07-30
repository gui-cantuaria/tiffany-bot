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
