import pytest

from app.db import get_connection
from conftest import headers


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
        'display_name':None, 'avatar_url':None,
        'goals':{'calories':2000, 'protein':90, 'carbs':250, 'fat':60},
    }


def test_patch_me_profile_and_partial_goals(context):
    client, users, _ = context
    add_identity(users[0])
    response = client.patch('/users/me', headers=headers(users[0]), json={
        'display_name':'  Harper  ', 'avatar_url':'  https://example.com/a.png  ',
        'goals':{'calories':2200, 'protein':120}})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['display_name'] == 'Harper'
    assert result['avatar_url'] == 'https://example.com/a.png'
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


def test_pair_members_include_profile_information(context):
    client, users, _ = context
    for index, user in enumerate(users[:2]):
        add_identity(user, email=f'person-{index}@example.com')
        response = client.patch(
            '/users/me',
            headers=headers(user),
            json={
                'display_name': f'Member {index + 1}',
                'avatar_url': f'https://example.com/{index + 1}.png',
            },
        )
        assert response.status_code == 200

    pair = client.get('/pairs/me', headers=headers(users[0]))
    assert pair.status_code == 200
    members = {value['user_id']: value for value in pair.json()['members']}
    assert members[str(users[0])]['display_name'] == 'Member 1'
    assert members[str(users[0])]['avatar_url'] == 'https://example.com/1.png'
    assert members[str(users[1])]['display_name'] == 'Member 2'
    assert members[str(users[1])]['avatar_url'] == 'https://example.com/2.png'
