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
    ('get','/meals/recent'), ('get','/meals/reuse?date=2026-09-08'),
    ('post','/meals/favorites'), ('delete',f'/meals/favorites/{uuid4()}'),
    ('get',f'/meals/{uuid4()}'), ('patch',f'/meals/{uuid4()}'),
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
    assert meal['dishes'] == [] and meal['ai_hint'] is None and meal['original_input'] is None
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


@pytest.mark.parametrize('metadata', [
    {'dishes':[{'name':str(i), 'calories':1} for i in range(11)]},
    {'dishes':[{'name':'rice', 'calories':-1}]},
    {'dishes':[{'name':' ', 'calories':1}]},
    {'dishes':[{'name':'rice', 'calories':'NaN'}]},
])
def test_invalid_ai_metadata(context, metadata):
    client, users, _ = context
    assert client.post('/meals', headers=headers(users[0]),
                       json=payload(**metadata)).status_code == 422


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
    # An unpaired user has a valid private Meal scope, but cannot access Pair meals.
    for method in ['get','patch','delete']:
        kwargs = {'json':{'name':'intrusion'}} if method == 'patch' else {}
        assert client.request(method, path, headers=headers(users[3]), **kwargs).status_code == 404
    response = client.post('/meals', headers=headers(users[2]), json=payload(share_mode='shared_half'))
    assert response.status_code == 409


def test_unpaired_user_solo_crud_recent_reuse_and_favorite(context):
    client, users, _ = context
    user = users[3]
    auth = headers(user)
    created = client.post('/meals', headers=auth, json=payload(name='private meal'))
    assert created.status_code == 201, created.text
    meal = created.json()
    assert meal['user_id'] == str(user)
    assert meal['pair_id'] is None
    assert meal['share_mode'] == 'solo'
    assert meal['shared_meal_id'] is None

    path = '/meals/' + meal['id']
    assert client.get(path, headers=auth).json() == meal
    assert client.get('/meals', headers=auth,
                      params={'date':meal['meal_date']}).json() == {'meals':[meal]}
    assert client.get('/meals/recent', headers=auth).json() == {'meals':[meal]}
    reuse = client.get('/meals/reuse', headers=auth,
                       params={'date':meal['meal_date']}).json()['items']
    assert [item['meal_id'] for item in reuse] == [meal['id']]

    favorite = client.post('/meals/favorites', headers=auth,
                           json={'meal_id':meal['id']})
    assert favorite.status_code == 201, favorite.text
    patched = client.patch(path, headers=auth, json={'name':'private updated'})
    assert patched.status_code == 200, patched.text
    assert patched.json()['name'] == 'private updated'
    assert patched.json()['pair_id'] is None
    assert client.delete(path, headers=auth).status_code == 204
    assert client.get(path, headers=auth).status_code == 404


def test_single_scope_security_and_non_solo_rejection(context):
    client, users, _ = context
    pending_user, unpaired_user = users[2], users[3]
    meal = client.post('/meals', headers=headers(unpaired_user),
                       json=payload(name='A private')).json()

    for method in ['get', 'patch', 'delete']:
        kwargs = {'json':{'name':'intrusion'}} if method == 'patch' else {}
        response = client.request(method, '/meals/'+meal['id'],
                                  headers=headers(pending_user), **kwargs)
        assert response.status_code == 404
    listed = client.get('/meals', headers=headers(pending_user),
                        params={'date':meal['meal_date']}).json()['meals']
    assert listed == []

    for user in (pending_user, unpaired_user):
        for mode in ['partner_only', 'shared_half', 'shared_me_one_third',
                     'shared_me_two_thirds']:
            response = client.post('/meals', headers=headers(user),
                                   json=payload(share_mode=mode))
            assert response.status_code == 409
            assert response.json()['detail'] == 'A partner is required for this share mode'


def test_pending_pair_meal_stays_private(context):
    client, users, _ = context
    user = users[2]
    pair = client.get('/pairs/me', headers=headers(user)).json()
    assert len(pair['members']) == 1
    assert pair['connected_at'] is None and pair['ended_at'] is None

    response = client.post('/meals', headers=headers(user), json=payload(name='pending private'))
    assert response.status_code == 201, response.text
    assert response.json()['pair_id'] is None
    with get_connection() as conn:
        stored = conn.execute('SELECT pair_id, share_mode, share_owner_id, shared_meal_id '
                              'FROM meals WHERE id = %s', (response.json()['id'],)).fetchone()
    assert stored == {'pair_id':None, 'share_mode':'solo',
                      'share_owner_id':user, 'shared_meal_id':None}


