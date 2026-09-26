from datetime import date
from decimal import Decimal

import pytest

from app import body as body_module
from app.db import get_connection
from conftest import headers


TODAY = date(2026, 9, 27)


def add_identity(user):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO auth_identities
               (user_id, provider, provider_subject, email)
               VALUES (%s, 'google', %s, 'body@example.com')""",
            (user, str(user)),
        )


def set_height(client, user, height=170):
    add_identity(user)
    response = client.patch(
        '/users/me', headers=headers(user), json={'height_cm':height})
    assert response.status_code == 200, response.text


def recommendation_payload(**changes):
    return {
        'birth_year':1998,
        'sex_for_energy_estimate':'male',
        'height_cm':170,
        'current_weight_kg':63,
        'target_weight_kg':63,
        'target_date':'2026-12-31',
        'activity_level':'moderate',
    } | changes


def onboarding_payload(**changes):
    return recommendation_payload(
        target_weight_kg=58,
        target_date='2027-01-01',
    ) | {
        'goals':{'calories':1850, 'protein':110, 'carbs':220, 'fat':55},
    } | changes


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(body_module, '_today', lambda: TODAY)
    monkeypatch.setattr('app.users._today', lambda: TODAY)


def test_new_user_starts_onboarding_incomplete(context):
    client, users, _ = context
    add_identity(users[3])
    result = client.get('/users/me', headers=headers(users[3])).json()
    assert result['onboarding_completed_at'] is None
    assert all(result[key] is None for key in (
        'birth_year', 'sex_for_energy_estimate', 'height_cm',
        'target_weight_kg', 'target_date', 'activity_level'))


def test_body_endpoints_require_authentication(context):
    client = context[0]
    assert client.get('/users/me/body').status_code == 401
    assert client.get('/users/me/weight-measurements').status_code == 401
    assert client.post('/users/me/weight-measurements', json={
        'measured_on':'2026-09-27', 'weight_kg':63}).status_code == 401
    assert client.post('/users/me/calorie-recommendation',
                       json=recommendation_payload()).status_code == 401
    assert client.post('/users/me/onboarding', json=onboarding_payload()).status_code == 401


def test_body_without_measurement_uses_null_not_zero(context):
    client, users, _ = context
    result = client.get('/users/me/body', headers=headers(users[3]))
    assert result.status_code == 200
    assert result.json() == {
        'height_cm':None, 'current_weight':None, 'target_weight_kg':None,
        'target_date':None, 'weight_difference_kg':None}


def test_weight_create_list_order_bmi_and_latest_body(context):
    client, users, _ = context
    user = users[3]
    set_height(client, user)
    first = client.post('/users/me/weight-measurements', headers=headers(user), json={
        'measured_on':'2026-09-20', 'weight_kg':63.2})
    second = client.post('/users/me/weight-measurements', headers=headers(user), json={
        'measured_on':'2026-09-27', 'weight_kg':62.5})
    assert first.status_code == second.status_code == 201
    assert first.json()['height_cm_snapshot'] == 170
    assert first.json()['bmi'] == 21.9
    listed = client.get('/users/me/weight-measurements', headers=headers(user),
                        params={'limit':1})
    assert listed.status_code == 200
    assert [row['id'] for row in listed.json()['measurements']] == [second.json()['id']]

    assert client.patch('/users/me', headers=headers(user), json={
        'target_weight_kg':60, 'target_date':'2026-12-31'}).status_code == 200
    body = client.get('/users/me/body', headers=headers(user)).json()
    assert body == {
        'height_cm':170,
        'current_weight':{
            'measurement_id':second.json()['id'], 'measured_on':'2026-09-27',
            'weight_kg':62.5, 'bmi':21.6},
        'target_weight_kg':60, 'target_date':'2026-12-31',
        'weight_difference_kg':-2.5,
    }


def test_weight_requires_height_and_enforces_one_per_day(context):
    client, users, _ = context
    user = users[3]
    assert client.post('/users/me/weight-measurements', headers=headers(user), json={
        'measured_on':'2026-09-27', 'weight_kg':63}).status_code == 409
    set_height(client, user)
    assert client.post('/users/me/weight-measurements', headers=headers(user), json={
        'measured_on':'2026-09-27', 'weight_kg':63}).status_code == 201
    duplicate = client.post('/users/me/weight-measurements', headers=headers(user), json={
        'measured_on':'2026-09-27', 'weight_kg':64})
    assert duplicate.status_code == 409
    assert client.post('/users/me/weight-measurements', headers=headers(user), json={
        'measured_on':'2026-09-28', 'weight_kg':64}).status_code == 422


def test_weight_patch_date_conflict_delete_and_user_isolation(context):
    client, users, _ = context
    owner, other = users[3], users[0]
    set_height(client, owner)
    first = client.post('/users/me/weight-measurements', headers=headers(owner), json={
        'measured_on':'2026-09-26', 'weight_kg':64}).json()
    second = client.post('/users/me/weight-measurements', headers=headers(owner), json={
        'measured_on':'2026-09-27', 'weight_kg':63}).json()
    changed = client.patch(
        f"/users/me/weight-measurements/{first['id']}", headers=headers(owner),
        json={'weight_kg':63.5, 'measured_on':'2026-09-25'})
    assert changed.status_code == 200
    assert changed.json()['weight_kg'] == 63.5
    conflict = client.patch(
        f"/users/me/weight-measurements/{first['id']}", headers=headers(owner),
        json={'measured_on':'2026-09-27'})
    assert conflict.status_code == 409
    for method in ('patch', 'delete'):
        response = getattr(client, method)(
            f"/users/me/weight-measurements/{second['id']}",
            headers=headers(other), **({'json':{'weight_kg':60}} if method == 'patch' else {}))
        assert response.status_code == 404
    assert client.delete(
        f"/users/me/weight-measurements/{second['id']}",
        headers=headers(owner)).status_code == 204


def test_height_snapshot_keeps_historical_bmi(context):
    client, users, _ = context
    user = users[3]
    set_height(client, user, 170)
    created = client.post('/users/me/weight-measurements', headers=headers(user), json={
        'measured_on':'2026-09-27', 'weight_kg':63.2}).json()
    assert client.patch('/users/me', headers=headers(user), json={
        'height_cm':180}).status_code == 200
    result = client.get('/users/me/weight-measurements', headers=headers(user)).json()
    assert result['measurements'][0]['height_cm_snapshot'] == 170
    assert result['measurements'][0]['bmi'] == created['bmi'] == 21.9


@pytest.mark.parametrize(('sex', 'activity', 'expected_bmr', 'expected_tdee'), [
    ('male', 'sedentary', 1558, 1869),
    ('male', 'moderate', 1558, 2414),
    ('male', 'high', 1558, 2687),
    ('female', 'moderate', 1392, 2157),
])
def test_recommendation_formula_and_activity(
    context, sex, activity, expected_bmr, expected_tdee,
):
    client, users, _ = context
    response = client.post('/users/me/calorie-recommendation',
        headers=headers(users[3]), json=recommendation_payload(
            sex_for_energy_estimate=sex, activity_level=activity))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['method'] == 'mifflin_st_jeor_v1'
    assert result['direction'] == 'maintain'
    assert result['bmr'] == expected_bmr
    assert result['maintenance_calories'] == expected_tdee
    assert result['recommended_calories'] == expected_tdee


def test_recommendation_safe_loss_and_macros_are_deterministic(context):
    client, users, _ = context
    request = recommendation_payload(target_weight_kg=58, target_date='2027-01-01')
    first = client.post('/users/me/calorie-recommendation',
                        headers=headers(users[3]), json=request)
    second = client.post('/users/me/calorie-recommendation',
                         headers=headers(users[3]), json=request)
    assert first.status_code == 200
    assert first.json() == second.json()
    result = first.json()
    assert result['direction'] == 'lose'
    assert result['aggressive_timeline'] is False
    assert result['recommended_target_date'] == '2027-01-01'
    assert result['recommended_calories'] == 2013
    goals = result['recommended_goals']
    assert goals == {'calories':2013, 'protein':113, 'carbs':264, 'fat':56}
    assert abs(goals['protein']*4 + goals['carbs']*4 + goals['fat']*9
               - goals['calories']) <= 3
    with get_connection() as conn:
        stored = conn.execute("""SELECT birth_year, height_cm, calorie_goal
            FROM users WHERE id=%s""", (users[3],)).fetchone()
    assert all(value is None for value in stored.values())


def test_recommendation_aggressive_loss_and_gain_return_safe_date(context):
    client, users, _ = context
    loss = client.post('/users/me/calorie-recommendation', headers=headers(users[3]),
        json=recommendation_payload(target_weight_kg=58, target_date='2026-10-27')).json()
    assert loss['direction'] == 'lose'
    assert loss['aggressive_timeline'] is True
    assert loss['recommended_calories'] == 1811
    assert loss['recommended_target_date'] == '2026-11-30'
    assert loss['recommended_calories'] >= 1500

    gain = client.post('/users/me/calorie-recommendation', headers=headers(users[3]),
        json=recommendation_payload(target_weight_kg=68, target_date='2026-10-27')).json()
    assert gain['direction'] == 'gain'
    assert gain['aggressive_timeline'] is True
    assert gain['recommended_calories'] == 2761
    assert gain['recommended_target_date'] == '2027-01-17'


@pytest.mark.parametrize('changes', [
    {'birth_year':2010}, {'birth_year':2008}, {'birth_year':2027}, {'height_cm':0},
    {'current_weight_kg':0}, {'target_weight_kg':401},
    {'sex_for_energy_estimate':'other'}, {'activity_level':'sometimes'},
    {'target_date':'2026-09-26'}, {'current_weight_kg':'NaN'},
])
def test_recommendation_rejects_invalid_or_underage_input(context, changes):
    response = context[0].post('/users/me/calorie-recommendation',
        headers=headers(context[1][3]), json=recommendation_payload(**changes))
    assert response.status_code == 422


def test_onboarding_is_atomic_retry_safe_and_saves_all_fields(context):
    client, users, _ = context
    user = users[3]
    add_identity(user)
    first = client.post('/users/me/onboarding', headers=headers(user),
                        json=onboarding_payload())
    assert first.status_code == 200, first.text
    result = first.json()
    assert result['onboarding_completed_at'] is not None
    assert result['current_weight']['measured_on'] == '2026-09-27'
    assert result['current_weight']['weight_kg'] == 63
    assert result['current_weight']['height_cm_snapshot'] == 170
    assert result['current_weight']['bmi'] == 21.8
    assert result['goals'] == {'calories':1850, 'protein':110, 'carbs':220, 'fat':55}

    retry = client.post('/users/me/onboarding', headers=headers(user),
                        json=onboarding_payload(current_weight_kg=62.8))
    assert retry.status_code == 200
    assert retry.json()['onboarding_completed_at'] == result['onboarding_completed_at']
    assert retry.json()['current_weight']['id'] == result['current_weight']['id']
    assert retry.json()['current_weight']['weight_kg'] == 62.8
    current = client.get('/users/me', headers=headers(user)).json()
    assert {key:current[key] for key in (
        'birth_year', 'sex_for_energy_estimate', 'height_cm',
        'target_weight_kg', 'target_date', 'activity_level')} == {
        'birth_year':1998, 'sex_for_energy_estimate':'male', 'height_cm':170,
        'target_weight_kg':58, 'target_date':'2027-01-01',
        'activity_level':'moderate'}
    assert current['goals'] == result['goals']
    with get_connection() as conn:
        count = conn.execute(
            'SELECT count(*) AS n FROM weight_measurements WHERE user_id=%s',
            (user,)).fetchone()['n']
    assert count == 1


def test_onboarding_failure_rolls_back_profile_goals_and_weight(context):
    client, users, _ = context
    user = users[3]
    add_identity(user)
    with get_connection() as conn:
        conn.execute("""CREATE FUNCTION fail_onboarding_weight() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'forced rollback'; END; $$""")
        conn.execute("""CREATE TRIGGER fail_onboarding_weight
            BEFORE INSERT ON weight_measurements
            FOR EACH ROW EXECUTE FUNCTION fail_onboarding_weight()""")
    try:
        response = client.post('/users/me/onboarding', headers=headers(user),
                               json=onboarding_payload())
        assert response.status_code == 503
        with get_connection() as conn:
            stored = conn.execute("""SELECT onboarding_completed_at, birth_year,
                height_cm, calorie_goal FROM users WHERE id=%s""", (user,)).fetchone()
            assert all(value is None for value in stored.values())
            assert conn.execute("""SELECT count(*) AS n FROM weight_measurements
                WHERE user_id=%s""", (user,)).fetchone()['n'] == 0
    finally:
        with get_connection() as conn:
            conn.execute('DROP TRIGGER fail_onboarding_weight ON weight_measurements')
            conn.execute('DROP FUNCTION fail_onboarding_weight()')


def test_weight_is_private_and_account_delete_cascades(context):
    client, users, _ = context
    owner, partner = users[0], users[1]
    set_height(client, owner)
    measurement = client.post('/users/me/weight-measurements', headers=headers(owner),
        json={'measured_on':'2026-09-27', 'weight_kg':63}).json()
    pair = client.get('/pairs/me', headers=headers(partner)).json()
    daily = client.get('/summary/daily', headers=headers(partner),
                       params={'date':'2026-09-27'}).json()
    private_keys = {'birth_year', 'sex_for_energy_estimate', 'height_cm',
                    'weight_kg', 'bmi', 'target_weight_kg', 'target_date'}
    def all_keys(value):
        if isinstance(value, dict):
            return set(value) | set().union(*(all_keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(all_keys(item) for item in value)) if value else set()
        return set()
    assert private_keys.isdisjoint(all_keys(pair))
    assert private_keys.isdisjoint(all_keys(daily))
    assert client.delete('/users/me', headers=headers(owner)).status_code == 204
    with get_connection() as conn:
        assert conn.execute('SELECT 1 FROM weight_measurements WHERE id=%s',
                            (measurement['id'],)).fetchone() is None
