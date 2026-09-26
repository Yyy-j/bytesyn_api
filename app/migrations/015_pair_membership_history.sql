-- Preserve Pair membership history while allowing one active Pair per user.
BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE pair_members ADD COLUMN IF NOT EXISTS left_at TIMESTAMPTZ;

-- Existing Ended Pairs predate per-membership lifecycle state.
UPDATE pair_members AS pm
SET left_at = p.ended_at
FROM pairs AS p
WHERE p.id = pm.pair_id
  AND p.ended_at IS NOT NULL
  AND pm.left_at IS NULL;

ALTER TABLE pair_members
    DROP CONSTRAINT IF EXISTS pair_members_user_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS pair_members_active_user_id_key
    ON pair_members (user_id)
    WHERE left_at IS NULL;

-- Deleting one account must not delete a former partner's Meal allocation.
ALTER TABLE meals DROP CONSTRAINT IF EXISTS meals_share_owner_id_fkey;
ALTER TABLE meals ADD CONSTRAINT meals_share_owner_id_fkey
    FOREIGN KEY (share_owner_id) REFERENCES users(id) ON DELETE SET NULL;

INSERT INTO schema_migrations (version)
VALUES ('015_pair_membership_history')
ON CONFLICT (version) DO NOTHING;
COMMIT;
