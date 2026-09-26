# Auth Session and Account Contract

## Session lifetimes

- Access Token: unchanged; default `ACCESS_TOKEN_EXPIRE_MINUTES=60`.
- Refresh Session: default `REFRESH_SESSION_EXPIRE_DAYS=30`.

`POST /auth/google` creates one hashed refresh session expiring 30 days after
login. `POST /auth/refresh` atomically replaces the stored token hash and sets
the new expiry to 30 days after rotation. The old token is invalid immediately.
Expired and revoked sessions return 401 and are never rotated.

Refresh tokens are never stored in plaintext. `POST /auth/logout` sets
`revoked_at`; a revoked token cannot be reused.

## `DELETE /users/me`

Requires a valid Bearer Access Token and returns HTTP 204.

The endpoint runs as one database transaction:

1. Lock the user and any active Pair.
2. End an active Pending or Connected Pair, setting lifecycle timestamps.
3. Delete all of the user's auth sessions, identities, favorites, Meals,
   weight measurements, training templates/weeks/custom exercises/videos, and
   membership rows.
4. Delete the user profile.

Deleting one Connected member ends the Pair. The partner account, membership
history, and partner-owned Meal allocation remain. `share_owner_id` becomes null
when the deleted user was the original share owner. The partner becomes Single
and may pair again.

Deleting a Pending member ends the Pair before deleting membership, so its old
invite is not joinable. All refresh sessions disappear in the same commit; old
refresh tokens return 401.

## Errors

- `401`: missing/invalid access token; refresh token missing, unknown, expired,
  revoked, already rotated, or deleted with its account.
- `422`: malformed login/refresh/logout request body.
- `503`: database failure; the account deletion transaction rolls back fully.

Only Google login is implemented in this contract.
