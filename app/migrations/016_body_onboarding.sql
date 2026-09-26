-- Private body profile, onboarding state, and immutable-height weight history.
BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_completed_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_year INTEGER;
ALTER TABLE users ADD COLUMN IF NOT EXISTS sex_for_energy_estimate TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS height_cm NUMERIC;
ALTER TABLE users ADD COLUMN IF NOT EXISTS target_weight_kg NUMERIC;
ALTER TABLE users ADD COLUMN IF NOT EXISTS target_date DATE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS activity_level TEXT;

-- Only users that existed before this migration are grandfathered. On a
-- repeat run the marker already exists, so users created later remain pending.
UPDATE users
SET onboarding_completed_at = now()
WHERE onboarding_completed_at IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM schema_migrations
      WHERE version = '016_body_onboarding'
  );

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'users'::regclass
          AND conname = 'users_birth_year_range'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_birth_year_range
            CHECK (birth_year IS NULL OR birth_year BETWEEN 1900 AND 3000);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'users'::regclass
          AND conname = 'users_sex_for_energy_estimate_valid'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_sex_for_energy_estimate_valid
            CHECK (sex_for_energy_estimate IS NULL
                   OR sex_for_energy_estimate IN ('male', 'female'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'users'::regclass
          AND conname = 'users_height_cm_range'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_height_cm_range
            CHECK (height_cm IS NULL OR height_cm BETWEEN 100 AND 250);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'users'::regclass
          AND conname = 'users_target_weight_kg_range'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_target_weight_kg_range
            CHECK (target_weight_kg IS NULL OR target_weight_kg BETWEEN 20 AND 400);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'users'::regclass
          AND conname = 'users_activity_level_valid'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_activity_level_valid
            CHECK (activity_level IS NULL OR activity_level IN
                   ('sedentary', 'light', 'moderate', 'high', 'very_high'));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS weight_measurements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    measured_on DATE NOT NULL,
    weight_kg NUMERIC NOT NULL,
    height_cm_snapshot NUMERIC NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT weight_measurements_user_date_key UNIQUE (user_id, measured_on),
    CONSTRAINT weight_measurements_weight_range
        CHECK (weight_kg BETWEEN 20 AND 400),
    CONSTRAINT weight_measurements_height_range
        CHECK (height_cm_snapshot BETWEEN 100 AND 250)
);

CREATE INDEX IF NOT EXISTS weight_measurements_user_date_idx
    ON weight_measurements (user_id, measured_on DESC, created_at DESC);

CREATE OR REPLACE FUNCTION set_weight_measurements_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'weight_measurements'::regclass
          AND tgname = 'trg_weight_measurements_updated_at'
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER trg_weight_measurements_updated_at
            BEFORE UPDATE ON weight_measurements
            FOR EACH ROW EXECUTE FUNCTION set_weight_measurements_updated_at();
    END IF;
END $$;

INSERT INTO schema_migrations (version)
VALUES ('016_body_onboarding')
ON CONFLICT (version) DO NOTHING;
COMMIT;
