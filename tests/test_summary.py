from decimal import Decimal

import pytest

from app.db import get_connection
from conftest import headers, payload

DATE = '2026-09-08'
GOALS = {'calorie_goal':2000, 'protein_goal':90, 'carbs_goal':250, 'fat_goal':60}
ZERO = {'calories':0, 'protein':0, 'carbs':0, 'fat':0}


def meal_for(context, user, date=DATE, **changes):
    client, _, _ = context
    response = client.post('/meals', headers=headers(user), json=payload(**changes))
    assert response.status_code == 201, response.text
    meal = response.json()
    with get_connection() as conn:
        if meal['shared_meal_id']:
            conn.execute('UPDATE meals SET meal_date = %s WHERE shared_meal_id = %s',
                         (date, meal['shared_meal_id']))
        else:
            conn.execute('UPDATE meals SET meal_date = %s WHERE id = %s', (date, meal['id']))
    return meal


def summary(context, user, date=DATE):
    response = context[0].get('/summary/daily', headers=headers(user), params={'date':date})
    assert response.status_code == 200, response.text
    return response.json()


def monthly(context, user, month='2026-09'):
    response = context[0].get('/summary/monthly', headers=headers(user), params={'month':month})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('auth', [{}, {'Authorization':'Bearer invalid'}, {'Authorization':'Basic invalid'}])
def test_summary_unauthenticated(context, auth):
    for path, params in [('/summary/daily', {'date':DATE}),
                         ('/summary/monthly', {'month':'2026-09'})]:
        response = context[0].get(path, params=params, headers=auth)
        assert response.status_code == 401


def test_summary_unpaired(context):
    response = context[0].get('/summary/daily', params={'date':DATE}, headers=headers(context[1][3]))
    assert response.status_code == 404
    assert response.json() == {'detail':'Current pair not found'}


def test_summary_one_member_empty(context):
    user = context[1][2]
    result = summary(context, user)
    assert result == dict(date=DATE, **ZERO, meal_count=0, meals=[],
                         self_slice=dict(user_id=str(user), display_name='未命名成员',
                                         character='boy', **ZERO),
                         partner_slice=None, self_goals=GOALS, partner_goals=None)


def test_summary_one_member_meals_and_stored_totals(context):
    client, users, _ = context
    meal = meal_for(context, users[2], base_calories=900, portion_ratio=2)
    # Deliberately differ from base × portion. Summary must use persisted final values.
    with get_connection() as conn:
        conn.execute('UPDATE meals SET calories=%s, protein=%s, carbs=%s, fat=%s WHERE id=%s',
                     (Decimal('0.10'), Decimal('0.20'), Decimal('0.30'), Decimal('0.40'), meal['id']))
    second = meal_for(context, users[2])
    with get_connection() as conn:
        conn.execute('UPDATE meals SET calories=%s, protein=%s, carbs=%s, fat=%s WHERE id=%s',
                     (Decimal('0.20'), Decimal('0.30'), Decimal('0.40'), Decimal('0.50'), second['id']))
    result = summary(context, users[2])
    expected = dict(calories=.3, protein=.5, carbs=.7, fat=.9)
    assert {key:result[key] for key in expected} == expected
    assert {key:result['self_slice'][key] for key in expected} == expected
    assert result['meal_count'] == 2
    assert result['partner_slice'] is None and result['partner_goals'] is None
    listed = client.get('/meals', headers=headers(users[2]), params={'date':DATE}).json()['meals']
    assert result['meals'] == listed
    assert all(isinstance(result[key], (int,float)) for key in expected)


