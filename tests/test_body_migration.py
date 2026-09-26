import os
from pathlib import Path
from uuid import uuid4

import psycopg


ROOT = Path(__file__).resolve().parents[1]


def test_body_migration_backfills_only_existing_users_and_is_repeatable():
    database_name = 'bytesync_body_migration_' + uuid4().hex
    admin = dict(
        host=os.environ['DATABASE_HOST'],
        port=os.environ['DATABASE_PORT'],
        user='postgres',
        password='test-only',
    )
    with psycopg.connect(dbname='postgres', autocommit=True, **admin) as conn:
        conn.execute(f'CREATE DATABASE {database_name}')
    try:
        with psycopg.connect(dbname=database_name, **admin) as conn:
            conn.execute((ROOT / 'app/migrations/001_auth_mvp.sql').read_text())
            conn.execute((ROOT / 'app/migrations/002_pairs.sql').read_text())
            old = conn.execute(
                "INSERT INTO users DEFAULT VALUES RETURNING id, created_at"
            ).fetchone()
            migration = (ROOT / 'app/migrations/016_body_onboarding.sql').read_text()
            conn.execute(migration)
            old_after = conn.execute(
                """SELECT created_at, onboarding_completed_at, birth_year,
                          sex_for_energy_estimate, height_cm, target_weight_kg,
                          target_date, activity_level
                   FROM users WHERE id=%s""",
                (old[0],),
            ).fetchone()
            assert old_after[0] == old[1]
            assert old_after[1] is not None
            assert all(value is None for value in old_after[2:])

            new_user = conn.execute(
                "INSERT INTO users DEFAULT VALUES RETURNING id"
            ).fetchone()[0]
            conn.execute(migration)
            assert conn.execute(
                "SELECT onboarding_completed_at FROM users WHERE id=%s",
                (new_user,),
            ).fetchone()[0] is None
            assert conn.execute(
                """SELECT count(*) FROM schema_migrations
                   WHERE version='016_body_onboarding'"""
            ).fetchone()[0] == 1

            constraints = {
                row[0] for row in conn.execute(
                    """SELECT conname FROM pg_constraint
                       WHERE conrelid='weight_measurements'::regclass"""
                ).fetchall()
            }
            assert 'weight_measurements_user_date_key' in constraints
            assert 'weight_measurements_weight_range' in constraints
            assert 'weight_measurements_height_range' in constraints

            measurement = conn.execute(
                """INSERT INTO weight_measurements
                       (user_id, measured_on, weight_kg, height_cm_snapshot)
                   VALUES (%s, '2026-09-27', 63, 170) RETURNING id""",
                (new_user,),
            ).fetchone()[0]
            conn.execute('DELETE FROM users WHERE id=%s', (new_user,))
            assert conn.execute(
                'SELECT 1 FROM weight_measurements WHERE id=%s',
                (measurement,),
            ).fetchone() is None
    finally:
        with psycopg.connect(dbname='postgres', autocommit=True, **admin) as conn:
            conn.execute(f'DROP DATABASE {database_name} WITH (FORCE)')
