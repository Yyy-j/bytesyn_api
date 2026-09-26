from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from psycopg import errors

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


def test_regenerate_invite_single_pending_connected_and_old_code(context):
    client, users, _ = context
    owner = users[3]
    assert client.post('/pairs/invite-code/regenerate',
                       headers=headers(owner)).status_code == 409
    with get_connection() as conn:
        joiner = conn.execute('INSERT INTO users DEFAULT VALUES RETURNING id').fetchone()['id']

    pending = client.post('/pairs', headers=headers(owner)).json()
    pair_id = pending['pair_id']
    try:
        regenerated = client.post('/pairs/invite-code/regenerate',
                                  headers=headers(owner))
        assert regenerated.status_code == 200, regenerated.text
        result = regenerated.json()
        assert result['pair_id'] == pair_id
        assert result['invite_code'] != pending['invite_code']
        assert result['members'] == pending['members']
        assert result['connected_at'] is None and result['ended_at'] is None

        assert client.post('/pairs/join', headers=headers(joiner), json={
            'invite_code':pending['invite_code']}).status_code == 409
        joined = client.post('/pairs/join', headers=headers(joiner), json={
            'invite_code':result['invite_code']})
        assert joined.status_code == 200, joined.text
        assert joined.json()['connected_at'] is not None
        assert client.post('/pairs/invite-code/regenerate',
                           headers=headers(owner)).status_code == 409
    finally:
        with get_connection() as conn:
            conn.execute('DELETE FROM pairs WHERE id = %s', (pair_id,))
            conn.execute('DELETE FROM users WHERE id = %s', (joiner,))


def test_concurrent_join_and_regenerate_are_serialized(context):
    client, users, _ = context
    owner = users[3]
    with get_connection() as conn:
        joiner = conn.execute('INSERT INTO users DEFAULT VALUES RETURNING id').fetchone()['id']
    pending = client.post('/pairs', headers=headers(owner)).json()
    pair_id = pending['pair_id']
    try:
        with ThreadPoolExecutor(2) as executor:
            join_future = executor.submit(
                client.post, '/pairs/join', headers=headers(joiner),
                json={'invite_code':pending['invite_code']})
            regenerate_future = executor.submit(
                client.post, '/pairs/invite-code/regenerate', headers=headers(owner))
            joined, regenerated = join_future.result(), regenerate_future.result()

        assert sorted([joined.status_code, regenerated.status_code]) == [200, 409]
        with get_connection() as conn:
            pair = conn.execute('''SELECT invite_code, connected_at, ended_at
                FROM pairs WHERE id = %s''', (pair_id,)).fetchone()
            member_count = conn.execute('''SELECT count(*) AS n FROM pair_members
                WHERE pair_id = %s AND left_at IS NULL''', (pair_id,)).fetchone()['n']
        if joined.status_code == 200:
            assert pair['invite_code'] == pending['invite_code']
            assert pair['connected_at'] is not None and member_count == 2
        else:
            assert pair['invite_code'] != pending['invite_code']
            assert pair['connected_at'] is None and member_count == 1
        assert pair['ended_at'] is None
    finally:
        with get_connection() as conn:
            conn.execute('DELETE FROM pairs WHERE id = %s', (pair_id,))
            conn.execute('DELETE FROM users WHERE id = %s', (joiner,))


def test_cancel_pending_preserves_history_and_allows_new_pair(context):
    client, users, _ = context
    owner = users[3]
    personal = client.post('/meals', headers=headers(owner), json={
        'name':'private', 'source':'manual', 'base_calories':100,
        'base_protein':10, 'base_carbs':20, 'base_fat':5,
        'portion_ratio':1, 'share_mode':'solo', 'meal_time':'08:00'}).json()
    pending = client.post('/pairs', headers=headers(owner)).json()
    first_pair_id = pending['pair_id']
    second_pair_id = None
    with get_connection() as conn:
        joiner = conn.execute('INSERT INTO users DEFAULT VALUES RETURNING id').fetchone()['id']
    try:
        assert client.post('/pairs/cancel', headers=headers(owner)).status_code == 204
        assert client.get('/pairs/me', headers=headers(owner)).status_code == 404
        assert client.post('/pairs/join', headers=headers(joiner), json={
            'invite_code':pending['invite_code']}).status_code == 409
        with get_connection() as conn:
            pair = conn.execute('SELECT ended_at FROM pairs WHERE id = %s',
                                (first_pair_id,)).fetchone()
            member = conn.execute('''SELECT left_at FROM pair_members
                WHERE pair_id = %s AND user_id = %s''',
                                  (first_pair_id, owner)).fetchone()
            meal = conn.execute('SELECT pair_id FROM meals WHERE id = %s',
                                (personal['id'],)).fetchone()
        assert pair['ended_at'] is not None
        assert member['left_at'] == pair['ended_at']
        assert meal['pair_id'] is None

        replacement = client.post('/pairs', headers=headers(owner))
        assert replacement.status_code == 201, replacement.text
        second_pair_id = replacement.json()['pair_id']
    finally:
        with get_connection() as conn:
            if second_pair_id is not None:
                conn.execute('DELETE FROM pairs WHERE id = %s', (second_pair_id,))
            conn.execute('DELETE FROM pairs WHERE id = %s', (first_pair_id,))
            conn.execute('DELETE FROM users WHERE id = %s', (joiner,))


