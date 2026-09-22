-- Stable user character selection. Historical users remain nullable.
BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS character VARCHAR(16);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'users_character_check'
          AND conrelid = 'users'::regclass
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT users_character_check
            CHECK (character IS NULL OR character IN ('boy', 'girl'));
    END IF;
END
$$;

INSERT INTO schema_migrations (version) VALUES ('012_user_character')
ON CONFLICT (version) DO NOTHING;
COMMIT;
