-- Tiffany Bot core schema (PostgreSQL 14+)
-- Apply via infra.postgres.run_migrations() on bot startup when DATABASE_URL is set.

CREATE TABLE IF NOT EXISTS subscriptions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_type    TEXT NOT NULL CHECK (subject_type IN ('user', 'guild')),
    subject_id      BIGINT NOT NULL,
    tier            TEXT NOT NULL DEFAULT 'free' CHECK (tier IN ('free', 'premium', 'premium_plus')),
    source          TEXT NOT NULL DEFAULT 'grant',
    external_id     TEXT,
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS subscriptions_subject_source
    ON subscriptions (subject_type, subject_id, source);

CREATE INDEX IF NOT EXISTS subscriptions_expires
    ON subscriptions (expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS guild_features (
    guild_id        BIGINT PRIMARY KEY,
    max_queue       INT NOT NULL DEFAULT 50,
    custom_embeds   INT NOT NULL DEFAULT 5,
    giveaway_boost  BOOLEAN NOT NULL DEFAULT false,
    ai_daily_quota  INT NOT NULL DEFAULT 20,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_cosmetics (
    user_id         BIGINT PRIMARY KEY,
    badge_id        TEXT,
    profile_frame   TEXT,
    purchased_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_usage_daily (
    subject_type    TEXT NOT NULL,
    subject_id      BIGINT NOT NULL,
    day             DATE NOT NULL,
    calls           INT NOT NULL DEFAULT 0,
    tokens_in       BIGINT NOT NULL DEFAULT 0,
    tokens_out      BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (subject_type, subject_id, day)
);

CREATE TABLE IF NOT EXISTS giveaways (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guild_id        BIGINT NOT NULL,
    channel_id      BIGINT NOT NULL,
    message_id      BIGINT,
    host_id         BIGINT NOT NULL,
    prize           TEXT NOT NULL,
    winner_count    INT NOT NULL DEFAULT 1,
    ends_at         TIMESTAMPTZ NOT NULL,
    requirements    JSONB NOT NULL DEFAULT '{}',
    embed_style     JSONB NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'ended', 'cancelled')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS giveaways_active_ends
    ON giveaways (status, ends_at) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS giveaway_entries (
    giveaway_id     UUID NOT NULL REFERENCES giveaways(id) ON DELETE CASCADE,
    user_id         BIGINT NOT NULL,
    entered_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (giveaway_id, user_id)
);

CREATE TABLE IF NOT EXISTS embed_templates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guild_id        BIGINT NOT NULL,
    name            TEXT NOT NULL,
    payload         JSONB NOT NULL,
    created_by      BIGINT NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (guild_id, name)
);

CREATE TABLE IF NOT EXISTS i18n_keys (
    key             TEXT PRIMARY KEY,
    namespace       TEXT NOT NULL DEFAULT 'core',
    description     TEXT
);

CREATE TABLE IF NOT EXISTS i18n_strings (
    key_id          TEXT NOT NULL REFERENCES i18n_keys(key) ON DELETE CASCADE,
    lang            VARCHAR(5) NOT NULL,
    value           TEXT NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (key_id, lang)
);

CREATE INDEX IF NOT EXISTS i18n_strings_lang ON i18n_strings (lang);

CREATE TABLE IF NOT EXISTS automod_events (
    id              BIGSERIAL PRIMARY KEY,
    guild_id        BIGINT NOT NULL,
    user_id         BIGINT NOT NULL,
    channel_id      BIGINT,
    layer           TEXT NOT NULL,
    action          TEXT NOT NULL,
    reason          TEXT,
    content_snip    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS automod_events_guild_time
    ON automod_events (guild_id, created_at DESC);
