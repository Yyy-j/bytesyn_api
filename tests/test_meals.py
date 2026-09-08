from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from psycopg import sql

from app.db import get_connection
from conftest import headers, payload, ROOT


def create(context, **changes):
    client, users, _ = context
    response = client.post('/meals', headers=headers(users[0]), json=payload(**changes))
    assert response.status_code == 201, response.text
    return response.json()


def group(meal):
    with get_connection() as conn:
        return conn.execute('SELECT * FROM meals WHERE shared_meal_id = %s ORDER BY user_id',
                            (meal['shared_meal_id'],)).fetchall()


@pytest.mark.parametrize('method,path', [('post','/meals'), ('get','/meals?date=2026-09-08'),
    ('get','/meals/recent'), ('get',f'/meals/{uuid4()}'), ('patch',f'/meals/{uuid4()}'),
    ('delete',f'/meals/{uuid4()}')])
def test_unauthenticated(context, method, path):
    client, _, _ = context
    assert client.request(method, path).status_code == 401


def test_solo_crud_and_recent(context):
    client, users, pair = context
    meal = create(context, base_calories=123.456789, portion_ratio=1.25)
    assert meal['pair_id'] == str(pair) and meal['user_id'] == str(users[0])
    assert meal['base_calories'] == 123.456789 and meal['calories'] == 154.32
    assert meal['shared_meal_id'] is None and meal['share_ratio'] == 1
    assert meal['meal_time'] == '12:30'
    datetime.fromisoformat(meal['updated_at'])
    with get_connection() as conn:
        assert conn.execute('SELECT base_calories FROM meals WHERE id = %s', (meal['id'],)).fetchone()['base_calories'] == Decimal('123.456789')
    auth = headers(users[0])
    path = '/meals/' + meal['id']
    assert client.get(path, headers=auth).json() == meal
    assert client.get('/meals', params={'date':meal['meal_date']}, headers=headers(users[1])).json() == {'meals':[meal]}
    assert client.get('/meals?date=1900-01-01', headers=auth).json() == {'meals':[]}
    assert client.get('/meals/recent', headers=auth).json() == {'meals':[meal]}
    updated = client.patch(path, headers=auth, json={'name':'Dinner','base_calories':200,
                            'meal_time':'18:00', 'expected_updated_at':meal['updated_at']})
    assert updated.status_code == 200, updated.text
    assert updated.json()['calories'] == 250 and updated.json()['name'] == 'Dinner'
    assert updated.json()['base_calories'] == 200
    assert client.patch(path, headers=auth, json={'name':'stale','expected_updated_at':meal['updated_at']}).status_code == 409
    assert client.delete(path, headers=auth).status_code == 204
    assert client.get(path, headers=auth).status_code == 404


@pytest.mark.parametrize('mode,ratios', [('shared_half',[.5,.5]), ('shared_me_one_third',[1/3,2/3]), ('shared_me_two_thirds',[2/3,1/3])])
def test_shared_lifecycle(context, mode, ratios):
    client, users, _ = context
    meal = create(context, share_mode=mode, base_calories=100, portion_ratio=1.1)
    rows = group(meal)
    assert len(rows) == 2
    by_user = {str(r['user_id']):r for r in rows}
    for user, ratio in zip(users, ratios):
        assert float(by_user[str(user)]['share_ratio']) == pytest.approx(ratio)
    assert all(r['base_calories'] == 100 for r in rows)
    assert len(client.get('/meals/recent', headers=headers(users[0])).json()['meals']) == 1
    sibling = by_user[str(users[1])]
    response = client.patch('/meals/'+str(sibling['id']), headers=headers(users[1]), json={
        'name':'Edited by partner', 'base_calories':333.333333, 'base_protein':19.876,
        'base_carbs':40.234, 'base_fat':7.891, 'portion_ratio':2, 'share_mode':'shared_half',
        'meal_time':'19:45','expected_updated_at':meal['updated_at']})
    assert response.status_code == 200, response.text
    rows = group(meal)
    assert all(r['name'] == 'Edited by partner' and r['calories'] == Decimal('333.33')
               and r['protein'] == Decimal('19.88') and r['carbs'] == Decimal('40.23')
               and r['fat'] == Decimal('7.89') and r['meal_time'].isoformat() == '19:45:00'
               and r['meal_date'].isoformat() == meal['meal_date'] for r in rows)
    assert rows[0]['updated_at'] == rows[1]['updated_at']
    assert client.patch('/meals/'+meal['id'], headers=headers(users[0]), json={
        'name':'stale','expected_updated_at':meal['updated_at']}).status_code == 409
    assert client.delete('/meals/'+str(sibling['id']), headers=headers(users[1])).status_code == 204
    assert group(meal) == []


