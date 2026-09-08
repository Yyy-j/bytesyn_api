# Meals MVP HTTP contract

Implemented backend contract, 2026-09-08. No Summary endpoint is included.

The official share_mode request, storage and response values match
`Yyy-j/bytesync_app` main's `mobile/lib/features/meals/domain/meal_share_mode.dart`
(blob `ba7c730809a117897ebed26268f94fc80d902826`):
`solo / partner_only / shared_half / shared_me_one_third / shared_me_two_thirds`.
POST and PATCH accept only these values, and Meal responses return the same
value. The retired aliases `ta_only / half / me_1_3 / me_2_3` return 422;
there is no alias normalization or alternate response dialect. Flutter is unchanged.
Source values and other request/response fields were checked against the eight
requested main-branch files and the meal mapper.

## Authentication and visibility

Every endpoint requires `Authorization: Bearer <access_token>`, verified by the
existing JWT dependency. Internal `users.id` comes from JWT `sub`; the pair comes
from `pair_members`. Request bodies reject unknown fields, including `user_id`,
`pair_id`, `shared_meal_id`, stored nutrition, `share_ratio`, and `meal_date`.

All six endpoints return `404 {"detail":"Current pair not found"}` for an
unpaired authenticated user with otherwise valid input. A one-member pair can
create solo meals; other modes return `409` until exactly one partner exists.
Members can read, edit and delete all meals belonging to their current pair,
including the partner's solo meals. Other pairs' IDs return `404 Meal not found`.

## Endpoints

| Method and path | Success response |
| --- | --- |
| `POST /meals` | `201`, one Meal object |
| `GET /meals?date=YYYY-MM-DD` | `200`, `{"meals":[Meal,...]}` |
| `GET /meals/recent?limit=3` | `200`, `{"meals":[Meal,...]}` |
| `GET /meals/{id}` | `200`, one Meal object |
| `PATCH /meals/{id}` | `200`, one Meal object |
| `DELETE /meals/{id}` | `204`, no body |

`id` must be a UUID. `date` is required and must be a valid calendar date.
Date lists include both shared rows, ordered by meal_time, created_at, id ascending.
No matches return an empty array. Recent defaults to 3, accepts only integers
1..10 (otherwise 422), orders by meal_date / meal_time / created_at / id descending,
and includes one reusable representative per shared group, preferring the
current user's row. It does not deduplicate unrelated meals by name.
`/recent` is registered before the UUID route.

## Create request

All fields below are required:

```json
{
  "name": "Lunch",
  "source": "manual",
  "base_calories": 601.23,
  "base_protein": 30.12,
  "base_carbs": 70.45,
  "base_fat": 20.67,
  "portion_ratio": 1,
  "share_mode": "solo",
  "meal_time": "12:30"
}
```

- name: 1..255 characters, not whitespace-only; preserved as supplied.
- source: `manual`, `ai`, `text`; no AI processing is added.
- base macros: finite, nonnegative numbers, at most 99999999, at most 30 total
  digits and 18 fractional digits. Base values are stored without rounding.
- portion_ratio: finite number greater than 0 and at most 100, at most 24 total
  digits and 18 fractional digits.
- meal_time: `HH:mm`, 00:00..23:59.
- meal_date: server's current calendar date in **Asia/Tokyo**, not UTC.
- timestamps: PostgreSQL TIMESTAMPTZ, returned as offset-bearing ISO-8601 strings.

| share_mode | Original creator's allocation | Partner allocation | Rows |
| --- | --- | --- | --- |
| solo | 1 | 0 | One, owned by creator |
| partner_only | 0 | 1 | One, owned by partner |
| shared_half | 1/2 | 1/2 | Two, same shared_meal_id |
| shared_me_one_third | 1/3 | 2/3 | Two, same shared_meal_id |
| shared_me_two_thirds | 2/3 | 1/3 | Two, same shared_meal_id |

Share modes retain the **original creator's perspective**, even when the partner
edits a row. Internal `share_owner_id` records that perspective and is not exposed
or client-writable. Both shared rows carry the same share_mode, base values,
portion_ratio and timestamps. Their user_id, share_ratio and stored macros differ.
Create returns the creator's allocation for shared meals, or the sole row for
solo/partner_only. Flutter reloads the date list to retrieve both rows.

