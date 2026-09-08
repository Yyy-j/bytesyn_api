# Meals MVP NAS deployment and acceptance

Status: **not deployed**. The Meals share_mode contract now matches Flutter main:
`solo / partner_only / shared_half / shared_me_one_third / shared_me_two_thirds`.
Only these values are accepted and returned; retired short aliases return 422.
No Summary or Flutter changes are included.

## Observed NAS compatibility

Read-only inspection on 2026-09-08 found PostgreSQL 17.11, an existing 32-column
public.meals table, 12 constraints, 4 indexes, and 0 records. Do not infer that a
later deployment is still empty. Schema-only evidence is in
`tests/fixtures/nas_meals.sql`; no business data was exported.

Existing base_* are nullable numeric(10,2), stored macros are numeric(10,2),
portion/share ratios are numeric(8,4), meal_time and pair_id are nullable.
Extra original_*, dishes/base_dishes/original_dishes, image_url, hint and user
metadata columns exist. name is varchar(255), source/share_mode varchar(30).
The trigger trg_meals_updated_at calls set_updated_at(), assigning NOW().

003 is transactional and repeatable. It creates the MVP table only when absent,
adds missing base columns and nullable share_owner_id, widens base/ratio NUMERIC
precision without changing existing values, preserves all old fields and
constraints, adds missing indexes and records schema_migrations version
003_meals_mvp once. It performs no UPDATE, DELETE, DROP COLUMN or backfill.
The existing stored nutrition scale (2 decimals) is retained.

A fresh read-only NAS check for this contract correction found 0 meals and no
share_mode CHECK constraint among the 12 existing constraints. Migration 003
also has no share_mode CHECK. Its executable SQL is unchanged; only its
partner_only comment was updated. No data conversion, constraint replacement,
or legacy alias support is needed for the inspected schema.

Type widening needs an exclusive table lock and may rewrite a large table; the
migration uses a 5-second lock timeout and rolls back on failure. Run it during
an appropriate deployment window. Unknown/diverged schemas must be inspected;
this migration is verified against the recorded NAS schema and a clean database,
not every possible historical schema.

## NAS commands

Run on this NAS from /home/yyy/bytesync-api.
The inspected API uses network bytesync-db_default, port 8000, restart
unless-stopped and no mounts/Compose labels. Preserve the existing .env.runtime;
do not paste secrets into commands or source it as shell code.

```bash
cd /home/yyy/bytesync-api

# Backup before any schema change; contains private business data.
mkdir -p /home/yyy/bytesync-backups
chmod 700 /home/yyy/bytesync-backups
umask 077
docker exec bytesync-postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "/home/yyy/bytesync-backups/pre-meals-$(date +%Y%m%d-%H%M%S).dump"

# Inspect the current table again; abort if it diverged from the documented schema.
docker exec bytesync-postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\d+ public.meals"'

# Build before taking down the existing API.
docker build -t backend-api:meals-v1 .

# ON_ERROR_STOP ensures migration errors stop deployment; 003 has BEGIN/COMMIT.
docker exec -i bytesync-postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < app/migrations/003_meals_mvp.sql
# Do not continue if the previous command failed.
docker exec bytesync-postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "TABLE schema_migrations"'

# Keep the old container for rollback. This backup name must not already exist.
docker stop bytesync-api
docker rename bytesync-api bytesync-api-before-meals
docker run -d --name bytesync-api --restart unless-stopped \
  --network bytesync-db_default --env-file /home/yyy/bytesync-api/.env.runtime \
  -p 8000:8000 backend-api:meals-v1
curl --fail-with-body http://127.0.0.1:8000/health
```

Rollback application only; additive migration can remain:

```bash
docker stop bytesync-api
docker rename bytesync-api bytesync-api-meals-failed
docker rename bytesync-api-before-meals bytesync-api
docker start bytesync-api
```

## curl acceptance

Requires bash and jq, an existing pair with two real users, and a valid JWT from
Google login. Requests create real meals and remove those meals at the end.
The script uses the official Flutter main share_mode values.

