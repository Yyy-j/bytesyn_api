# Pair API Contract

All Pair endpoints require `Authorization: Bearer <access_token>`.

## Lifecycle states

- **Single**: the user has no `pair_members` row. `GET /pairs/me` returns
  `404 {"detail":"Current pair not found"}`. No Pair is created automatically.
- **Pending**: the Pair has one member and `connected_at=null`, `ended_at=null`.
- **Connected**: the Pair has exactly two members, `connected_at` is non-null,
  and `ended_at=null`.

The existence of a Pair alone does not mean that the user is Connected.

## `GET /pairs/me`

Returns HTTP `200` with the authenticated user's Pending or Connected Pair.
Single users receive the 404 response documented above.

## `POST /pairs`

The request body is empty. It creates a Pending Pair containing only the
authenticated user and returns HTTP `201`. It does not change Meal scope.

## `POST /pairs/join`

Request body:

```json
{"invite_code":"AB12CD34"}
```

The target Pair row is locked. In the same transaction, the endpoint verifies
that the Pair is Pending with exactly one member, inserts the second member,
and sets `connected_at=now()`. It returns HTTP `200`. A Pair never exceeds two
members.

## Response shape

All successful Pair endpoints return the same JSON shape:

```json
{
  "pair_id": "uuid",
  "invite_code": "AB12CD34",
  "members": [
    {
      "user_id": "uuid",
      "display_name": null,
      "character": "boy"
    }
  ],
  "created_at": "2026-01-01T00:00:00Z",
  "connected_at": null,
  "ended_at": null
}
```

`connected_at` and `ended_at` are nullable. This Phase does not expose an API
that ends a Pair.

## Error status codes

- `401`: missing, malformed, expired, or invalid Bearer token.
- `404`: authenticated user is Single (`GET /pairs/me`).
- `409`: user already has a Pair, target Pair is not joinable/full, user is
  already a member, or the invite code conflicts/does not exist.
- `422`: malformed request input, including an invalid `invite_code`.

Database errors are never returned verbatim.
