-- Optional default duration for duration/cardio custom exercises, in seconds.
BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE training_custom_exercises
    ADD COLUMN IF NOT EXISTS default_duration_seconds INTEGER NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'training_custom_exercises_default_duration_seconds_check'
          AND conrelid = 'training_custom_exercises'::regclass
    ) THEN
        ALTER TABLE training_custom_exercises
            ADD CONSTRAINT training_custom_exercises_default_duration_seconds_check
            CHECK (
                default_duration_seconds IS NULL
                OR default_duration_seconds BETWEEN 1 AND 86400
            );
    END IF;
END
$$;

INSERT INTO schema_migrations (version) VALUES ('008_training_custom_duration')
ON CONFLICT (version) DO NOTHING;
COMMIT;
