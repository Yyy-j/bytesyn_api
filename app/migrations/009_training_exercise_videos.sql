-- User-private external teaching video URL per exercise catalog reference.
BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE IF NOT EXISTS training_exercise_videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exercise_id VARCHAR(120) NOT NULL,
    video_url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT training_exercise_videos_user_exercise_key
        UNIQUE (user_id, exercise_id),
    CONSTRAINT training_exercise_videos_exercise_id_check
        CHECK (length(exercise_id) BETWEEN 1 AND 120),
    CONSTRAINT training_exercise_videos_url_length_check
        CHECK (length(video_url) BETWEEN 1 AND 2048),
    CONSTRAINT training_exercise_videos_http_url_check
        CHECK (video_url ~* '^https?://[^[:space:]]+$')
);

CREATE INDEX IF NOT EXISTS training_exercise_videos_user_updated_idx
    ON training_exercise_videos (user_id, updated_at DESC);

INSERT INTO schema_migrations (version) VALUES ('009_training_exercise_videos')
ON CONFLICT (version) DO NOTHING;
COMMIT;
