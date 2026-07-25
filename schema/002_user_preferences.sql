-- Per-user Tiffany preferences (language is scoped strictly to Discord user_id).

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id         BIGINT PRIMARY KEY,
    lang            VARCHAR(5) NOT NULL CHECK (
        lang IN ('en', 'pt', 'es', 'fr', 'de', 'tr', 'sv', 'it', 'nl', 'ar', 'ja', 'ko', 'ru')
    ),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS user_preferences_lang ON user_preferences (lang);