@pytest.mark.parametrize('operation', ['INSERT', 'UPDATE', 'DELETE'])
def test_shared_failure_rolls_back(context, operation):
    client, users, pair = context
    meal = create(context, share_mode='shared_half') if operation != 'INSERT' else None
    before = group(meal) if meal else []
    # A sequence is intentionally nontransactional: fail on the SECOND row mutation.
    with get_connection() as conn:
        conn.execute('CREATE SEQUENCE fail_meal_counter')
        conn.execute("""CREATE FUNCTION fail_second_meal() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF nextval('fail_meal_counter') = 2 THEN
                    RAISE EXCEPTION 'secret SQL password must never reach client';
                END IF;
                IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
                RETURN NEW;
            END; $$""")
        conn.execute(sql.SQL('CREATE TRIGGER fail_meals BEFORE {} ON meals '
                             'FOR EACH ROW EXECUTE FUNCTION fail_second_meal()').format(sql.SQL(operation)))
    try:
        if operation == 'INSERT':
            response = client.post('/meals', headers=headers(users[0]), json=payload(share_mode='shared_half'))
        elif operation == 'UPDATE':
            response = client.patch('/meals/'+meal['id'], headers=headers(users[0]), json={'name':'must roll back'})
        else:
            response = client.delete('/meals/'+meal['id'], headers=headers(users[0]))
        assert response.status_code == 503
        assert response.json() == {'detail':'Database unavailable'}
        if meal:
            assert group(meal) == before
        else:
            with get_connection() as conn:
                assert conn.execute('SELECT count(*) AS n FROM meals WHERE pair_id = %s', (pair,)).fetchone()['n'] == 0
    finally:
        with get_connection() as conn:
            conn.execute('DROP TRIGGER fail_meals ON meals')
            conn.execute('DROP FUNCTION fail_second_meal()')
            conn.execute('DROP SEQUENCE fail_meal_counter')


@pytest.mark.parametrize('change', [dict(user_id=str(uuid4())),dict(pair_id=str(uuid4())),
    dict(meal_date='2026-01-01'),dict(base_calories=-1),dict(portion_ratio=0),
    dict(share_mode='invalid'),dict(source='camera'),dict(meal_time='24:00'),dict(name=' '),
    dict(base_fat='NaN'),dict(base_calories=99999999,portion_ratio=100)])
def test_invalid_input(context, change):
    client, users, _ = context
    assert client.post('/meals', headers=headers(users[0]), json=payload(**change)).status_code == 422


@pytest.mark.parametrize('query', ['limit=0','limit=11','limit=x'])
def test_invalid_recent_limit(context, query):
    client, users, _ = context
    assert client.get('/meals/recent?'+query, headers=headers(users[0])).status_code == 422


def test_pair_authorization(context):
    client, users, _ = context
    meal = create(context)
    path = '/meals/'+meal['id']
    for method in ['get','patch','delete']:
        kwargs = {'json':{'name':'intrusion'}} if method == 'patch' else {}
        assert client.request(method, path, headers=headers(users[2]), **kwargs).status_code == 404
    for method, route in [('post','/meals'),('get','/meals?date='+meal['meal_date']),
        ('get','/meals/recent'),('get',path),('patch',path),('delete',path)]:
        kwargs = {'json':payload()} if method == 'post' else {'json':{}} if method == 'patch' else {}
        result = client.request(method, route, headers=headers(users[3]), **kwargs)
        assert result.status_code == 404 and result.json()['detail'] == 'Current pair not found'
    response = client.post('/meals', headers=headers(users[2]), json=payload(share_mode='shared_half'))
    assert response.status_code == 409


