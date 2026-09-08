"""Integration tests require a disposable PostgreSQL database named bytesync_meals_test."""
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

# Explicit test-only database; never read .env.runtime or use production defaults.
os.environ.update(DATABASE_HOST=os.environ.get('MEALS_TEST_HOST', '127.0.0.1'),
                  DATABASE_PORT=os.environ.get('MEALS_TEST_PORT', '5432'),
                  DATABASE_NAME='bytesync_meals_test', DATABASE_USER='postgres',
                  DATABASE_PASSWORD='test-only', JWT_SECRET='meals-test-only-secret-' * 3)
from app.auth import create_access_token
from app.main import app
from app.db import get_connection

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='session', autouse=True)
def database():
    with psycopg.connect(host=os.environ['DATABASE_HOST'], port=os.environ['DATABASE_PORT'],
                         dbname='postgres', user='postgres', password='test-only',
                         autocommit=True) as conn:
        conn.execute('CREATE DATABASE bytesync_meals_test')
    with get_connection() as conn:
        conn.execute((ROOT / 'app/migrations/001_auth_mvp.sql').read_text())
        conn.execute((ROOT / 'app/migrations/002_pairs.sql').read_text())
        conn.execute((ROOT / 'tests/fixtures/nas_meals.sql').read_text())
        conn.execute((ROOT / 'app/migrations/003_meals_mvp.sql').read_text())
        conn.execute((ROOT / 'app/migrations/003_meals_mvp.sql').read_text())
    yield
    with psycopg.connect(host=os.environ['DATABASE_HOST'], port=os.environ['DATABASE_PORT'],
                         dbname='postgres', user='postgres', password='test-only',
                         autocommit=True) as conn:
        conn.execute('DROP DATABASE bytesync_meals_test WITH (FORCE)')


@pytest.fixture
def context():
    with get_connection() as conn:
        users = [conn.execute('INSERT INTO users DEFAULT VALUES RETURNING id').fetchone()['id']
                 for _ in range(4)]
        pair = conn.execute('INSERT INTO pairs (invite_code) VALUES (%s) RETURNING id',
                            (str(uuid4()),)).fetchone()['id']
        for user in users[:2]:
            conn.execute('INSERT INTO pair_members (pair_id, user_id) VALUES (%s, %s)', (pair, user))
        other_pair = conn.execute('INSERT INTO pairs (invite_code) VALUES (%s) RETURNING id',
                                  (str(uuid4()),)).fetchone()['id']
        conn.execute('INSERT INTO pair_members (pair_id, user_id) VALUES (%s, %s)', (other_pair, users[2]))
    with TestClient(app) as client:
        yield client, users, pair
    with get_connection() as conn:
        conn.execute('DELETE FROM meals WHERE pair_id = ANY(%s)', ([pair, other_pair],))
        conn.execute('DELETE FROM pairs WHERE id = ANY(%s)', ([pair, other_pair],))
        conn.execute('DELETE FROM users WHERE id = ANY(%s)', (users,))


def headers(user):
    return {'Authorization': 'Bearer ' + create_access_token(user)}


def payload(**changes):
    return dict(name='Lunch', source='manual', base_calories=601.23, base_protein=30.12,
                base_carbs=70.45, base_fat=20.67, portion_ratio=1, share_mode='solo',
                meal_time='12:30') | changes
