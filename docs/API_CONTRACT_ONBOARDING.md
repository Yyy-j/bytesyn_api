# First-login Onboarding Contract

## Existing and new users

Migration `016_body_onboarding` sets `onboarding_completed_at` to the migration
execution time only for users that already exist before its first execution.
Their other new body fields remain null. Users created after the migration have
`onboarding_completed_at=null` and require first-login onboarding.

Flutter routing rule:

```text
GET /users/me -> onboarding_completed_at == null -> show onboarding
```

## `POST /users/me/onboarding`

Requires Bearer authentication.

Request:

```json
{
  "birth_year": 1998,
  "sex_for_energy_estimate": "male",
  "height_cm": 170,
  "current_weight_kg": 63,
  "target_weight_kg": 58,
  "target_date": "2027-01-01",
  "activity_level": "moderate",
  "goals": {
    "calories": 1850,
    "protein": 110,
    "carbs": 220,
    "fat": 55
  }
}
```

Response (HTTP 200):

```json
{
  "onboarding_completed_at": "2026-09-27T08:00:00Z",
  "birth_year": 1998,
  "sex_for_energy_estimate": "male",
  "height_cm": 170.0,
  "target_weight_kg": 58.0,
  "target_date": "2027-01-01",
  "activity_level": "moderate",
  "goals": {
    "calories": 1850.0,
    "protein": 110.0,
    "carbs": 220.0,
    "fat": 55.0
  },
  "current_weight": {
    "id": "uuid",
    "measured_on": "2026-09-27",
    "weight_kg": 63.0,
    "height_cm_snapshot": 170.0,
    "bmi": 21.8,
    "created_at": "2026-09-27T08:00:00Z",
    "updated_at": "2026-09-27T08:00:00Z"
  }
}
```

One database transaction updates the six body fields, stores the submitted
nutrition goals, writes today's first weight with the submitted height snapshot,
and sets `onboarding_completed_at`. Any database failure rolls back every write.

The operation is retry-safe: `(user_id, today)` is upserted, so a repeated valid
submission updates that day's onboarding weight instead of creating a second
row. The original completion timestamp is retained. Goals are validated but do
not need to equal the recommendation preview.

Errors:

- `401`: missing/invalid authentication.
- `422`: missing/extra field, invalid enum/date, NaN/infinity, or out-of-range
  profile, weight, or goals (`calories` 0–10000; each macro 0–1000).
- `503`: database failure; no partial onboarding state is committed.

The recommendation preview is separate and has no write side effect. Pair and
Summary APIs do not expose onboarding body or weight data.
