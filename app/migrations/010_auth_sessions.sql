-- Rotating refresh sessions with a 72-hour sliding inactivity window.
BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE IF NOT EXISTS auth_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT auth_sessions_token_hash_key UNIQUE (token_hash),
    CONSTRAINT auth_sessions_token_hash_format_check
        CHECK (token_hash ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS auth_sessions_user_active_idx
    ON auth_sessions (user_id, expires_at DESC)
    WHERE revoked_at IS NULL;

INSERT INTO schema_migrations (version) VALUES ('010_auth_sessions')
ON CONFLICT (version) DO NOTHING;
COMMIT;
