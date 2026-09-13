-- Additive user profile and nutrition goals. Historical users remain nullable.
BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS calorie_goal NUMERIC;
ALTER TABLE users ADD COLUMN IF NOT EXISTS protein_goal NUMERIC;
ALTER TABLE users ADD COLUMN IF NOT EXISTS carbs_goal NUMERIC;
ALTER TABLE users ADD COLUMN IF NOT EXISTS fat_goal NUMERIC;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'users'::regclass AND conname = 'users_calorie_goal_nonnegative'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_calorie_goal_nonnegative
            CHECK (calorie_goal >= 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'users'::regclass AND conname = 'users_protein_goal_nonnegative'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_protein_goal_nonnegative
            CHECK (protein_goal >= 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'users'::regclass AND conname = 'users_carbs_goal_nonnegative'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_carbs_goal_nonnegative
            CHECK (carbs_goal >= 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'users'::regclass AND conname = 'users_fat_goal_nonnegative'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_fat_goal_nonnegative
            CHECK (fat_goal >= 0);
    END IF;
END $$;

CREATE OR REPLACE FUNCTION set_users_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'users'::regclass AND tgname = 'trg_users_updated_at'
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users
            FOR EACH ROW EXECUTE FUNCTION set_users_updated_at();
    END IF;
END $$;

INSERT INTO schema_migrations (version) VALUES ('004_user_profile_goals')
ON CONFLICT (version) DO NOTHING;
COMMIT;
