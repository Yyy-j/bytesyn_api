import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row


def get_connection() -> Connection:
    """Create a database connection using environment-only configuration."""
    return psycopg.connect(
        host=os.environ["DATABASE_HOST"],
        port=int(os.environ.get("DATABASE_PORT", "5432")),
        dbname=os.environ["DATABASE_NAME"],
        user=os.environ["DATABASE_USER"],
        password=os.environ["DATABASE_PASSWORD"],
        connect_timeout=5,
        row_factory=dict_row,
    )


@contextmanager
def connection() -> Iterator[Connection]:
    with get_connection() as conn:
        yield conn


def find_or_create_identity(
    *, provider: str, provider_subject: str, email: str | None
) -> dict[str, object]:
    """Return one internal user for a provider identity, creating it atomically."""
    identity_key = f"{len(provider)}:{provider}{provider_subject}"
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (identity_key,),
            )
            cursor.execute(
                """
                SELECT user_id, email FROM auth_identities
                WHERE provider = %s AND provider_subject = %s
                """,
                (provider, provider_subject),
            )
            identity = cursor.fetchone()
            if identity is not None:
                return identity

            cursor.execute("INSERT INTO users DEFAULT VALUES RETURNING id")
            user_id = cursor.fetchone()["id"]
            cursor.execute(
                """
                INSERT INTO auth_identities
                    (user_id, provider, provider_subject, email)
                VALUES (%s, %s, %s, %s)
                RETURNING user_id, email
                """,
                (user_id, provider, provider_subject, email),
            )
            return cursor.fetchone()


def get_user_identity(user_id: UUID) -> dict[str, object] | None:
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id, ai.provider, ai.email, u.display_name, u.character,
                       u.calorie_goal, u.protein_goal, u.carbs_goal, u.fat_goal,
                       u.onboarding_completed_at, u.birth_year,
                       u.sex_for_energy_estimate, u.height_cm,
                       u.target_weight_kg, u.target_date, u.activity_level
                FROM users AS u
                JOIN auth_identities AS ai ON ai.user_id = u.id
                WHERE u.id = %s
                ORDER BY ai.created_at
                LIMIT 1
                """,
                (user_id,),
            )
            return cursor.fetchone()


def create_auth_session(
    *, user_id: UUID, token_hash: str, expires_at: datetime
) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO auth_sessions (user_id, token_hash, expires_at)
            VALUES (%s, %s, %s)
            """,
            (user_id, token_hash, expires_at),
        )


def rotate_auth_session(
    *,
    old_token_hash: str,
    new_token_hash: str,
    now: datetime,
    expires_at: datetime,
) -> UUID | None:
    """Atomically consume one valid refresh token and replace it."""
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE auth_sessions
            SET token_hash = %s, expires_at = %s, updated_at = %s
            WHERE token_hash = %s
              AND revoked_at IS NULL
              AND expires_at > %s
            RETURNING user_id
            """,
            (new_token_hash, expires_at, now, old_token_hash, now),
        ).fetchone()
        return row["user_id"] if row is not None else None


def revoke_auth_session(*, token_hash: str, now: datetime) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = COALESCE(revoked_at, %s), updated_at = %s
            WHERE token_hash = %s
            """,
            (now, now, token_hash),
        )