def test_partner_only_and_mode_transitions(context):
    client, users, _ = context
    meal = create(context, share_mode='partner_only')
    assert meal['user_id'] == str(users[1]) and meal['shared_meal_id'] is None
    assert meal['share_ratio'] == 1
    response = client.patch('/meals/'+meal['id'], headers=headers(users[1]), json={'share_mode':'shared_me_one_third'})
    assert response.status_code == 200, response.text
    shared = response.json()
    assert len(group(shared)) == 2
    response = client.patch('/meals/'+shared['id'], headers=headers(users[0]), json={'share_mode':'solo'})
    assert response.status_code == 200
    assert response.json()['user_id'] == str(users[0]) and response.json()['shared_meal_id'] is None
    assert group(shared) == []


def test_concurrent_optimistic_updates(context):
    client, users, _ = context
    meal = create(context, share_mode='shared_half')
    rows = group(meal)
    def update(i):
        return client.patch('/meals/'+str(rows[i]['id']), headers=headers(users[i]), json={
            'name':f'writer {i}', 'expected_updated_at':meal['updated_at']}).status_code
    with ThreadPoolExecutor(2) as executor:
        assert sorted(executor.map(update, [0,1])) == [200,409]
    rows = group(meal)
    assert rows[0]['name'] == rows[1]['name']


def test_repeated_patch_no_rounding_drift(context):
    client, users, _ = context
    meal = create(context, share_mode='shared_me_one_third', base_calories=1.005)
    path = '/meals/'+meal['id']
    for portion in [2, 1, 3, 1]:
        response = client.patch(path, headers=headers(users[0]), json={'portion_ratio':portion})
        assert response.status_code == 200
    assert response.json()['base_calories'] == 1.005
    assert response.json()['calories'] == .34


def test_invalid_patch_and_dates(context):
    client, users, _ = context
    meal = create(context)
    for patch in [{'name':None}, {'source':'ai'}, {'expected_updated_at':'2026-01-01T00:00:00'}, {'name':' '}]:
        assert client.patch('/meals/'+meal['id'], headers=headers(users[0]), json=patch).status_code == 422
    assert client.get('/meals?date=2026-02-30', headers=headers(users[0])).status_code == 422
    assert client.get('/meals', headers=headers(users[0])).status_code == 422


def test_migration_preserves_populated_nas_schema():
    # Separate schema with the exact NAS table fixture, including nullable legacy base values.
    with get_connection() as conn:
        conn.execute('CREATE SCHEMA legacy_compat')
        conn.execute('SET LOCAL search_path TO legacy_compat, public')
        conn.execute((ROOT/'app/migrations/001_auth_mvp.sql').read_text())
        # Migration COMMIT resets SET LOCAL, so explicitly set session search_path.
        conn.execute('SET search_path TO legacy_compat, public')
        conn.execute((ROOT/'app/migrations/002_pairs.sql').read_text())
        fixture = (ROOT/'tests/fixtures/nas_meals.sql').read_text().replace('public.', 'legacy_compat.')
        conn.execute(fixture)
        user = conn.execute('INSERT INTO legacy_compat.users DEFAULT VALUES RETURNING id').fetchone()['id']
        conn.execute("INSERT INTO legacy_compat.meals (user_id,name,calories,meal_date,hint) VALUES (%s,'legacy',12.34,'2025-01-01','preserve')", (user,))
        before = conn.execute('SELECT * FROM legacy_compat.meals').fetchone()
        for _ in range(2):
            conn.execute((ROOT/'app/migrations/003_meals_mvp.sql').read_text())
        after = conn.execute('SELECT * FROM legacy_compat.meals').fetchone()
        assert {k:after[k] for k in before} == before
        assert after['share_owner_id'] is None
        assert conn.execute("SELECT count(*) AS n FROM legacy_compat.schema_migrations WHERE version = '003_meals_mvp'").fetchone()['n'] == 1
        conn.execute('SET search_path TO public')
        conn.execute('DROP SCHEMA legacy_compat CASCADE')