def test_summary_two_members_shared_and_viewer_perspective(context):
    client, users, _ = context
    meal_for(context, users[0], base_calories=100, base_protein=10, base_carbs=20, base_fat=4)
    meal_for(context, users[1], base_calories=200, base_protein=20, base_carbs=40, base_fat=8)
    meal_for(context, users[0], share_mode='shared_me_one_third', base_calories=300,
             base_protein=30, base_carbs=60, base_fat=12)
    result = summary(context, users[0])
    assert {key:result[key] for key in ZERO} == dict(calories=600,protein=60,carbs=120,fat=24)
    assert result['meal_count'] == 4  # Both persisted shared allocations count.
    assert result['self_slice'] == dict(user_id=str(users[0]), display_name='未命名成员',
                                       character='boy',
                                       calories=200,protein=20,carbs=40,fat=8)
    assert result['partner_slice'] == dict(user_id=str(users[1]), display_name='未命名成员',
                                          character='boy',
                                          calories=400,protein=40,carbs=80,fat=16)
    assert result['self_goals'] == result['partner_goals'] == GOALS
    assert result['meals'] == client.get('/meals', headers=headers(users[0]), params={'date':DATE}).json()['meals']
    reverse = summary(context, users[1])
    assert reverse['self_slice'] == result['partner_slice']
    assert reverse['partner_slice'] == result['self_slice']
    assert reverse['meals'] == result['meals']


def test_summary_two_members_empty(context):
    result = summary(context, context[1][0])
    assert result['meal_count'] == 0 and result['meals'] == []
    assert result['partner_slice']['user_id'] == str(context[1][1])
    assert {key:result['partner_slice'][key] for key in ZERO} == ZERO
    assert result['partner_goals'] == GOALS


def test_summary_date_and_cross_pair_isolation(context):
    _, users, _ = context
    included = meal_for(context, users[0], base_calories=10)
    meal_for(context, users[0], date='2026-09-09', base_calories=20)
    meal_for(context, users[2], base_calories=30)
    result = summary(context, users[0])
    assert result['calories'] == 10 and result['meal_count'] == 1
    assert [row['id'] for row in result['meals']] == [included['id']]
    assert summary(context, users[0], '2026-09-09')['calories'] == 20
    assert summary(context, users[2])['calories'] == 30
    assert summary(context, users[0], '1900-01-01')['meal_count'] == 0
    spoof = context[0].get('/summary/daily', headers=headers(users[2]),
                          params={'date':DATE, 'pair_id':str(context[2]), 'user_id':str(users[0])})
    assert spoof.status_code == 200
    assert spoof.json()['calories'] == 30
    assert spoof.json()['self_slice']['user_id'] == str(users[2])


@pytest.mark.parametrize('params', [{}, {'date':'invalid'}, {'date':'2026-02-30'}])
def test_summary_invalid_date(context, params):
    response = context[0].get('/summary/daily', headers=headers(context[1][0]), params=params)
    assert response.status_code == 422


def test_summary_nas_display_names(context):
    users = context[1]
    with get_connection() as conn:
        conn.execute('UPDATE users SET display_name = %s WHERE id = %s', ('小明',users[0]))
        conn.execute('UPDATE users SET display_name = %s WHERE id = %s', ('小红',users[1]))
    result = summary(context, users[0])
    assert result['self_slice']['display_name'] == '小明'
    assert result['partner_slice']['display_name'] == '小红'
    assert summary(context, users[2])['self_slice']['display_name'] == '未命名成员'


def test_summary_uses_member_goals_with_per_field_fallback(context):
    users = context[1]
    with get_connection() as conn:
        conn.execute('''UPDATE users SET calorie_goal = 2200, protein_goal = 120,
            carbs_goal = NULL, fat_goal = 65 WHERE id = %s''', (users[0],))
        conn.execute('''UPDATE users SET calorie_goal = 1800, protein_goal = NULL,
            carbs_goal = 200, fat_goal = 55 WHERE id = %s''', (users[1],))
    result = summary(context, users[0])
    assert result['self_goals'] == {
        'calorie_goal':2200, 'protein_goal':120, 'carbs_goal':250, 'fat_goal':65}
    assert result['partner_goals'] == {
        'calorie_goal':1800, 'protein_goal':90, 'carbs_goal':200, 'fat_goal':55}


@pytest.mark.parametrize('params', [{}, {'month':'2026-9'}, {'month':'2026-00'},
    {'month':'2026-13'}, {'month':'abc'}, {'month':'2026/09'}])
def test_monthly_invalid_month(context, params):
    response = context[0].get('/summary/monthly', headers=headers(context[1][0]), params=params)
    assert response.status_code == 422


