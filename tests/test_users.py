import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from psycopg.types.json import Jsonb

from app.db import get_connection
from conftest import headers, payload


def add_identity(user, email='person@example.com'):
    with get_connection() as conn:
        conn.execute('''INSERT INTO auth_identities
            (user_id, provider, provider_subject, email) VALUES (%s, 'google', %s, %s)''',
                     (user, str(user), email))


def test_get_me_default_goals(context):
    client, users, _ = context
    add_identity(users[0])
    response = client.get('/users/me', headers=headers(users[0]))
    assert response.status_code == 200
    assert response.json() == {
        'id':str(users[0]), 'email':'person@example.com', 'provider':'google',
        'display_name':None, 'character':'boy',
        'goals':{'calories':2000, 'protein':90, 'carbs':250, 'fat':60},
    }


def test_patch_me_profile_and_partial_goals(context):
    client, users, _ = context
    add_identity(users[0])
    response = client.patch('/users/me', headers=headers(users[0]), json={
        'display_name':'  Harper  ',
        'goals':{'calories':2200, 'protein':120}})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['display_name'] == 'Harper'
    assert result['goals'] == {'calories':2200, 'protein':120, 'carbs':250, 'fat':60}
    with get_connection() as conn:
        row = conn.execute('''SELECT display_name, calorie_goal, protein_goal,
            carbs_goal, updated_at, created_at FROM users WHERE id = %s''',
                           (users[0],)).fetchone()
    assert row['display_name'] == 'Harper' and row['carbs_goal'] is None
    assert row['updated_at'] >= row['created_at']

    cleared = client.patch('/users/me', headers=headers(users[0]),
                           json={'display_name':' ', 'goals':{'protein':None}})
    assert cleared.status_code == 200
    assert cleared.json()['display_name'] is None
    assert cleared.json()['goals']['protein'] == 90


@pytest.mark.parametrize('value', [-1, 'NaN', 'Infinity', '-Infinity'])
def test_patch_me_rejects_invalid_goal(context, value):
    client, users, _ = context
    add_identity(users[0])
    assert client.patch('/users/me', headers=headers(users[0]),
                        json={'goals':{'fat':value}}).status_code == 422


def test_users_me_requires_authentication(context):
    client, _, _ = context
    assert client.get('/users/me').status_code == 401
    assert client.patch('/users/me', json={'display_name':'Harper'}).status_code == 401


def test_patch_me_character_persists_without_changing_profile(context):
    client, users, _ = context
    user = users[0]
    add_identity(user)
    profile = client.patch('/users/me', headers=headers(user), json={
        'display_name':'Harper', 'goals':{'calories':2200, 'protein':120}})
    assert profile.status_code == 200, profile.text

    changed = client.patch(
        '/users/me', headers=headers(user), json={'character':'girl'})
    assert changed.status_code == 200, changed.text
    assert changed.json()['character'] == 'girl'
    assert changed.json()['display_name'] == 'Harper'
    assert changed.json()['goals'] == {
        'calories':2200, 'protein':120, 'carbs':250, 'fat':60}
    assert client.get('/users/me', headers=headers(user)).json()['character'] == 'girl'
    with get_connection() as conn:
        stored = conn.execute(
            'SELECT character FROM users WHERE id = %s', (user,)).fetchone()
    assert stored['character'] == 'girl'


@pytest.mark.parametrize('character', [
    'cat', 'admin', '', 'BODY-BOY', 'mobile/svg/body-boy.svg', None])
def test_patch_me_rejects_invalid_character(context, character):
    client, users, _ = context
    add_identity(users[0])
    response = client.patch(
        '/users/me', headers=headers(users[0]), json={'character':character})
    assert response.status_code == 422


