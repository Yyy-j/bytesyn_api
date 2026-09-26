# Pair API Contract

All Pair endpoints require `Authorization: Bearer <access_token>`.

## Active and historical membership

`pair_members` retains history. `left_at=null` means the membership is active;
a non-null `left_at` means historical. A partial unique index permits at most
one active Pair per user while allowing any number of historical Pairs.

- **Single**: no active membership.
- **Pending**: one active member, `connected_at=null`, `ended_at=null`.
- **Connected**: two active members, `connected_at!=null`, `ended_at=null`.
- **Ended**: `ended_at!=null`; all remaining memberships have `left_at` set.

Ended membership never counts as the current Pair.

## Endpoints

### `GET /pairs/me`

Returns HTTP 200 for the authenticated user's active Pending or Connected Pair.
Single and Ended-only users receive:

```json
{"detail":"Current pair not found"}
```

with HTTP 404.

### `POST /pairs`

Creates a new Pending Pair for a Single user and returns HTTP 201. Historical
membership does not prevent creation.

### `POST /pairs/join`

```json
{"invite_code":"AB12CD34"}
```

Locks the target Pair row, verifies that it is active Pending, inserts the
second active membership, and sets `connected_at=now()` in one transaction.
The caller must be Single.

### `POST /pairs/invite-code/regenerate`

Pending-only. Locks the same Pair row as join, replaces the invite code, and
returns the unchanged Pair with HTTP 200. Pair ID, member, and lifecycle fields
do not change. The old code is invalid immediately. Connected/Single/Ended
states return 409.

### `POST /pairs/cancel`

Pending-only. Sets the Pair's `ended_at` and the sole active membership's
`left_at` to the same transaction timestamp. Returns HTTP 204. Pair and
membership history remain; its invite can no longer be joined.

### `POST /pairs/end`

Connected-only. Sets `ended_at` and both active memberships' `left_at` to the
same timestamp in one transaction. Returns HTTP 204. Pair, membership, and Meal
history remain. Both users immediately become Single and may pair again.

## Pair response

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

## Errors

- `401`: missing, malformed, expired, or invalid Bearer token.
- `404`: no active current Pair for `GET /pairs/me`.
- `409`: wrong lifecycle state, caller already has an active Pair, Pair is not
  joinable/full, or invite code is invalid/obsolete.
- `422`: malformed input, including invalid invite-code request data.