def test_recent_default_limit_and_order(context):
    client, users, _ = context
    meals = [create(context, name=f'Meal {i}', meal_time=f'{10+i}:00') for i in range(5)]
    response = client.get('/meals/recent', headers=headers(users[0])).json()['meals']
    assert [m['id'] for m in response] == [m['id'] for m in reversed(meals[2:])]
    assert len(client.get('/meals/recent?limit=1', headers=headers(users[0])).json()['meals']) == 1
    assert len(client.get('/meals/recent?limit=10', headers=headers(users[0])).json()['meals']) == 5


@pytest.mark.parametrize('source', ['manual', 'ai', 'text'])
def test_sources(context, source):
    assert create(context, source=source)['source'] == source


def test_clean_database_migration():
    with get_connection() as conn:
        conn.execute('CREATE SCHEMA clean_compat')
        conn.execute('SET search_path TO clean_compat')
        try:
            for filename in ['001_auth_mvp.sql', '002_pairs.sql', '003_meals_mvp.sql', '003_meals_mvp.sql']:
                conn.execute((ROOT/'app/migrations'/filename).read_text())
            assert conn.execute('SELECT count(*) AS n FROM meals').fetchone()['n'] == 0
        finally:
            conn.execute('SET search_path TO public')
            conn.execute('DROP SCHEMA clean_compat CASCADE')


@pytest.mark.parametrize('mode', [
    'solo', 'partner_only', 'shared_half',
    'shared_me_one_third', 'shared_me_two_thirds',
])
@pytest.mark.parametrize('method', ['post', 'patch'])
def test_official_share_modes_round_trip(context, mode, method):
    client, users, pair = context
    auth = headers(users[0])
    if method == 'post':
        response = client.post('/meals', headers=auth, json=payload(share_mode=mode))
        assert response.status_code == 201, response.text
    else:
        initial = create(context)
        response = client.patch('/meals/'+initial['id'], headers=auth, json={
            'share_mode':mode, 'expected_updated_at':initial['updated_at']})
        assert response.status_code == 200, response.text
    meal = response.json()
    assert meal['share_mode'] == mode
    assert client.get('/meals/'+meal['id'], headers=auth).json()['share_mode'] == mode
    listed = client.get('/meals', headers=auth, params={'date':meal['meal_date']}).json()['meals']
    assert len(listed) == (2 if mode.startswith('shared_') else 1)
    assert all(row['share_mode'] == mode for row in listed)
    recent = client.get('/meals/recent', headers=auth).json()['meals']
    assert len(recent) == 1 and recent[0]['share_mode'] == mode
    with get_connection() as conn:
        stored = conn.execute('SELECT share_mode FROM meals WHERE pair_id = %s', (pair,)).fetchall()
        assert len(stored) == len(listed)
        assert all(row['share_mode'] == mode for row in stored)


@pytest.mark.parametrize('mode', ['ta_only', 'half', 'me_1_3', 'me_2_3'])
@pytest.mark.parametrize('method', ['post', 'patch'])
def test_retired_share_modes_rejected(context, mode, method):
    client, users, pair = context
    auth = headers(users[0])
    if method == 'post':
        response = client.post('/meals', headers=auth, json=payload(share_mode=mode))
        expected_count = 0
    else:
        meal = create(context)
        response = client.patch('/meals/'+meal['id'], headers=auth, json={'share_mode':mode})
        assert client.get('/meals/'+meal['id'], headers=auth).json() == meal
        expected_count = 1
    assert response.status_code == 422, response.text
    assert any(error['loc'] == ['body', 'share_mode'] for error in response.json()['detail'])
    with get_connection() as conn:
        assert conn.execute('SELECT count(*) AS n FROM meals WHERE pair_id = %s', (pair,)).fetchone()['n'] == expected_count