def test_end_connected_preserves_memberships_and_allows_repair(context):
    client, users, historical_pair = context
    assert client.post('/pairs/end', headers=headers(users[0])).status_code == 204
    assert client.get('/pairs/me', headers=headers(users[0])).status_code == 404
    assert client.get('/pairs/me', headers=headers(users[1])).status_code == 404
    with get_connection() as conn:
        pair = conn.execute('SELECT ended_at FROM pairs WHERE id = %s',
                            (historical_pair,)).fetchone()
        members = conn.execute('''SELECT user_id, left_at FROM pair_members
            WHERE pair_id = %s ORDER BY user_id''', (historical_pair,)).fetchall()
    assert pair['ended_at'] is not None
    assert len(members) == 2
    assert all(member['left_at'] == pair['ended_at'] for member in members)

    replacement = client.post('/pairs', headers=headers(users[0]))
    assert replacement.status_code == 201, replacement.text
    replacement_id = replacement.json()['pair_id']
    try:
        joined = client.post('/pairs/join', headers=headers(users[1]), json={
            'invite_code':replacement.json()['invite_code']})
        assert joined.status_code == 200, joined.text
    finally:
        with get_connection() as conn:
            conn.execute('DELETE FROM pairs WHERE id = %s', (replacement_id,))


def test_pair_lifecycle_transition_conflicts(context):
    client, users, _ = context
    assert client.post('/pairs/cancel', headers=headers(users[0])).status_code == 409
    assert client.post('/pairs/end', headers=headers(users[2])).status_code == 409
    assert client.post('/pairs/cancel', headers=headers(users[3])).status_code == 409
    assert client.post('/pairs/end', headers=headers(users[3])).status_code == 409


def test_new_pair_mutations_require_authentication(context):
    client = context[0]
    for path in ('/pairs/invite-code/regenerate', '/pairs/cancel', '/pairs/end'):
        assert client.post(path).status_code == 401


def test_membership_history_migration_allows_one_new_active_pair():
    schema = 'membership_history_' + uuid4().hex
    with get_connection() as conn:
        conn.execute(f'CREATE SCHEMA {schema}')
        conn.execute(f'SET search_path TO {schema}, public')
        try:
            for filename in ('001_auth_mvp.sql', '002_pairs.sql', '003_meals_mvp.sql',
                             '014_pair_lifecycle.sql'):
                conn.execute((ROOT/'app/migrations'/filename).read_text())
                conn.execute(f'SET search_path TO {schema}, public')
            user = conn.execute('INSERT INTO users DEFAULT VALUES RETURNING id').fetchone()['id']
            ended = conn.execute("""INSERT INTO pairs
                (invite_code, connected_at, ended_at)
                VALUES ('ENDED', now(), now()) RETURNING id, ended_at""").fetchone()
            conn.execute('INSERT INTO pair_members (pair_id,user_id) VALUES (%s,%s)',
                         (ended['id'], user))
            conn.execute((ROOT/'app/migrations/015_pair_membership_history.sql').read_text())
            conn.execute((ROOT/'app/migrations/015_pair_membership_history.sql').read_text())

            historical = conn.execute('''SELECT left_at FROM pair_members
                WHERE pair_id = %s AND user_id = %s''',
                                      (ended['id'], user)).fetchone()
            assert historical['left_at'] == ended['ended_at']
            active = conn.execute(
                "INSERT INTO pairs (invite_code) VALUES ('ACTIVE') RETURNING id").fetchone()['id']
            conn.execute('INSERT INTO pair_members (pair_id,user_id) VALUES (%s,%s)',
                         (active, user))
            second = conn.execute(
                "INSERT INTO pairs (invite_code) VALUES ('SECOND') RETURNING id").fetchone()['id']
            with pytest.raises(errors.UniqueViolation):
                with conn.transaction():
                    conn.execute('INSERT INTO pair_members (pair_id,user_id) VALUES (%s,%s)',
                                 (second, user))
            assert conn.execute("""SELECT count(*) AS n FROM schema_migrations
                WHERE version = '015_pair_membership_history'""").fetchone()['n'] == 1
        finally:
            conn.execute('SET search_path TO public')
            conn.execute(f'DROP SCHEMA {schema} CASCADE')