def test_pair_members_include_profile_information(context):
    client, users, _ = context
    for index, user in enumerate(users[:2]):
        add_identity(user, email=f'person-{index}@example.com')
        response = client.patch(
            '/users/me',
            headers=headers(user),
            json={
                'display_name': f'Member {index + 1}',
                'character': 'boy' if index == 0 else 'girl',
            },
        )
        assert response.status_code == 200

    pair = client.get('/pairs/me', headers=headers(users[0]))
    assert pair.status_code == 200
    members = {value['user_id']: value for value in pair.json()['members']}
    assert members[str(users[0])]['display_name'] == 'Member 1'
    assert members[str(users[1])]['display_name'] == 'Member 2'
    assert members[str(users[0])]['character'] == 'boy'
    assert members[str(users[1])]['character'] == 'girl'

    daily = client.get(
        '/summary/daily', headers=headers(users[0]), params={'date':'2026-09-08'})
    assert daily.status_code == 200, daily.text
    assert daily.json()['self_slice']['character'] == 'boy'
    assert daily.json()['partner_slice']['character'] == 'girl'

    monthly = client.get(
        '/summary/monthly', headers=headers(users[0]), params={'month':'2026-09'})
    assert monthly.status_code == 200, monthly.text
    assert monthly.json()['self']['character'] == 'boy'
    assert monthly.json()['partner']['character'] == 'girl'


def test_delete_single_account_removes_all_user_owned_data_and_sessions(context):
    client, users, _ = context
    user = users[3]
    add_identity(user)
    meal = client.post('/meals', headers=headers(user), json=payload(
        source='ai', dishes=[{'name':'private', 'calories':100}],
        ai_hint='private hint', original_input='private input')).json()
    assert client.post('/meals/favorites', headers=headers(user),
                       json={'meal_id':meal['id']}).status_code == 201
    refresh_token = 'delete-account-refresh-token'
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    days = [{'day_index':index, 'items':[]} for index in range(7)]
    with get_connection() as conn:
        conn.execute('''INSERT INTO auth_sessions (user_id,token_hash,expires_at)
            VALUES (%s,%s,%s)''',
                     (user, token_hash, datetime.now(timezone.utc)+timedelta(days=30)))
        conn.execute('INSERT INTO training_templates (user_id,days) VALUES (%s,%s)',
                     (user, Jsonb(days)))
        conn.execute('''INSERT INTO training_weeks
            (user_id,week_id,week_start,week_end,days)
            VALUES (%s,'2026-W39','2026-09-21','2026-09-27',%s)''',
                     (user, Jsonb(days)))
        conn.execute('''INSERT INTO training_custom_exercises
            (user_id,name,default_sets,default_reps)
            VALUES (%s,'private exercise',3,10)''', (user,))
        conn.execute('''INSERT INTO training_exercise_videos
            (user_id,exercise_id,video_url)
            VALUES (%s,'private-video','https://example.com/video')''', (user,))

    response = client.delete('/users/me', headers=headers(user))
    assert response.status_code == 204, response.text
    assert client.post('/auth/refresh', json={
        'refresh_token':refresh_token}).status_code == 401
    with get_connection() as conn:
        assert conn.execute('SELECT 1 FROM users WHERE id = %s', (user,)).fetchone() is None
        for table in ('auth_identities', 'auth_sessions', 'meal_favorites', 'meals',
                      'training_templates', 'training_weeks',
                      'training_custom_exercises', 'training_exercise_videos'):
            assert conn.execute(f'SELECT count(*) AS n FROM {table} WHERE user_id = %s',
                                (user,)).fetchone()['n'] == 0


def test_delete_pending_account_ends_invite_without_orphan(context):
    client, users, _ = context
    user, joiner = users[2], users[3]
    pending = client.get('/pairs/me', headers=headers(user)).json()
    personal = client.post('/meals', headers=headers(user),
                           json=payload(name='pending private')).json()
    assert personal['pair_id'] is None

    assert client.delete('/users/me', headers=headers(user)).status_code == 204
    assert client.post('/pairs/join', headers=headers(joiner), json={
        'invite_code':pending['invite_code']}).status_code == 409
    with get_connection() as conn:
        pair = conn.execute('SELECT ended_at FROM pairs WHERE id = %s',
                            (pending['pair_id'],)).fetchone()
        assert pair['ended_at'] is not None
        assert conn.execute('SELECT count(*) AS n FROM pair_members WHERE pair_id = %s',
                            (pending['pair_id'],)).fetchone()['n'] == 0
        assert conn.execute('SELECT 1 FROM meals WHERE id = %s',
                            (personal['id'],)).fetchone() is None