```bash
BASE_URL=http://127.0.0.1:8000
read -rsp 'Bearer JWT: ' TOKEN
printf '\n'

# Missing auth: 401.
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE_URL/meals/recent"

# Solo create: 201; inspect Meal JSON.
MEAL=$(curl --fail-with-body -sS "$BASE_URL/meals" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"curl acceptance","source":"manual","base_calories":601.23,"base_protein":30.12,"base_carbs":70.45,"base_fat":20.67,"portion_ratio":1,"share_mode":"solo","meal_time":"12:30"}')
printf '%s\n' "$MEAL" | jq .
MEAL_ID=$(printf '%s' "$MEAL" | jq -r .id)
MEAL_DATE=$(printf '%s' "$MEAL" | jq -r .meal_date)
VERSION=$(printf '%s' "$MEAL" | jq -r .updated_at)

# List, get and recent: 200.
curl --fail-with-body -sS -H "Authorization: Bearer $TOKEN" "$BASE_URL/meals?date=$MEAL_DATE" | jq .
curl --fail-with-body -sS -H "Authorization: Bearer $TOKEN" "$BASE_URL/meals/$MEAL_ID" | jq .
curl --fail-with-body -sS -H "Authorization: Bearer $TOKEN" "$BASE_URL/meals/recent?limit=3" | jq .

# Patch: 200. Retry the old version: 409.
PATCH=$(jq -n --arg version "$VERSION" '{name:"curl edited",portion_ratio:1.5,expected_updated_at:$version}')
curl --fail-with-body -sS -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d "$PATCH" "$BASE_URL/meals/$MEAL_ID" | jq .
curl -sS -w '\n%{http_code}\n' -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d "$PATCH" "$BASE_URL/meals/$MEAL_ID"

# Invalid input: 422.
curl -sS -w '\n%{http_code}\n' -H "Authorization: Bearer $TOKEN" "$BASE_URL/meals/recent?limit=11"

# Shared create: 201, requires both pair members.
SHARED=$(curl --fail-with-body -sS "$BASE_URL/meals" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"curl shared","source":"manual","base_calories":600,"base_protein":30,"base_carbs":60,"base_fat":20,"portion_ratio":1,"share_mode":"shared_me_one_third","meal_time":"18:00"}')
SHARED_ID=$(printf '%s' "$SHARED" | jq -r .id)
GROUP_ID=$(printf '%s' "$SHARED" | jq -r .shared_meal_id)
SHARED_DATE=$(printf '%s' "$SHARED" | jq -r .meal_date)
SHARED_VERSION=$(printf '%s' "$SHARED" | jq -r .updated_at)

# Both rows: 200/400 calories respectively.
curl --fail-with-body -sS -H "Authorization: Bearer $TOKEN" "$BASE_URL/meals?date=$SHARED_DATE" \
  | jq --arg group "$GROUP_ID" '[.meals[] | select(.shared_meal_id == $group)]'

# One patch updates both to 300 calories and the same name/time/version.
SHARED_PATCH=$(jq -n --arg version "$SHARED_VERSION" '{name:"shared edited",share_mode:"shared_half",meal_time:"19:00",expected_updated_at:$version}')
curl --fail-with-body -sS -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d "$SHARED_PATCH" "$BASE_URL/meals/$SHARED_ID" | jq .
curl --fail-with-body -sS -H "Authorization: Bearer $TOKEN" "$BASE_URL/meals?date=$SHARED_DATE" \
  | jq --arg group "$GROUP_ID" '[.meals[] | select(.shared_meal_id == $group)]'

# Each delete: 204; deleting one shared id removes both allocations.
curl --fail-with-body -sS -o /dev/null -w '%{http_code}\n' -X DELETE \
  -H "Authorization: Bearer $TOKEN" "$BASE_URL/meals/$SHARED_ID"
curl --fail-with-body -sS -H "Authorization: Bearer $TOKEN" "$BASE_URL/meals?date=$SHARED_DATE" \
  | jq --arg group "$GROUP_ID" '[.meals[] | select(.shared_meal_id == $group)]'
curl --fail-with-body -sS -o /dev/null -w '%{http_code}\n' -X DELETE \
  -H "Authorization: Bearer $TOKEN" "$BASE_URL/meals/$MEAL_ID"
unset TOKEN
```

## Automated test result

2026-09-08: **56 passed in 3.98s**, PostgreSQL 17, Python 3.12.
All original 38 cases were rerun using the official values, plus 18 new cases:
five official modes accepted by POST and PATCH with identical values in create,
patch, get, date-list, recent and stored rows; four retired modes rejected with
422 by both POST and PATCH without data changes.
Two dependency deprecation warnings (Starlette/httpx and AnyIO), no failures.
Coverage includes all six JWT-protected endpoints, pair isolation, validation,
source values, recent ordering/limits, exact base preservation, repeated
recalculation, all share modes, mode transitions, concurrent optimistic conflict,
second-row INSERT/UPDATE/DELETE failure rollback, clean-schema migration, and
repeat migration over a populated copy of the actual NAS schema.
`git diff --check` and Python compilation also passed.

These are backend tests, not a successful Flutter end-to-end acceptance.
The share_mode contract mismatch is resolved; deployment and live Flutter
acceptance have not been performed.

## Repeat automated tests

Tests contain no production mocks: FastAPI TestClient invokes the real SQL and
JWT dependency against PostgreSQL. Test fixtures use a fixed disposable database
name, override database env configuration, and never load .env.runtime. Use the
isolated container network below, not a NAS production database.

```bash
cd /home/yyy/bytesync-api
docker build -f tests/Dockerfile -t bytesync-meals-tests .
docker run -d --rm --name bytesync-meals-test-db --network none \
  -e POSTGRES_HOST_AUTH_METHOD=trust postgres:17
# Wait until pg_isready succeeds before running tests.
docker exec bytesync-meals-test-db pg_isready -U postgres
docker run --rm --network container:bytesync-meals-test-db \
  -v /home/yyy/bytesync-api:/workspace:ro \
  -e PYTHONDONTWRITEBYTECODE=1 bytesync-meals-tests
docker stop bytesync-meals-test-db
```