def test_personal_history_remains_private_after_partner_joins(context):
    client, users, _ = context
    owner, partner = users[3], users[2]
    owner_auth, partner_auth = headers(owner), headers(partner)
    before = client.post('/meals', headers=owner_auth,
                         json=payload(name='before invite')).json()
    pending = client.post('/pairs', headers=owner_auth)
    assert pending.status_code == 201, pending.text
    pair = pending.json()
    pair_id = pair['pair_id']
    try:
        assert pair['connected_at'] is None
        during = client.post('/meals', headers=owner_auth,
                             json=payload(name='while pending')).json()
        assert before['pair_id'] is None and during['pair_id'] is None

        # Release the fixture's unrelated Pending Pair so this user can join A.
        with get_connection() as conn:
            conn.execute('DELETE FROM pair_members WHERE user_id = %s', (partner,))
        joined = client.post('/pairs/join', headers=partner_auth,
                             json={'invite_code':pair['invite_code']})
        assert joined.status_code == 200, joined.text
        assert joined.json()['connected_at'] is not None

        shared = client.post('/meals', headers=owner_auth,
                             json=payload(name='after connected', share_mode='shared_half'))
        assert shared.status_code == 201, shared.text
        assert shared.json()['pair_id'] == pair_id

        meal_date = before['meal_date']
        owner_meals = client.get('/meals', headers=owner_auth,
                                 params={'date':meal_date}).json()['meals']
        partner_meals = client.get('/meals', headers=partner_auth,
                                   params={'date':meal_date}).json()['meals']
        assert {meal['id'] for meal in owner_meals}.issuperset({before['id'], during['id']})
        assert before['id'] not in {meal['id'] for meal in partner_meals}
        assert during['id'] not in {meal['id'] for meal in partner_meals}
        assert len([meal for meal in partner_meals if meal['shared_meal_id']]) == 2

        for old in (before, during):
            assert client.get('/meals/'+old['id'], headers=partner_auth).status_code == 404
            assert client.patch('/meals/'+old['id'], headers=partner_auth,
                                json={'name':'intrusion'}).status_code == 404
            assert client.delete('/meals/'+old['id'], headers=partner_auth).status_code == 404

        owner_summary = client.get('/summary/daily', headers=owner_auth,
                                   params={'date':meal_date}).json()
        partner_summary = client.get('/summary/daily', headers=partner_auth,
                                     params={'date':meal_date}).json()
        assert {meal['id'] for meal in owner_summary['meals']}.issuperset(
            {before['id'], during['id']})
        assert before['id'] not in {meal['id'] for meal in partner_summary['meals']}
        assert during['id'] not in {meal['id'] for meal in partner_summary['meals']}

        # Personal history cannot be converted into Pair scope after connection.
        rejected = client.patch('/meals/'+before['id'], headers=owner_auth,
                                json={'share_mode':'shared_half'})
        assert rejected.status_code == 409
        with get_connection() as conn:
            assert conn.execute('SELECT pair_id FROM meals WHERE id = %s',
                                (before['id'],)).fetchone()['pair_id'] is None

        month = meal_date[:7]
        day_index = int(meal_date[-2:]) - 1
        owner_month = client.get('/summary/monthly', headers=owner_auth,
                                 params={'month':month}).json()['days'][day_index]
        partner_month = client.get('/summary/monthly', headers=partner_auth,
                                   params={'month':month}).json()['days'][day_index]
        assert owner_month['self_calories'] > partner_month['partner_calories']
    finally:
        with get_connection() as conn:
            conn.execute('DELETE FROM meals WHERE pair_id = %s', (pair_id,))
            conn.execute('DELETE FROM pairs WHERE id = %s', (pair_id,))


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


def test_ai_metadata_round_trip_and_patch(context):
    client, users, _ = context
    text = create(context, source='text', original_input='午饭吃了鸡肉咖喱饭')
    assert text['original_input'] == '午饭吃了鸡肉咖喱饭'
    assert client.get('/meals/'+text['id'], headers=headers(users[0])).json() == text

    image = create(context, source='ai', dishes=[
        {'name':'米饭', 'calories':300}, {'name':'咖喱鸡肉', 'calories':420}],
        ai_hint='米饭只有半碗')
    listed = client.get('/meals', headers=headers(users[0]),
                        params={'date':image['meal_date']}).json()['meals']
    stored = next(meal for meal in listed if meal['id'] == image['id'])
    assert stored['dishes'] == [
        {'name':'米饭', 'calories':300}, {'name':'咖喱鸡肉', 'calories':420}]
    assert stored['ai_hint'] == '米饭只有半碗' and stored['original_input'] is None

    patched = client.patch('/meals/'+image['id'], headers=headers(users[0]), json={
        'dishes':[{'name':'咖喱', 'calories':500}], 'ai_hint':None,
        'original_input':'corrected'} )
    assert patched.status_code == 200, patched.text
    assert patched.json()['dishes'] == [{'name':'咖喱', 'calories':500}]
    assert patched.json()['ai_hint'] is None
    assert patched.json()['original_input'] == 'corrected'


