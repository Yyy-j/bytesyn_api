# Summary API Contract

Implemented Backend Phase 1 contract, 2026-09-26.

## Endpoints

- `GET /summary/daily?date=YYYY-MM-DD`
- `GET /summary/monthly?month=YYYY-MM`

Both endpoints require `Authorization: Bearer <access_token>`. Identity always
comes from the JWT. Client-supplied `user_id` or `pair_id` query parameters do
not affect scope.

## Scope and privacy

- **Single** and **Pending** users receive HTTP 200. Summary uses the current
  user's profile, goals, and `pair_id=null` Meals. Daily `partner_slice` and
  `partner_goals` are null. Monthly `partner` and every day's
  `partner_calories` are null.
- **Connected** users receive current Pair allocations plus all of their own
  historical allocations, including `pair_id=null` Meals and prior Ended Pair
  rows. Historical rows contribute only to that viewer's self totals. They are
  never included in the Partner's response or partner slice.
- **Ended** users are Single for presentation: Daily partner fields and Monthly
  partner fields are null. Their own persisted allocation from the Ended Pair
  remains included in self totals, so ending a Pair does not erase nutrition
  history.
- Current Pair Meals keep the existing two-person self/partner behavior. Both
  allocation rows of a shared Meal remain visible and are counted separately.

Creating an invite does not change Summary scope. The switch to Dual behavior
occurs only after the second member joins and the Pair has a non-null
`connected_at` with `ended_at=null`.

## Daily response

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
    "character": "boy",
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

Top-level macros sum every row returned in `meals`. `meal_count` is the number
of returned allocation rows. `meals` uses the same Meal object and ordering as
`GET /meals?date=...`. Persisted macro values are summed directly; base values
are not recalculated.

For Connected users, `partner_slice` and `partner_goals` are objects even when
the partner has no Meals. For Single/Pending users they are null.

## Monthly response

```json
{
  "month": "2026-09",
  "self": {
    "user_id": "11111111-1111-4111-8111-111111111111",
    "display_name": "未命名成员",
    "character": "boy",
    "calorie_goal": 2000
  },
  "partner": null,
  "days": [
    {
      "date": "2026-09-01",
      "self_calories": 0,
      "partner_calories": null
    }
  ]
}
```

`days` contains every calendar day in the requested month. Connected responses
use numeric partner calories (including zero); Single/Pending responses use
null. Self totals include the viewer's own personal Meal history and their
current Pair allocations.

## Goals, names, and consistency

Per-user stored goals are used, with defaults of 2000 calories, 90 protein,
250 carbs, and 60 fat for missing values. Blank display names become
`未命名成员`; a missing character falls back to `boy`.

Each request runs in one PostgreSQL `REPEATABLE READ, READ ONLY` transaction so
Pair state, profiles, Meal rows, and totals come from one snapshot.

## Errors

- `401`: missing, malformed, expired, or invalid Bearer JWT.
- `422`: missing or invalid `date`/`month`.
- `409`: a historical Meal row cannot be serialized under the Meal contract.
- `503`: PostgreSQL failure, always `{"detail":"Database unavailable"}`.

Single/Pending state is not an error and does not return the former
`404 {"detail":"Current pair not found"}` response.
