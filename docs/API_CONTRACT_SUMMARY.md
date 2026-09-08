# Daily Summary API contract

`GET /summary/daily?date=YYYY-MM-DD`

Frozen against Flutter main:
`mobile/lib/features/summary/domain/daily_summary.dart`
(blob `3f14318d78badf1c74175b4f79619ef1914049c1`) and
`mobile/lib/features/summary/data/remote_summary_repository.dart`
(blob `ce32c8269f22f4eb78aa7ea1c81e88c20bd738dd`).
Flutter and the Meals contract are unchanged. No migration is needed.

## Authentication and scope

Requires `Authorization: Bearer <access_token>` using the existing JWT verifier.
Current users.id comes from JWT sub, and current pair_id from pair_members.
Client-supplied user_id or pair_id query parameters do not affect scope.
The date parameter is required and must be a valid calendar date. It selects the
stored meal_date directly; no timezone conversion or current-day substitution.

Unpaired users receive `404 {"detail":"Current pair not found"}`, consistent
with Meals. A pair containing only the current user is fully supported.

## Response: 200

Example for a one-member pair on a day without meals:

```json
{
  "date": "2026-09-08",
  "calories": 0,
  "protein": 0,
  "carbs": 0,
  "fat": 0,
  "meal_count": 0,
  "meals": [],
  "self_slice": {
    "user_id": "11111111-1111-4111-8111-111111111111",
    "display_name": "未命名成员",
    "calories": 0,
    "protein": 0,
    "carbs": 0,
    "fat": 0
  },
  "partner_slice": null,
  "self_goals": {
    "calorie_goal": 2000,
    "protein_goal": 90,
    "carbs_goal": 250,
    "fat_goal": 60
  },
  "partner_goals": null
}
```

All fields are always present. Macro totals are JSON numbers, meal_count is an
integer, user_id is a UUID string and display_name is a string.

- Top-level totals sum **all returned meal rows** belonging to the current pair
  on the requested date, using persisted calories/protein/carbs/fat. No base or
  portion/share recalculation occurs. Decimal values are summed before conversion
  to JSON numbers; no additional rounding is applied.
- `meals` uses the existing `app.meals.public_meal` serializer, exactly matching
  `GET /meals?date=...`, including order (meal_time, created_at, id ascending).
  There is no second Meal DTO. See [Meals contract](API_CONTRACT_MEALS.md).
- `meal_count = len(meals)`. Both allocations of a shared meal are included and
  counted separately, matching Flutter DailySummary.fromMeals semantics.
- `self_slice` sums rows whose user_id is the authenticated user. `partner_slice`
  sums rows owned by the other pair member. Accessing the endpoint as the other
  member swaps these slices, without changing the top-level pair totals.
- One-member pair: partner_slice and partner_goals are null. Two-member pair:
  both are objects, even when the partner has eaten nothing (zero macro totals).
- Empty date: 200, zero totals, meal_count=0 and meals=[], with member identities
  and goals still populated. An empty meal list never means 404.
- display_name uses users.display_name, trimmed; absent, null or blank names
  become `未命名成员`, matching Flutter's fallback. The SQL supports both the
  minimal migrated users table without display_name and the NAS users table.
- MVP goals are the explicit fixed defaults 2000/90/250/60 for each present
  member. The existing NAS users.goals JSON is not interpreted; per-user goal
  settings are outside this endpoint's current contract. These are product
  defaults, not fabricated meal records or a production mock.

## Consistency and errors

Queries run in one PostgreSQL REPEATABLE READ, READ ONLY transaction, so membership,
profile names, meal rows and their totals reflect one snapshot. Concurrent shared
meal mutations are visible wholly before or wholly after commit. All external
query values are passed as SQL parameters. This endpoint performs no writes.

- 401: missing, malformed, expired or invalid Bearer JWT.
- 404: current user has no pair.
- 422: missing/invalid date.
- 409: a historical Meal row cannot be serialized under the existing Meals
  contract (same explicit reconciliation error as Meals).
- 503: PostgreSQL failure, `{"detail":"Database unavailable"}`. The existing
  global handler prevents exposing database SQL, passwords or exception details.

## Automated verification

69 passed in 4.78s: all 56 Meals regression cases plus 13 Summary cases, using
real JWT verification and an isolated PostgreSQL 17 database through FastAPI
TestClient. Coverage includes missing/invalid auth, unpaired users, one-member
pairs with/without meals, two-member pairs with/without meals, viewer-relative
slices, all macro totals from stored values, identical Meal DTOs, date isolation,
cross-pair isolation (including supplied foreign IDs), invalid dates and real
NAS-style display names. Two test-dependency deprecation warnings, no failures.
Python compilation and git diff --check passed. Live Flutter acceptance and
production deployment have not been performed by this change.

## NAS deployment

The inspected running API uses port 8000, network bytesync-db_default, restart
unless-stopped and no mounts. Existing Meals migrations are already deployed.
No new SQL migration is required. Run commands in order, stopping on any error.

```bash
cd /home/yyy/bytesync-api
docker build -t backend-api:summary-v1 .

# Retain the currently deployed container for rollback.
# Confirm this backup name is unused before stopping the service.
docker stop bytesync-api
docker rename bytesync-api bytesync-api-before-summary
docker run -d --name bytesync-api --restart unless-stopped \
  --network bytesync-db_default \
  --env-file /home/yyy/bytesync-api/.env.runtime \
  -p 8000:8000 backend-api:summary-v1
curl --fail-with-body http://127.0.0.1:8000/health
```

Application rollback (no database changes to undo):

```bash
docker stop bytesync-api
docker rename bytesync-api bytesync-api-summary-failed
docker rename bytesync-api-before-summary bytesync-api
docker start bytesync-api
```

## curl acceptance

Use a valid JWT from the deployed Google login. These commands only read data.
Requires bash and jq. Set MEAL_DATE to the date of the meal saved from Flutter.

```bash
BASE_URL=http://127.0.0.1:8000
MEAL_DATE=2026-09-08
read -rsp 'Bearer JWT: ' TOKEN
printf '\n'

# 401 without authentication.
curl -sS -w '\n%{http_code}\n' "$BASE_URL/summary/daily?date=$MEAL_DATE"

# 200 with a paired user's token, including a one-member pair.
curl --fail-with-body -sS -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/summary/daily?date=$MEAL_DATE" | jq .

# Meal DTOs should match this existing endpoint for the same date.
curl --fail-with-body -sS -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/meals?date=$MEAL_DATE" | jq .

# Pick a date without meals: 200, zero totals, meal_count=0, meals=[].
curl --fail-with-body -sS -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/summary/daily?date=1900-01-01" | jq .

# Invalid date: 422.
curl -sS -w '\n%{http_code}\n' -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/summary/daily?date=2026-02-30"

# To verify 404, repeat with a valid JWT belonging to an unpaired user.
# For a two-member pair, the other user's JWT should swap self/partner slices.
unset TOKEN
```

Repeat database tests using the isolated container commands in
[Meals deployment](MEALS_DEPLOYMENT.md#repeat-automated-tests); the existing test
runner discovers tests/test_summary.py automatically. Never run these fixtures
against the production database.
