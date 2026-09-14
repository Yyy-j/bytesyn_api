-- Private, user-owned custom exercise catalog.
BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE IF NOT EXISTS training_custom_exercises (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL DEFAULT '',
    item_type VARCHAR(20) NOT NULL DEFAULT 'strength',
    default_sets INTEGER NOT NULL,
    default_reps INTEGER NOT NULL,
    default_weight NUMERIC NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT training_custom_exercises_item_type_check
        CHECK (item_type IN ('strength', 'duration', 'cardio')),
    CONSTRAINT training_custom_exercises_default_sets_check
        CHECK (default_sets BETWEEN 1 AND 50),
    CONSTRAINT training_custom_exercises_default_reps_check
        CHECK (default_reps BETWEEN 0 AND 999),
    CONSTRAINT training_custom_exercises_default_weight_check
        CHECK (default_weight BETWEEN 0 AND 10000)
);

CREATE INDEX IF NOT EXISTS training_custom_exercises_user_created_idx
    ON training_custom_exercises (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS training_custom_exercises_user_name_idx
    ON training_custom_exercises (user_id, name);

INSERT INTO schema_migrations (version) VALUES ('007_training_custom_exercises')
ON CONFLICT (version) DO NOTHING;
COMMIT;