def test_shared_meal_metadata_stays_identical(context):
    client, users, _ = context
    meal = create(context, share_mode='shared_half',
                  dishes=[{'name':'饭', 'calories':600}], ai_hint='两人分食')
    rows = group(meal)
    assert rows[0]['dishes'] == rows[1]['dishes']
    sibling_id = str(next(row for row in rows if row['user_id'] == users[1])['id'])
    response = client.patch('/meals/'+sibling_id, headers=headers(users[1]), json={
        'dishes':[{'name':'饭', 'calories':500}], 'ai_hint':'修正',
        'original_input':'shared input'})
    assert response.status_code == 200, response.text
    rows = group(meal)
    for key in ['name', 'base_calories', 'base_protein', 'base_carbs', 'base_fat',
                'portion_ratio', 'share_mode', 'dishes', 'ai_hint', 'original_input']:
        assert rows[0][key] == rows[1][key]


def test_reuse_is_date_scoped_owned_ordered_and_limited(context):
    client, users, _ = context
    own = create(context, name='own', meal_time='10:00')
    partner = client.post('/meals', headers=headers(users[1]),
                          json=payload(name='partner', meal_time='20:00')).json()
    shared = create(context, name='shared', meal_time='18:00', share_mode='shared_half')
    other_date = create(context, name='other date', meal_time='23:00')
    target = '2026-09-13'
    with get_connection() as conn:
        conn.execute('UPDATE meals SET meal_date = %s WHERE id = %s', (target, own['id']))
        conn.execute('UPDATE meals SET meal_date = %s WHERE id = %s', (target, partner['id']))
        conn.execute('UPDATE meals SET meal_date = %s WHERE shared_meal_id = %s',
                     (target, shared['shared_meal_id']))
        conn.execute('UPDATE meals SET meal_date = %s WHERE id = %s',
                     ('2026-09-12', other_date['id']))
    result = client.get('/meals/reuse', headers=headers(users[0]),
                        params={'date':target, 'limit':5}).json()['items']
    assert [meal['name'] for meal in result] == ['shared', 'own']
    assert all(not meal['is_favorite'] and meal['favorite_id'] is None for meal in result)
    limited = client.get('/meals/reuse', headers=headers(users[0]),
                         params={'date':target, 'limit':1}).json()['items']
    assert [meal['name'] for meal in limited] == ['shared']
    assert client.get('/meals/reuse', headers=headers(users[0]),
                      params={'date':target, 'limit':6}).status_code == 422
    assert client.get('/meals/reuse', headers=headers(users[3]),
                      params={'date':target}).json() == {'items':[]}


def test_reuse_without_limit_returns_all_items_for_date(context):
    client, users, _ = context
    target = '2026-09-13'
    meals = [
        create(context, name=f'reusable-{index}', meal_time=f'{10 + index}:00')
        for index in range(7)
    ]
    with get_connection() as conn:
        conn.execute('UPDATE meals SET meal_date = %s WHERE id = ANY(%s)',
                     (target, [meal['id'] for meal in meals]))

    unlimited = client.get('/meals/reuse', headers=headers(users[0]),
                           params={'date':target}).json()['items']
    assert [item['name'] for item in unlimited] == [
        f'reusable-{index}' for index in reversed(range(7))]

    limited = client.get('/meals/reuse', headers=headers(users[0]),
                         params={'date':target, 'limit':5}).json()['items']
    assert [item['name'] for item in limited] == [
        f'reusable-{index}' for index in reversed(range(2, 7))]


