-- Remove the deprecated user avatar URL field.
BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE users DROP COLUMN avatar_url;

INSERT INTO schema_migrations (version) VALUES ('011_drop_user_avatar_url')
ON CONFLICT (version) DO NOTHING;
COMMIT;
