# Pair API Contract

All Pair endpoints require `Authorization: Bearer <access_token>`.

## `GET /pairs/me`

Returns the current pair with HTTP `200`. When the authenticated user has no
pair, returns HTTP `404` with `{"detail":"Current pair not found"}`.

## `POST /pairs`

The request body is empty. It creates a pair containing the authenticated user
and returns HTTP `201`.

## `POST /pairs/join`

Request body:

```json
{"invite_code":"AB12CD34"}
```

The authenticated user is added to the pair identified by `invite_code` and
the endpoint returns HTTP `200`.

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
      "avatar_url": null
    }
  ],
  "created_at": "2026-01-01T00:00:00Z"
}
```

## Error status codes

- `401`: missing, malformed, expired, or invalid Bearer token.
- `404`: authenticated user has no current pair (`GET /pairs/me`).
- `409`: user already has a pair, the pair is full, the user is already a
  member, or the invite code conflicts/does not exist.
- `422`: malformed request input, including an invalid `invite_code`.

Database errors are never returned verbatim.