def test_favorite_create_duplicate_delete_and_user_isolation(context):
    client, users, _ = context
    meal = create(context, name='favorite', base_calories=321,
                  base_protein=12, base_carbs=34, base_fat=5)
    response = client.post('/meals/favorites', headers=headers(users[0]),
                           json={'meal_id':meal['id']})
    assert response.status_code == 201, response.text
    favorite = response.json()
    assert favorite == {
        'meal_id':meal['id'], 'favorite_id':favorite['favorite_id'],
        'name':'favorite', 'calories':321, 'protein':12, 'carbs':34, 'fat':5,
        'is_favorite':True,
    }

    duplicate = client.post('/meals/favorites', headers=headers(users[0]),
                            json={'meal_id':meal['id']})
    assert duplicate.status_code == 201
    assert duplicate.json() == favorite
    with get_connection() as conn:
        count = conn.execute(
            'SELECT count(*) AS total FROM meal_favorites WHERE user_id = %s',
            (users[0],)).fetchone()['total']
    assert count == 1

    assert client.post('/meals/favorites', headers=headers(users[1]),
                       json={'meal_id':meal['id']}).status_code == 404
    path = '/meals/favorites/' + favorite['favorite_id']
    assert client.delete(path, headers=headers(users[1])).status_code == 404
    assert client.delete(path, headers=headers(users[0])).status_code == 204


def test_favorite_limit_and_reuse_across_dates(context):
    client, users, _ = context
    favorites = []
    for index in range(6):
        meal = create(context, name=f'favorite-{index}', meal_time=f'0{index}:00')
        response = client.post('/meals/favorites', headers=headers(users[0]),
                               json={'meal_id':meal['id']})
        if index < 5:
            assert response.status_code == 201, response.text
            favorites.append(response.json())
        else:
            assert response.status_code == 409
            assert response.json()['detail'] == 'Favorite limit reached'

    for target in ('2026-01-01', '2026-12-31'):
        items = client.get('/meals/reuse', headers=headers(users[0]),
                           params={'date':target, 'limit':5}).json()['items']
        assert [item['favorite_id'] for item in items] == [
            item['favorite_id'] for item in favorites]
        assert len(items) == 5
        assert all(item['is_favorite'] for item in items)


def test_favorite_snapshot_survives_source_meal_delete(context):
    client, users, _ = context
    meal = create(context, name='persistent snapshot', base_calories=456,
                  base_protein=23, base_carbs=45, base_fat=6)
    favorite = client.post('/meals/favorites', headers=headers(users[0]),
                           json={'meal_id':meal['id']}).json()
    assert client.delete('/meals/' + meal['id'],
                         headers=headers(users[0])).status_code == 204

    items = client.get('/meals/reuse', headers=headers(users[0]),
                       params={'date':'1900-01-01', 'limit':5}).json()['items']
    assert items == [favorite | {'meal_id':None}]


def test_reuse_favorites_first_deduplicates_and_fills_remaining(context):
    client, users, _ = context
    target = '2026-09-13'
    favorite_target = create(context, name='favorite target', meal_time='19:00')
    favorite_other = create(context, name='favorite other', meal_time='08:00')
    normal = [
        create(context, name=f'normal-{index}', meal_time=f'{23-index}:00')
        for index in range(4)
    ]
    with get_connection() as conn:
        conn.execute('UPDATE meals SET meal_date = %s WHERE id = %s',
                     (target, favorite_target['id']))
        for meal in normal:
            conn.execute('UPDATE meals SET meal_date = %s WHERE id = %s',
                         (target, meal['id']))
        conn.execute('UPDATE meals SET meal_date = %s WHERE id = %s',
                     ('2026-09-12', favorite_other['id']))
    for meal in (favorite_target, favorite_other):
        assert client.post('/meals/favorites', headers=headers(users[0]),
                           json={'meal_id':meal['id']}).status_code == 201

    items = client.get('/meals/reuse', headers=headers(users[0]),
                       params={'date':target, 'limit':5}).json()['items']
    assert [item['name'] for item in items] == [
        'favorite target', 'favorite other', 'normal-0', 'normal-1', 'normal-2']
    assert [item['is_favorite'] for item in items] == [True, True, False, False, False]
    assert sum(item['meal_id'] == favorite_target['id'] for item in items) == 1


def test_clean_database_migration():
    with get_connection() as conn:
        conn.execute('CREATE SCHEMA clean_compat')
        conn.execute('SET search_path TO clean_compat')
        try:
            for filename in ['001_auth_mvp.sql', '002_pairs.sql', '003_meals_mvp.sql',
                             '004_user_profile_goals.sql', '005_meal_ai_metadata.sql',
                             '004_user_profile_goals.sql', '005_meal_ai_metadata.sql']:
                conn.execute((ROOT/'app/migrations'/filename).read_text())
            assert conn.execute('SELECT count(*) AS n FROM meals').fetchone()['n'] == 0
            assert conn.execute("SELECT count(*) AS n FROM schema_migrations WHERE version IN ('004_user_profile_goals', '005_meal_ai_metadata')").fetchone()['n'] == 2
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
