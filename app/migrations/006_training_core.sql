-- User-scoped training templates and immutable-by-default weekly snapshots.
BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE IF NOT EXISTS training_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    days JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT training_templates_user_id_key UNIQUE (user_id),
    CONSTRAINT training_templates_seven_days CHECK (
        jsonb_typeof(days) = 'array' AND jsonb_array_length(days) = 7
        AND days @? '$[*] ? (@.day_index == 0)'
        AND days @? '$[*] ? (@.day_index == 1)'
        AND days @? '$[*] ? (@.day_index == 2)'
        AND days @? '$[*] ? (@.day_index == 3)'
        AND days @? '$[*] ? (@.day_index == 4)'
        AND days @? '$[*] ? (@.day_index == 5)'
        AND days @? '$[*] ? (@.day_index == 6)'
    )
);

CREATE TABLE IF NOT EXISTS training_weeks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    week_key VARCHAR(8) NOT NULL,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    template_version INTEGER NOT NULL CHECK (template_version >= 1),
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    synced_at TIMESTAMPTZ,
    days JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT training_weeks_user_week_key UNIQUE (user_id, week_key),
    CONSTRAINT training_weeks_key_format CHECK (
        week_key ~ '^[0-9]{4}-W(0[1-9]|[1-4][0-9]|5[0-3])$'
    ),
    CONSTRAINT training_weeks_date_range CHECK (week_end = week_start + 6),
    CONSTRAINT training_weeks_seven_days CHECK (
        jsonb_typeof(days) = 'array' AND jsonb_array_length(days) = 7
    )
);

CREATE INDEX IF NOT EXISTS training_weeks_user_start_idx
    ON training_weeks (user_id, week_start DESC);

INSERT INTO schema_migrations (version) VALUES ('006_training_core')
ON CONFLICT (version) DO NOTHING;
COMMIT;
