from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from app.db import get_connection
from conftest import ROOT, headers


def test_pair_pending_then_connected_join_is_atomic(context):
    client, users, _ = context
    owner = users[3]
    with get_connection() as conn:
        joiners = [
            conn.execute('INSERT INTO users DEFAULT VALUES RETURNING id').fetchone()['id']
            for _ in range(2)
        ]

    created = client.post('/pairs', headers=headers(owner))
    assert created.status_code == 201, created.text
    pending = created.json()
    pair_id = pending['pair_id']
    try:
        assert len(pending['members']) == 1
        assert pending['connected_at'] is None
        assert pending['ended_at'] is None
        assert client.get('/pairs/me', headers=headers(owner)).json() == pending

        def join(user):
            return client.post('/pairs/join', headers=headers(user),
                               json={'invite_code':pending['invite_code']})

        with ThreadPoolExecutor(2) as executor:
            responses = list(executor.map(join, joiners))
        assert sorted(response.status_code for response in responses) == [200, 409]
        connected = next(response.json() for response in responses
                         if response.status_code == 200)
        assert len(connected['members']) == 2
        assert connected['connected_at'] is not None
        assert connected['ended_at'] is None

        with get_connection() as conn:
            stored = conn.execute('''SELECT p.connected_at, p.ended_at,
                COUNT(pm.user_id) AS member_count
                FROM pairs p JOIN pair_members pm ON pm.pair_id = p.id
                WHERE p.id = %s GROUP BY p.id''', (pair_id,)).fetchone()
        assert stored['connected_at'] is not None
        assert stored['ended_at'] is None
        assert stored['member_count'] == 2
    finally:
        with get_connection() as conn:
            conn.execute('DELETE FROM pairs WHERE id = %s', (pair_id,))
            conn.execute('DELETE FROM users WHERE id = ANY(%s)', (joiners,))


def test_pair_lifecycle_migration_backfills_without_touching_meals():
    schema = 'pair_lifecycle_' + uuid4().hex
    with get_connection() as conn:
        conn.execute(f'CREATE SCHEMA {schema}')
        conn.execute(f'SET search_path TO {schema}, public')
        try:
            conn.execute((ROOT/'app/migrations/001_auth_mvp.sql').read_text())
            conn.execute(f'SET search_path TO {schema}, public')
            conn.execute((ROOT/'app/migrations/002_pairs.sql').read_text())
            conn.execute((ROOT/'app/migrations/003_meals_mvp.sql').read_text())
            users = [
                conn.execute('INSERT INTO users DEFAULT VALUES RETURNING id').fetchone()['id']
                for _ in range(3)
            ]
            dual = conn.execute("INSERT INTO pairs (invite_code) VALUES ('DUAL') RETURNING id").fetchone()['id']
            pending = conn.execute("INSERT INTO pairs (invite_code) VALUES ('PENDING') RETURNING id").fetchone()['id']
            conn.execute("INSERT INTO pair_members (pair_id,user_id,joined_at) VALUES (%s,%s,'2026-01-01T00:00:00Z')",
                         (dual, users[0]))
            conn.execute("INSERT INTO pair_members (pair_id,user_id,joined_at) VALUES (%s,%s,'2026-01-02T03:04:05Z')",
                         (dual, users[1]))
            conn.execute("INSERT INTO pair_members (pair_id,user_id,joined_at) VALUES (%s,%s,'2026-02-01T00:00:00Z')",
                         (pending, users[2]))
            meal = conn.execute("""INSERT INTO meals
                (user_id, pair_id, name, meal_date) VALUES (%s, %s, 'historical', '2026-01-01')
                RETURNING *""", (users[0], dual)).fetchone()

            conn.execute((ROOT/'app/migrations/014_pair_lifecycle.sql').read_text())
            first = conn.execute('SELECT connected_at, ended_at FROM pairs WHERE id = %s',
                                 (dual,)).fetchone()
            conn.execute((ROOT/'app/migrations/014_pair_lifecycle.sql').read_text())
            second = conn.execute('SELECT connected_at, ended_at FROM pairs WHERE id = %s',
                                  (dual,)).fetchone()
            pending_state = conn.execute(
                'SELECT connected_at, ended_at FROM pairs WHERE id = %s',
                (pending,)).fetchone()
            after_meal = conn.execute('SELECT * FROM meals WHERE id = %s',
                                      (meal['id'],)).fetchone()

            assert first == second
            assert first['connected_at'].isoformat() == '2026-01-02T03:04:05+00:00'
            assert first['ended_at'] is None
            assert pending_state == {'connected_at':None, 'ended_at':None}
            assert after_meal == meal
            assert conn.execute("""SELECT count(*) AS n FROM schema_migrations
                WHERE version = '014_pair_lifecycle'""").fetchone()['n'] == 1
        finally:
            conn.execute('SET search_path TO public')
            conn.execute(f'DROP SCHEMA {schema} CASCADE')
