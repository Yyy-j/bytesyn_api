-- Additive Pair lifecycle foundation. Historical Meal rows are intentionally untouched.
BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE pairs ADD COLUMN IF NOT EXISTS connected_at TIMESTAMPTZ;
ALTER TABLE pairs ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ;

-- Run the historical backfill only on the first application. A two-member Pair
-- became connected when its second member joined; one-member Pairs stay pending.
WITH existing_pairs AS (
    SELECT pm.pair_id, COUNT(*) AS member_count, MAX(pm.joined_at) AS connected_at
    FROM pair_members AS pm
    WHERE NOT EXISTS (
        SELECT 1 FROM schema_migrations WHERE version = '014_pair_lifecycle'
    )
    GROUP BY pm.pair_id
)
UPDATE pairs AS p
SET connected_at = existing_pairs.connected_at
FROM existing_pairs
WHERE p.id = existing_pairs.pair_id
  AND existing_pairs.member_count = 2
  AND p.connected_at IS NULL
  AND p.ended_at IS NULL;

INSERT INTO schema_migrations (version) VALUES ('014_pair_lifecycle')
ON CONFLICT (version) DO NOTHING;
COMMIT;
