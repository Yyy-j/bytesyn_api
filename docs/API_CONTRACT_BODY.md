# Body Data, Weight, and Calorie Recommendation Contract

All endpoints require a Bearer Access Token. Body profile and weight data are
private to the authenticated user. Pair and Summary responses never expose
these fields.

## Body fields on `GET /users/me`

The existing response adds these nullable fields:

```json
{
  "onboarding_completed_at": "2026-09-27T08:00:00Z",
  "birth_year": 1998,
  "sex_for_energy_estimate": "male",
  "height_cm": 170.0,
  "target_weight_kg": 58.0,
  "target_date": "2027-01-01",
  "activity_level": "moderate"
}
```

`sex_for_energy_estimate` is only the `male|female` formula parameter used by
the energy estimate; it is not a general identity or gender model.
`activity_level` is one of `sedentary|light|moderate|high|very_high`.
`PATCH /users/me` accepts these six profile fields (not
`onboarding_completed_at`) in addition to the existing profile/goals fields.
Changing height does not rewrite any historical measurement snapshot.

## Weight measurements

One measurement is permitted per `(user_id, measured_on)`. Weight is 20–400 kg
and profile/snapshot height is 100–250 cm. These are product validation bounds,
not medical classifications.

### `GET /users/me/weight-measurements?limit=30`

`limit` is 1–100. Results are newest date first.

```json
{
  "measurements": [{
    "id": "uuid",
    "measured_on": "2026-09-27",
    "weight_kg": 63.2,
    "height_cm_snapshot": 170.0,
    "bmi": 21.9,
    "created_at": "2026-09-27T08:00:00Z",
    "updated_at": "2026-09-27T08:00:00Z"
  }]
}
```

### `POST /users/me/weight-measurements`

```json
{"measured_on":"2026-09-27","weight_kg":63.2}
```

Returns the measurement above with HTTP 201. The backend copies
`users.height_cm` into `height_cm_snapshot`; clients cannot submit a snapshot.
Missing profile height returns 409. A duplicate date returns 409. Future dates
and invalid values return 422.

### `PATCH /users/me/weight-measurements/{id}`

Accepts one or both fields:

```json
{"measured_on":"2026-09-26","weight_kg":63.0}
```

The original height snapshot is retained. A duplicate target date returns 409.
An absent or other user's ID returns 404.

### `DELETE /users/me/weight-measurements/{id}`

Returns 204. An absent or other user's ID returns 404.

## `GET /users/me/body`

The latest measurement by `measured_on` supplies current weight:

```json
{
  "height_cm": 170.0,
  "current_weight": {
    "measurement_id": "uuid",
    "measured_on": "2026-09-27",
    "weight_kg": 63.2,
    "bmi": 21.9
  },
  "target_weight_kg": 60.0,
  "target_date": "2026-12-31",
  "weight_difference_kg": -3.2
}
```

Without a measurement, `current_weight` and `weight_difference_kg` are null.
BMI is never stored. Every historical BMI is calculated as
`weight_kg / (height_cm_snapshot / 100)^2` and rounded to one decimal. No BMI
health classification is returned.

## `POST /users/me/calorie-recommendation`

This endpoint is a read-only preview and never changes profile, goals, or
weight. It does not call Gemini or another external service.

Request:

```json
{
  "birth_year": 1998,
  "sex_for_energy_estimate": "male",
  "height_cm": 170,
  "current_weight_kg": 63,
  "target_weight_kg": 58,
  "target_date": "2027-01-01",
  "activity_level": "moderate"
}
```

Response:

```json
{
  "method": "mifflin_st_jeor_v1",
  "direction": "lose",
  "bmr": 1558,
  "maintenance_calories": 2414,
  "recommended_calories": 2013,
  "requested_target_date": "2027-01-01",
  "recommended_target_date": "2027-01-01",
  "aggressive_timeline": false,
  "recommended_goals": {
    "calories": 2013,
    "protein": 113,
    "carbs": 264,
    "fat": 56
  }
}
```

Method `mifflin_st_jeor_v1` uses Mifflin-St Jeor and multipliers 1.2, 1.375,
1.55, 1.725, and 1.9 in activity enum order. Direction is derived from target
minus current weight with a 0.1 kg maintain tolerance.

Loss is capped by all of: 1% body weight/week, 25% TDEE/day, and a calorie
floor of 1500 for the `male` formula parameter or 1200 for `female`. Gain is
capped by 0.5% body weight/week and 15% TDEE/day. An aggressive request still
returns a safe calorie target, sets `aggressive_timeline=true`, and calculates a
later recommended date.

Protein is 1.8 g/kg for loss and 1.6 g/kg for maintain/gain. Fat is 25% of the
recommended calories. Carbohydrate uses the remaining calories. Whole-number
rounding can create a small calorie difference. This is a deterministic product
estimate, not a medical prescription. Age under 18 returns 422.
Because only birth year is collected, a current-year difference of exactly 18
cannot prove the birthday has occurred and is also rejected conservatively.

## Errors

- `401`: missing or invalid Access Token.
- `404`: measurement is absent or belongs to another user.
- `409`: profile height missing or duplicate measurement date.
- `422`: malformed date, enum, NaN/infinity, future measurement date, past
  target date, under-18 recommendation, or out-of-range body value.
- `503`: database operation failed.

These endpoints do not define a Phase 3 domain-level 400 response; request
validation errors use 422.