Each stored macro = base × portion_ratio × exact share fraction, rounded **once**
to 2 decimal places, half up. Computation uses exact rational arithmetic; rounded
stored macros and approximate stored thirds are never inputs to recalculation.
Independent slice rounding can differ from the unsplit total by 0.01.
Calculated values above 99999999.99 return 422 and roll back the operation.

## Meal response

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "pair_id": "22222222-2222-4222-8222-222222222222",
  "user_id": "33333333-3333-4333-8333-333333333333",
  "shared_meal_id": null,
  "name": "Lunch",
  "source": "manual",
  "base_calories": 601.23,
  "base_protein": 30.12,
  "base_carbs": 70.45,
  "base_fat": 20.67,
  "calories": 601.23,
  "protein": 30.12,
  "carbs": 70.45,
  "fat": 20.67,
  "portion_ratio": 1,
  "share_ratio": 1,
  "share_mode": "solo",
  "meal_date": "2026-09-08",
  "meal_time": "12:30",
  "created_at": "2026-09-08T03:30:00+00:00",
  "updated_at": "2026-09-08T03:30:00+00:00"
}
```

Macros and ratios are JSON **numbers**, not Decimal strings. The wire uses JSON
number precision while PostgreSQL retains exact input base decimals.

## Patch and delete

PATCH accepts only the following optional, non-null fields:
`name`, `base_calories`, `base_protein`, `base_carbs`, `base_fat`, `portion_ratio`,
`share_mode`, `meal_time`, `expected_updated_at`. Validation matches create.
`source`, identity fields and `meal_date` are not writable in the frozen Flutter
DTO. The original meal_date is preserved and synchronized across shared rows;
meal_time changes propagate. Date movement would require a later contract change.

```json
{
  "name": "Dinner",
  "portion_ratio": 1.5,
  "expected_updated_at": "2026-09-08T03:30:00+00:00"
}
```

`expected_updated_at` accepts an offset-bearing ISO timestamp. Comparison is by
instant, including microseconds. It is optional to match Flutter's DTO. If sent
and either shared row has a different version, return
`409 {"detail":"Meal was updated; refresh and retry"}` with no writes. Omission
means last-write-wins. Empty PATCH is a no-op after checking any supplied version.

One request synchronizes name, all base macros, portion/share mode, date and time,
then recalculates both allocations. Mode transitions add/remove rows atomically.
Existing allocation IDs are retained when possible; if the addressed allocation
is removed, the response is the surviving row (its id may differ). A newly created
allocation receives its own created_at; existing rows retain their created_at.

DELETE by either shared row removes the entire group atomically; clients must not
issue a second deletion. Repeating DELETE returns 404. DELETE has no optimistic
version parameter because Flutter sends none.

All database access is parameterized (dynamic identifiers are from server-owned
field sets and use psycopg.sql). Every operation uses one transaction. Pair row
locking serializes pair operations before meal locks, so sibling edits cannot
partially interleave. Existing NAS updated_at trigger is retained.

## Errors and historical compatibility

- 401: missing, malformed, expired or invalid Bearer token.
- 404: no current pair; meal absent or outside the current pair.
- 409: missing partner, optimistic conflict, or historical group requiring reconciliation.
- 422: invalid body, UUID, date, limit, timestamp, macro or calculated overflow.
- 503: database error; always `{"detail":"Database unavailable"}`. Internal SQL,
  exceptions and credentials are never returned.

003 preserves all historical rows/columns/constraints/triggers. It does not invent
missing historical baselines, meal_time or sharing provenance. Reading a row with
missing required wire fields or unknown enums returns an explicit 409, including
when encountered in a list. Historical solo rows with complete fields can be
edited, using their user_id as creator. Historical shared/partner_only rows without
share_owner_id cannot be edited until reconciled; no guess is made about original
ownership. Deletion remains possible for well-formed one/two-row groups. Groups
with a cross-pair sibling or other than two rows return 409 without modification.
