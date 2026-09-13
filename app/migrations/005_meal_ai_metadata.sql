-- Additive Meal AI metadata. No image bytes or historical rows are changed.
BEGIN;

ALTER TABLE meals ADD COLUMN IF NOT EXISTS dishes JSONB DEFAULT '[]'::jsonb;
ALTER TABLE meals ADD COLUMN IF NOT EXISTS ai_hint TEXT;
ALTER TABLE meals ADD COLUMN IF NOT EXISTS original_input TEXT;
ALTER TABLE meals ALTER COLUMN dishes SET DEFAULT '[]'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'meals'::regclass AND conname = 'meals_dishes_array'
    ) THEN
        ALTER TABLE meals ADD CONSTRAINT meals_dishes_array
            CHECK (dishes IS NULL OR jsonb_typeof(dishes) = 'array');
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_meals_user_date_time
    ON meals (user_id, meal_date, meal_time DESC);

INSERT INTO schema_migrations (version) VALUES ('005_meal_ai_metadata')
ON CONFLICT (version) DO NOTHING;
COMMIT;
