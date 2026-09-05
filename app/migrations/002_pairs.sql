BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE users ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE users ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE users ALTER COLUMN updated_at SET DEFAULT now();

CREATE TABLE IF NOT EXISTS pairs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invite_code TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pairs_invite_code_key UNIQUE (invite_code)
);

CREATE TABLE IF NOT EXISTS pair_members (
    pair_id UUID NOT NULL REFERENCES pairs(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (pair_id, user_id),
    CONSTRAINT pair_members_user_id_key UNIQUE (user_id)
);

CREATE INDEX IF NOT EXISTS pair_members_pair_id_idx ON pair_members(pair_id);

INSERT INTO schema_migrations (version)
VALUES ('002_pairs')
ON CONFLICT (version) DO NOTHING;

COMMIT;