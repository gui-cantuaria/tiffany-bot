-- ============================================================================
-- Tiffany Bot — Stripe Premium Subscriptions & Advanced Guild Config
-- Migration 002: stripe_premium.sql
-- Apply via infra.postgres.run_migrations() on bot startup.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Extend 'subscriptions' table with Stripe-specific columns
-- ---------------------------------------------------------------------------

-- New tiers for the Decoy-Priced packages.
-- We ALTER the existing CHECK constraint to accept the new tiers.
-- (safe to run multiple times: DO block is idempotent)
DO $$
BEGIN
    -- Drop old constraint if it exists
    ALTER TABLE subscriptions DROP CONSTRAINT IF EXISTS subscriptions_tier_check;
    -- Re-create with new tiers
    ALTER TABLE subscriptions ADD CONSTRAINT subscriptions_tier_check
        CHECK (tier IN ('free', 'premium', 'premium_plus', 'offers', 'news', 'ultimate'));
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'subscriptions_tier_check: %', SQLERRM;
END $$;

-- Add source = 'stripe' support (the existing CHECK on source is implicit via TEXT; no constraint to alter).

-- Stripe-specific columns (idempotent — IF NOT EXISTS / safe DO blocks)
DO $$
BEGIN
    ALTER TABLE subscriptions ADD COLUMN stripe_customer_id   TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE subscriptions ADD COLUMN stripe_subscription_id TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE subscriptions ADD COLUMN stripe_price_id TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE subscriptions ADD COLUMN cancelled_at TIMESTAMPTZ;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- Index for fast Stripe webhook lookups by subscription ID
CREATE INDEX IF NOT EXISTS subscriptions_stripe_sub
    ON subscriptions (stripe_subscription_id) WHERE stripe_subscription_id IS NOT NULL;

-- Index for Stripe customer lookups
CREATE INDEX IF NOT EXISTS subscriptions_stripe_cust
    ON subscriptions (stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- 2. guild_premium_config — Advanced JSONB configuration per guild
-- ---------------------------------------------------------------------------
-- Stores the rich, nested configuration that Premium guild owners can tweak
-- via the Discord UI panel (Phase 2).

CREATE TABLE IF NOT EXISTS guild_premium_config (
    guild_id        BIGINT PRIMARY KEY,
    -- Who purchased premium for this guild (Discord user ID)
    purchaser_id    BIGINT NOT NULL,
    -- The active package tier for this guild
    package         TEXT NOT NULL DEFAULT 'free'
                    CHECK (package IN ('free', 'offers', 'news', 'ultimate')),

    -- ===================================================================
    -- JSONB config blob — the "mega settings dictionary"
    -- ===================================================================
    -- Structure (all keys optional, defaults applied in Python):
    --
    -- offers: {
    --   min_discount_pct:     int (0-100, default 0),
    --   categories_whitelist: [str] (empty = all),
    --   keywords_blacklist:   [str],
    --   embed_layout: {
    --     button_position:  "top" | "bottom" (default "bottom"),
    --     title_max_chars:  int (default 256),
    --     title_max_words:  int (default 0=unlimited),
    --     show_affiliate:   bool (default true),
    --   },
    --   nsfw_enabled:         bool (default false),
    --   affiliate_override:   bool (default false → 70/30; true → 100% user),
    -- }
    --
    -- news: {
    --   custom_rss_urls:      [str] (max 10),
    --   category_routing: {
    --     "<category>": <channel_id>
    --   },
    --   auto_translate:       bool (default false),
    --   nsfw_enabled:         bool (default false),
    --   anti_bot_bypass:      bool (default false),
    -- }
    --
    -- ai_guardrails: {
    --   block_illegal:        bool (default true, cannot be disabled),
    --   nsfw_mode:            "block" | "tag" | "allow" (default "block"),
    -- }
    --
    -- music: {
    --   vip_enabled:          bool (default false),
    --   max_queue:            int (default 50, ultimate=500),
    --   nonstop_24_7:         bool (default false),
    -- }
    --
    -- ai_limits: {
    --   daily_quota:          int (default 20, ultimate=500),
    --   model_tier:           "fast" | "balanced" | "premium" (default "fast"),
    -- }
    config          JSONB NOT NULL DEFAULT '{}',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for JSONB queries (e.g., finding all guilds with NSFW enabled)
CREATE INDEX IF NOT EXISTS guild_premium_config_package
    ON guild_premium_config (package) WHERE package != 'free';


-- ---------------------------------------------------------------------------
-- 3. stripe_events — Idempotency log for webhook events
-- ---------------------------------------------------------------------------
-- Stripe can re-deliver the same event multiple times. This table ensures
-- we never process the same event_id twice.

CREATE TABLE IF NOT EXISTS stripe_events (
    event_id        TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Auto-prune events older than 90 days (run via cron or pg_cron)
-- DELETE FROM stripe_events WHERE processed_at < now() - INTERVAL '90 days';
