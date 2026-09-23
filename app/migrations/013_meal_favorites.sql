-- User-owned reusable meal snapshots.
BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE IF NOT EXISTS meal_favorites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_meal_id UUID REFERENCES meals(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    calories NUMERIC NOT NULL CHECK (calories >= 0),
    protein NUMERIC NOT NULL CHECK (protein >= 0),
    carbs NUMERIC NOT NULL CHECK (carbs >= 0),
    fat NUMERIC NOT NULL CHECK (fat >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT meal_favorites_user_source_key UNIQUE (user_id, source_meal_id)
);

CREATE INDEX IF NOT EXISTS meal_favorites_user_created_idx
    ON meal_favorites (user_id, created_at, id);

INSERT INTO schema_migrations (version) VALUES ('013_meal_favorites')
ON CONFLICT (version) DO NOTHING;
COMMIT;
