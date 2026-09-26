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

## Completion lifecycle

### First completion

When `onboarding_completed_at` is null, one database transaction updates the
six body fields, stores the submitted nutrition goals, upserts today's first
weight with the submitted height snapshot, and sets the completion timestamp.
Any database failure rolls back every write. Goals are validated but do not
need to equal the recommendation preview.

### Exact retry

After completion, the endpoint locks and reads the saved body fields, nutrition
goals, and today's weight. If every business value exactly equals the submitted
payload, including `weight_kg` and `height_cm_snapshot`, it returns the current
`OnboardingResponse` with HTTP 200 without issuing an UPDATE or INSERT. The
completion timestamp, measurement ID, and row timestamps remain unchanged.

Comparison uses typed date and numeric values rather than serialized JSON.

### Different payload after completion

When the saved onboarding profile is complete but any submitted body field,
goal, current weight, or height snapshot differs, the endpoint returns:

```json
{"detail":"Onboarding is already completed"}
```

with HTTP 409. No profile, goal, completion timestamp, or measurement is
changed. A complete profile with no measurement for today is also a 409 and is
not silently repaired.

### Grandfathered existing user

Migration `016_body_onboarding` marks pre-migration users completed so the app
does not force them through onboarding. Those users normally have one or more
required body/goal database fields still null. This is a valid grandfathered
state: `GET /users/me` works normally, and an explicit complete onboarding
submission is allowed once to initialize body, goals, and today's weight. The
original migration completion timestamp is preserved. Pair, Meal, Training,
Auth, and other existing data are untouched.

The minimal discriminator is therefore a complete saved body-and-goals state,
not `onboarding_completed_at` alone; no onboarding history table is used.

## Timeline validation

Recommendation and Onboarding call the same goal-timeline validator and use
the shared 0.1 kg maintain tolerance:

- A weight-changing goal requires `target_date > today`.
- A maintain goal may use `target_date == today`.
- A past target date always returns 422.

Errors:

- `401`: missing/invalid authentication.
- `409`: onboarding is already complete and the request is not an exact retry,
  including a complete state whose current-day measurement is missing.
- `422`: missing/extra field, invalid enum/date, NaN/infinity, or out-of-range
  profile, weight, or goals (`calories` 0–10000; each macro 0–1000).
- `503`: database failure; no partial onboarding state is committed.

The recommendation preview is separate and has no write side effect. Pair and
Summary APIs do not expose onboarding body or weight data.
