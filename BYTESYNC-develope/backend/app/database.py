import os
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


def check_database() -> bool:
    """Connect to PostgreSQL and verify that it can execute a trivial query."""
    connection_parameters = {
        "host": os.environ["DATABASE_HOST"],
        "port": int(os.environ.get("DATABASE_PORT", "5432")),
        "dbname": os.environ["DATABASE_NAME"],
        "user": os.environ["DATABASE_USER"],
        "password": os.environ["DATABASE_PASSWORD"],
        "connect_timeout": 5,
    }

    with psycopg.connect(**connection_parameters) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()

    return row == (1,)


def get_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ["DATABASE_HOST"],
        port=int(os.environ.get("DATABASE_PORT", "5432")),
        dbname=os.environ["DATABASE_NAME"],
        user=os.environ["DATABASE_USER"],
        password=os.environ["DATABASE_PASSWORD"],
        connect_timeout=5,
        row_factory=dict_row,
    )


def find_or_create_identity(
    *, provider: str, provider_subject: str, email: str | None
) -> dict[str, object]:
    identity_key = f"{len(provider)}:{provider}{provider_subject}"
    with get_connection() as connection:
        with connection.cursor() as cursor:
            # Serialize concurrent first logins for the same external identity.
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
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id, ai.provider, ai.email
                FROM users AS u
                JOIN auth_identities AS ai ON ai.user_id = u.id
                WHERE u.id = %s
                ORDER BY ai.created_at
                LIMIT 1
                """,
                (user_id,),
            )
            return cursor.fetchone()
