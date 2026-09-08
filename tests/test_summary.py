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


@pytest.mark.parametrize('auth', [{}, {'Authorization':'Bearer invalid'}, {'Authorization':'Basic invalid'}])
def test_summary_unauthenticated(context, auth):
    response = context[0].get('/summary/daily', params={'date':DATE}, headers=auth)
    assert response.status_code == 401


def test_summary_unpaired(context):
    response = context[0].get('/summary/daily', params={'date':DATE}, headers=headers(context[1][3]))
    assert response.status_code == 404
    assert response.json() == {'detail':'Current pair not found'}


def test_summary_one_member_empty(context):
    user = context[1][2]
    result = summary(context, user)
    assert result == dict(date=DATE, **ZERO, meal_count=0, meals=[],
                         self_slice=dict(user_id=str(user), display_name='未命名成员', **ZERO),
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
                                       calories=200,protein=20,carbs=40,fat=8)
    assert result['partner_slice'] == dict(user_id=str(users[1]), display_name='未命名成员',
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
    # Match NAS's optional column while the rest of the suite uses minimal migrations.
    with get_connection() as conn:
        conn.execute("ALTER TABLE users ADD COLUMN display_name VARCHAR DEFAULT ''")
        conn.execute('UPDATE users SET display_name = %s WHERE id = %s', ('小明',users[0]))
        conn.execute('UPDATE users SET display_name = %s WHERE id = %s', ('小红',users[1]))
    try:
        result = summary(context, users[0])
        assert result['self_slice']['display_name'] == '小明'
        assert result['partner_slice']['display_name'] == '小红'
        assert summary(context, users[2])['self_slice']['display_name'] == '未命名成员'
    finally:
        with get_connection() as conn:
            conn.execute('ALTER TABLE users DROP COLUMN display_name')