def test_delete_connected_member_preserves_partner_and_allocation(context):
    client, users, pair_id = context
    deleted_user, partner = users[:2]
    shared = client.post('/meals', headers=headers(deleted_user),
                         json=payload(name='shared history', share_mode='shared_half')).json()
    with get_connection() as conn:
        partner_row = conn.execute('''SELECT id FROM meals
            WHERE shared_meal_id = %s AND user_id = %s''',
                                   (shared['shared_meal_id'], partner)).fetchone()
    assert client.delete('/users/me', headers=headers(deleted_user)).status_code == 204

    assert client.get('/pairs/me', headers=headers(partner)).status_code == 404
    preserved = client.get('/meals/'+str(partner_row['id']), headers=headers(partner))
    assert preserved.status_code == 200, preserved.text
    assert preserved.json()['user_id'] == str(partner)
    with get_connection() as conn:
        pair = conn.execute('SELECT ended_at FROM pairs WHERE id = %s',
                            (pair_id,)).fetchone()
        allocation = conn.execute('''SELECT user_id, share_owner_id FROM meals
            WHERE id = %s''', (partner_row['id'],)).fetchone()
        assert conn.execute('SELECT 1 FROM users WHERE id = %s',
                            (deleted_user,)).fetchone() is None
        assert conn.execute('SELECT 1 FROM users WHERE id = %s',
                            (partner,)).fetchone() is not None
    assert pair['ended_at'] is not None
    assert allocation == {'user_id':partner, 'share_owner_id':None}

    solo = client.post('/meals', headers=headers(partner), json=payload(name='after delete'))
    assert solo.status_code == 201, solo.text
    assert solo.json()['pair_id'] is None
    replacement = client.post('/pairs', headers=headers(partner))
    assert replacement.status_code == 201, replacement.text
    with get_connection() as conn:
        conn.execute('DELETE FROM pairs WHERE id = %s', (replacement.json()['pair_id'],))


def test_delete_account_requires_authentication(context):
    assert context[0].delete('/users/me').status_code == 401


def test_delete_account_rolls_back_everything_on_failure(context):
    client, users, _ = context
    user = users[3]
    add_identity(user)
    token_hash = hashlib.sha256(b'rollback-refresh').hexdigest()
    with get_connection() as conn:
        conn.execute('''INSERT INTO auth_sessions (user_id,token_hash,expires_at)
            VALUES (%s,%s,now() + interval '30 days')''', (user, token_hash))
        conn.execute("""CREATE FUNCTION fail_account_delete() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'forced rollback'; END; $$""")
        conn.execute('''CREATE TRIGGER fail_account_delete BEFORE DELETE ON users
            FOR EACH ROW EXECUTE FUNCTION fail_account_delete()''')
    try:
        response = client.delete('/users/me', headers=headers(user))
        assert response.status_code == 503
        assert response.json() == {'detail':'Database unavailable'}
        with get_connection() as conn:
            assert conn.execute('SELECT 1 FROM users WHERE id = %s',
                                (user,)).fetchone() is not None
            assert conn.execute('SELECT 1 FROM auth_identities WHERE user_id = %s',
                                (user,)).fetchone() is not None
            assert conn.execute('SELECT 1 FROM auth_sessions WHERE user_id = %s',
                                (user,)).fetchone() is not None
    finally:
        with get_connection() as conn:
            conn.execute('DROP TRIGGER fail_account_delete ON users')
            conn.execute('DROP FUNCTION fail_account_delete()')
