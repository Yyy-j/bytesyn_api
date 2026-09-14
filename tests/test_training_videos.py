from conftest import headers
from test_training_custom_exercises import create_exercise


def put_video(client, user, exercise_id="chest_press", url="https://example.com/video"):
    return client.put(
        f"/training/exercises/{exercise_id}/video",
        headers=headers(user),
        json={"video_url": url},
    )


def test_video_create_list_update_and_delete(context):
    client, users, _ = context
    user = users[0]
    created = put_video(client, user)
    assert created.status_code == 200, created.text
    first = created.json()
    assert first["exercise_id"] == "chest_press"
    assert first["video_url"] == "https://example.com/video"
    assert "user_id" not in first

    listed = client.get("/training/exercises/videos", headers=headers(user))
    assert listed.status_code == 200
    assert listed.json() == {"videos": [first]}

    updated = put_video(client, user, url="http://example.org/updated")
    assert updated.status_code == 200
    assert updated.json()["id"] == first["id"]
    assert updated.json()["created_at"] == first["created_at"]
    assert updated.json()["video_url"] == "http://example.org/updated"

    deleted = client.delete(
        "/training/exercises/chest_press/video", headers=headers(user)
    )
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(
        "/training/exercises/videos", headers=headers(user)
    ).json() == {"videos": []}
    assert client.delete(
        "/training/exercises/chest_press/video", headers=headers(user)
    ).status_code == 404


def test_video_user_isolation_and_same_exercise_upsert(context):
    client, users, _ = context
    owner, other = users[0], users[2]
    owner_video = put_video(client, owner, url="https://example.com/owner").json()
    assert client.delete(
        "/training/exercises/chest_press/video", headers=headers(other)
    ).status_code == 404
    other_video = put_video(client, other, url="https://example.com/other").json()
    assert owner_video["id"] != other_video["id"]
    assert client.get(
        "/training/exercises/videos", headers=headers(owner)
    ).json()["videos"] == [owner_video]
    assert client.get(
        "/training/exercises/videos", headers=headers(other)
    ).json()["videos"] == [other_video]
    assert client.delete(
        "/training/exercises/chest_press/video", headers=headers(other)
    ).status_code == 204
    assert client.get(
        "/training/exercises/videos", headers=headers(owner)
    ).json()["videos"] == [owner_video]


def test_video_rejects_invalid_url_and_contract_fields(context):
    client, users, _ = context
    for value in (
        "ftp://example.com/video",
        "javascript:alert(1)",
        "example.com/video",
        "https:///missing-host",
        "https://example.com/has space",
        "",
    ):
        assert put_video(client, users[0], url=value).status_code == 422
    assert client.put(
        "/training/exercises/chest_press/video",
        headers=headers(users[0]),
        json={"video_url": "https://example.com/video", "title": "extra"},
    ).status_code == 422
    assert put_video(client, users[0], exercise_id="x" * 121).status_code == 422


def test_video_endpoints_require_jwt(context):
    client, _, _ = context
    assert client.get("/training/exercises/videos").status_code == 401
    assert client.put(
        "/training/exercises/chest_press/video",
        json={"video_url": "https://example.com/video"},
    ).status_code == 401
    assert client.delete(
        "/training/exercises/chest_press/video"
    ).status_code == 401


def test_custom_catalog_delete_removes_reference_video_only(context):
    client, users, _ = context
    user = users[0]
    exercise = create_exercise(client, user)
    assert put_video(client, user, exercise_id=exercise["id"]).status_code == 200
    assert client.delete(
        f"/training/exercises/custom/{exercise['id']}", headers=headers(user)
    ).status_code == 204
    assert client.get(
        "/training/exercises/videos", headers=headers(user)
    ).json() == {"videos": []}
