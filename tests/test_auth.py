import hashlib
from datetime import datetime, timedelta, timezone

import jwt

from app import auth
from app.db import get_connection


def _login(client, user, monkeypatch):
    monkeypatch.setattr(
        auth,
        "verify_google_token",
        lambda _: {"sub": "google-subject", "email": "person@example.com"},
    )
    monkeypatch.setattr(
        auth,
        "find_or_create_identity",
        lambda **_: {"user_id": user, "email": "person@example.com"},
    )
    return client.post("/auth/google", json={"id_token": "google-id-token"})


def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def test_login_returns_access_and_refresh_tokens(context, monkeypatch):
    client, users, _ = context
    before = datetime.now(timezone.utc)
    response = _login(client, users[0], monkeypatch)
    after = datetime.now(timezone.utc)

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["refresh_token"]
    claims = jwt.decode(
        payload["access_token"],
        auth.os.environ["JWT_SECRET"],
        algorithms=["HS256"],
        audience="bytesync-api",
        issuer="bytesync",
    )
    assert claims["sub"] == str(users[0])
    assert claims["exp"] - claims["iat"] == 60 * 60

    with get_connection() as conn:
        row = conn.execute(
            "SELECT token_hash, expires_at FROM auth_sessions WHERE user_id = %s",
            (users[0],),
        ).fetchone()
    assert row["token_hash"] == _token_hash(payload["refresh_token"])
    assert payload["refresh_token"] not in row["token_hash"]
    assert auth.REFRESH_SESSION_EXPIRE_DAYS == 30
    assert before + timedelta(days=30) <= row["expires_at"]
    assert row["expires_at"] <= after + timedelta(days=30)


def test_refresh_rotates_token_and_slides_expiry(context, monkeypatch):
    client, users, _ = context
    original = _login(client, users[0], monkeypatch).json()["refresh_token"]
    near_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
    with get_connection() as conn:
        conn.execute(
            "UPDATE auth_sessions SET expires_at = %s WHERE token_hash = %s",
            (near_expiry, _token_hash(original)),
        )

    before = datetime.now(timezone.utc)
    response = client.post("/auth/refresh", json={"refresh_token": original})
    after = datetime.now(timezone.utc)

    assert response.status_code == 200
    rotated = response.json()["refresh_token"]
    assert rotated != original
    with get_connection() as conn:
        old = conn.execute(
            "SELECT 1 FROM auth_sessions WHERE token_hash = %s",
            (_token_hash(original),),
        ).fetchone()
        current = conn.execute(
            "SELECT expires_at FROM auth_sessions WHERE token_hash = %s",
            (_token_hash(rotated),),
        ).fetchone()
    assert old is None
    assert before + timedelta(days=30) <= current["expires_at"]
    assert current["expires_at"] <= after + timedelta(days=30)
    assert current["expires_at"] > near_expiry

    assert client.post(
        "/auth/refresh", json={"refresh_token": original}
    ).status_code == 401


def test_refresh_rejects_expired_session(context, monkeypatch):
    client, users, _ = context
    refresh_token = _login(client, users[0], monkeypatch).json()["refresh_token"]
    with get_connection() as conn:
        conn.execute(
            "UPDATE auth_sessions SET expires_at = %s WHERE token_hash = %s",
            (datetime.now(timezone.utc) - timedelta(seconds=1), _token_hash(refresh_token)),
        )

    response = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 401


def test_logout_revokes_session(context, monkeypatch):
    client, users, _ = context
    refresh_token = _login(client, users[0], monkeypatch).json()["refresh_token"]

    assert client.post(
        "/auth/logout", json={"refresh_token": refresh_token}
    ).status_code == 204
    assert client.post(
        "/auth/refresh", json={"refresh_token": refresh_token}
    ).status_code == 401
    with get_connection() as conn:
        row = conn.execute(
            "SELECT revoked_at FROM auth_sessions WHERE token_hash = %s",
            (_token_hash(refresh_token),),
        ).fetchone()
    assert row["revoked_at"] is not None