def test_monthly_unpaired(context):
    response = context[0].get('/summary/monthly', headers=headers(context[1][3]),
                               params={'month':'2026-09'})
    assert response.status_code == 404
    assert response.json() == {'detail':'Current pair not found'}


@pytest.mark.parametrize('month,length', [('2026-02',28), ('2026-09',30),
    ('2026-10',31), ('2028-02',29)])
def test_monthly_empty_month_contains_every_day(context, month, length):
    result = monthly(context, context[1][0], month)
    assert result['month'] == month
    assert len(result['days']) == length
    assert result['days'][0]['date'] == month + '-01'
    assert result['days'][-1]['date'].startswith(month + '-')
    assert all(day['self_calories'] == 0 and day['partner_calories'] == 0
               for day in result['days'])


def test_monthly_cross_month_and_pair_isolation(context):
    _, users, _ = context
    meal_for(context, users[0], date='2026-08-31', base_calories=10)
    meal_for(context, users[0], date='2026-09-01', base_calories=100)
    meal_for(context, users[0], date='2026-09-30', base_calories=300)
    meal_for(context, users[0], date='2026-10-01', base_calories=1000)
    meal_for(context, users[2], date='2026-09-15', base_calories=9000)

    result = monthly(context, users[0])
    by_date = {day['date']: day for day in result['days']}
    assert by_date['2026-09-01']['self_calories'] == 100
    assert by_date['2026-09-30']['self_calories'] == 300
    assert by_date['2026-09-15']['self_calories'] == 0
    assert sum(day['self_calories'] for day in result['days']) == 400

    other_pair = monthly(context, users[2])
    assert other_pair['days'][14]['self_calories'] == 9000


def test_monthly_goals_names_and_viewer_perspective(context):
    _, users, _ = context
    with get_connection() as conn:
        conn.execute('UPDATE users SET display_name=%s, calorie_goal=%s WHERE id=%s',
                     ('小明', 2200, users[0]))
        conn.execute('UPDATE users SET display_name=%s, calorie_goal=NULL WHERE id=%s',
                     ('小红', users[1]))
    meal_for(context, users[0], base_calories=1200)
    meal_for(context, users[1], base_calories=1700)

    first = monthly(context, users[0])
    second = monthly(context, users[1])
    assert first['self'] == {'user_id':str(users[0]), 'display_name':'小明',
                             'character':'boy', 'calorie_goal':2200}
    assert first['partner'] == {'user_id':str(users[1]), 'display_name':'小红',
                                'character':'boy', 'calorie_goal':2000}
    assert first['days'][7]['self_calories'] == 1200
    assert first['days'][7]['partner_calories'] == 1700
    assert second['self'] == first['partner']
    assert second['partner'] == first['self']
    assert second['days'][7]['self_calories'] == 1700
    assert second['days'][7]['partner_calories'] == 1200


@pytest.mark.parametrize('mode', ['shared_half', 'shared_me_one_third',
                                  'shared_me_two_thirds'])
def test_monthly_shared_meals_use_stored_allocations(context, mode):
    _, users, _ = context
    meal = meal_for(context, users[0], share_mode=mode, base_calories=900)
    with get_connection() as conn:
        conn.execute('''UPDATE meals SET calories = CASE WHEN user_id = %s
            THEN %s ELSE %s END WHERE shared_meal_id = %s''',
                     (users[0], Decimal('101.11'), Decimal('202.22'),
                      meal['shared_meal_id']))

    result = monthly(context, users[0])
    day = result['days'][7]
    assert day['self_calories'] == pytest.approx(101.11)
    assert day['partner_calories'] == pytest.approx(202.22)
    assert isinstance(day['self_calories'], (int, float))
    assert isinstance(day['partner_calories'], (int, float))


def test_monthly_single_member_has_null_partner_values(context):
    user = context[1][2]
    result = monthly(context, user)
    assert result['partner'] is None
    assert all(day['partner_calories'] is None for day in result['days'])
    assert result['self']['calorie_goal'] == 2000
