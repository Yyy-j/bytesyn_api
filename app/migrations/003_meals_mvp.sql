-- Additive compatibility migration. No historical rows are rewritten/deleted.
BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE IF NOT EXISTS meals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pair_id UUID REFERENCES pairs(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    calories NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (calories >= 0),
    protein NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (protein >= 0),
    carbs NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (carbs >= 0),
    fat NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (fat >= 0),
    source VARCHAR(30) NOT NULL DEFAULT 'manual',
    portion_ratio NUMERIC NOT NULL DEFAULT 1 CHECK (portion_ratio > 0),
    share_ratio NUMERIC NOT NULL DEFAULT 1 CHECK (share_ratio BETWEEN 0 AND 1),
    share_mode VARCHAR(30) NOT NULL DEFAULT 'solo',
    shared_meal_id UUID,
    meal_date DATE NOT NULL,
    meal_time TIME,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE meals ADD COLUMN IF NOT EXISTS base_calories NUMERIC;
ALTER TABLE meals ADD COLUMN IF NOT EXISTS base_protein NUMERIC;
ALTER TABLE meals ADD COLUMN IF NOT EXISTS base_carbs NUMERIC;
ALTER TABLE meals ADD COLUMN IF NOT EXISTS base_fat NUMERIC;
-- Internal perspective of the original creator, including partner_only rows.
-- Historical rows stay NULL: edits requiring this information return 409.
ALTER TABLE meals ADD COLUMN IF NOT EXISTS share_owner_id UUID REFERENCES users(id);

-- Widen only: retain all existing values, defaults, nullability and checks.
ALTER TABLE meals ALTER COLUMN base_calories TYPE NUMERIC;
ALTER TABLE meals ALTER COLUMN base_protein TYPE NUMERIC;
ALTER TABLE meals ALTER COLUMN base_carbs TYPE NUMERIC;
ALTER TABLE meals ALTER COLUMN base_fat TYPE NUMERIC;
ALTER TABLE meals ALTER COLUMN portion_ratio TYPE NUMERIC;
ALTER TABLE meals ALTER COLUMN share_ratio TYPE NUMERIC;

CREATE INDEX IF NOT EXISTS idx_meals_pair_date_time
    ON meals (pair_id, meal_date, meal_time);
CREATE INDEX IF NOT EXISTS idx_meals_shared_meal
    ON meals (shared_meal_id) WHERE shared_meal_id IS NOT NULL;

INSERT INTO schema_migrations (version) VALUES ('003_meals_mvp')
ON CONFLICT (version) DO NOTHING;
COMMIT;
