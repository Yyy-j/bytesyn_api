from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.db import get_connection
from conftest import headers
from test_training import create_current, find_item, item, template


def exercise_payload(**changes):
    value = {
        "name": " 保加利亚分腿蹲 ",
        "category": " 腿部 ",
        "item_type": "strength",
        "default_sets": 3,
        "default_reps": 10,
        "default_weight": 10,
    }
    value.update(changes)
    return value


def create_exercise(client, user, **changes):
    response = client.post(
        "/training/exercises/custom",
        headers=headers(user),
        json=exercise_payload(**changes),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_custom_exercise_create_list_and_user_isolation(context):
    client, users, _ = context
    owner, stranger = users[0], users[2]

    created = create_exercise(client, owner)
    UUID(created["id"])
    assert created["name"] == "保加利亚分腿蹲"
    assert created["category"] == "腿部"
    assert created["default_weight"] == 10
    assert created["default_duration_seconds"] is None
    assert "user_id" not in created
    assert created["created_at"] == created["updated_at"]

    owner_list = client.get(
        "/training/exercises/custom", headers=headers(owner)
    )
    assert owner_list.status_code == 200
    assert owner_list.json() == {"exercises": [created]}
    assert client.get(
        "/training/exercises/custom", headers=headers(stranger)
    ).json() == {"exercises": []}

    path = f"/training/exercises/custom/{created['id']}"
    assert client.patch(
        path, headers=headers(stranger), json={"name": "越权修改"}
    ).status_code == 404
    assert client.delete(path, headers=headers(stranger)).status_code == 404


def test_custom_exercise_defaults_server_fields_and_list_order(context):
    client, users, _ = context
    user = users[0]
    minimal = {
        "name": "Minimal",
        "default_sets": 1,
        "default_reps": 0,
    }
    first_response = client.post(
        "/training/exercises/custom", headers=headers(user), json=minimal
    )
    assert first_response.status_code == 201, first_response.text
    first = first_response.json()
    assert {
        key: first[key] for key in ("category", "item_type", "default_weight")
    } == {"category": "", "item_type": "strength", "default_weight": 0}
    second = create_exercise(client, user, name="Second")

    patched = client.patch(
        f"/training/exercises/custom/{first['id']}",
        headers=headers(user),
        json={"category": "Recently updated"},
    )
    assert patched.status_code == 200, patched.text
    listed = client.get(
        "/training/exercises/custom", headers=headers(user)
    ).json()["exercises"]
    assert [value["id"] for value in listed] == [first["id"], second["id"]]

    assert client.post(
        "/training/exercises/custom",
        headers=headers(user),
        json=minimal | {"id": str(uuid4())},
    ).status_code == 422


def test_custom_exercise_patch_contract(context):
    client, users, _ = context
    user = users[0]
    created = create_exercise(client, user)
    path = f"/training/exercises/custom/{created['id']}"

    single = client.patch(path, headers=headers(user), json={"name": " 单腿蹲 "})
    assert single.status_code == 200, single.text
    assert single.json()["name"] == "单腿蹲"
    assert single.json()["category"] == "腿部"

    multiple = client.patch(
        path,
        headers=headers(user),
        json={
            "category": "耐力",
            "item_type": "cardio",
            "default_sets": 1,
            "default_reps": 0,
            "default_weight": 0,
        },
    )
    assert multiple.status_code == 200, multiple.text
    assert {
        key: multiple.json()[key]
        for key in (
            "category", "item_type", "default_sets", "default_reps", "default_weight"
        )
    } == {
        "category": "耐力",
        "item_type": "cardio",
        "default_sets": 1,
        "default_reps": 0,
        "default_weight": 0,
    }
    assert multiple.json()["updated_at"] >= single.json()["updated_at"]

    assert client.patch(path, headers=headers(user), json={}).status_code == 422
    assert client.patch(path, headers=headers(user), json={"name": None}).status_code == 422
    assert client.patch(
        path, headers=headers(user), json={"item_type": "mobility"}
    ).status_code == 422
    assert client.post(
        "/training/exercises/custom",
        headers=headers(user),
        json=exercise_payload(item_type="mobility"),
    ).status_code == 422
    assert client.patch(
        "/training/exercises/custom/not-a-uuid",
        headers=headers(user),
        json={"name": "valid"},
    ).status_code == 422
    assert client.patch(
        f"/training/exercises/custom/{uuid4()}",
        headers=headers(user),
        json={"name": "valid"},
    ).status_code == 404


def test_custom_exercise_duration_create_patch_and_null(context):
    client, users, _ = context
    user = users[0]
    created = create_exercise(
        client,
        user,
        item_type="cardio",
        default_duration_seconds=1500,
    )
    assert created["default_duration_seconds"] == 1500
    path = f"/training/exercises/custom/{created['id']}"

    changed = client.patch(
        path, headers=headers(user), json={"default_duration_seconds": 1800}
    )
    assert changed.status_code == 200
    assert changed.json()["default_duration_seconds"] == 1800
    cleared = client.patch(
        path, headers=headers(user), json={"default_duration_seconds": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["default_duration_seconds"] is None

    for invalid in (0, 86401):
        assert client.post(
            "/training/exercises/custom",
            headers=headers(user),
            json=exercise_payload(default_duration_seconds=invalid),
        ).status_code == 422
        assert client.patch(
            path,
            headers=headers(user),
            json={"default_duration_seconds": invalid},
        ).status_code == 422


def test_migration_008_is_repeatable_and_constrained(context):
    migration = Path("app/migrations/008_training_custom_duration.sql").read_text()
    with get_connection() as conn:
        conn.execute(migration)
        conn.execute(migration)
        assert conn.execute(
            """SELECT count(*) AS count FROM schema_migrations
               WHERE version = '008_training_custom_duration'"""
        ).fetchone()["count"] == 1
        assert conn.execute(
            """SELECT count(*) AS count FROM pg_constraint
               WHERE conname =
                   'training_custom_exercises_default_duration_seconds_check'
                 AND conrelid = 'training_custom_exercises'::regclass"""
        ).fetchone()["count"] == 1


@pytest.mark.parametrize(
    ("field", "valid_values", "invalid_values"),
    [
        ("default_sets", (1, 50), (0, 51)),
        ("default_reps", (0, 999), (-1, 1000)),
        ("default_weight", (0, 10000), (-0.01, 10000.01)),
    ],
)
def test_custom_exercise_numeric_boundaries(
    context, field, valid_values, invalid_values
):
    client, users, _ = context
    user = users[0]
    exercise = create_exercise(client, user)
    patch_path = f"/training/exercises/custom/{exercise['id']}"
    for value in valid_values:
        assert client.post(
            "/training/exercises/custom",
            headers=headers(user),
            json=exercise_payload(**{field: value}),
        ).status_code == 201
        assert client.patch(
            patch_path,
            headers=headers(user),
            json={field: value},
        ).status_code == 200
    for value in invalid_values:
        assert client.post(
            "/training/exercises/custom",
            headers=headers(user),
            json=exercise_payload(**{field: value}),
        ).status_code == 422
        assert client.patch(
            patch_path,
            headers=headers(user),
            json={field: value},
        ).status_code == 422


def test_custom_exercise_rejects_non_finite_weight(context):
    client, users, _ = context
    path = "/training/exercises/custom"
    for value in ("NaN", "Infinity", "-Infinity"):
        assert client.post(
            path,
            headers=headers(users[0]),
            json=exercise_payload(default_weight=value),
        ).status_code == 422


def test_custom_exercise_delete_preserves_template_and_week(context):
    client, users, _ = context
    user = users[0]
    custom = create_exercise(client, user, default_duration_seconds=720)
    custom_item = item(
        "custom-template-item",
        name=custom["name"],
        exercise_id=custom["id"],
        category=custom["category"],
        item_type="duration",
        target_duration_seconds=custom["default_duration_seconds"],
    )
    week = create_current(client, user, template(custom_item))
    template_before = client.get(
        "/training/template", headers=headers(user)
    ).json()["template"]
    week_before = client.get(
        f"/training/weeks/{week['week_id']}", headers=headers(user)
    ).json()
    assert find_item(template_before, "custom-template-item")["exercise_id"] == custom["id"]
    assert find_item(week_before, "custom-template-item")["exercise_id"] == custom["id"]
    assert find_item(template_before, "custom-template-item")["target_duration_seconds"] == 720
    assert find_item(week_before, "custom-template-item")["target_duration_seconds"] == 720

    response = client.delete(
        f"/training/exercises/custom/{custom['id']}", headers=headers(user)
    )
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(
        "/training/exercises/custom", headers=headers(user)
    ).json() == {"exercises": []}
    assert client.get(
        "/training/template", headers=headers(user)
    ).json()["template"] == template_before
    assert client.get(
        f"/training/weeks/{week['week_id']}", headers=headers(user)
    ).json() == week_before


def test_custom_exercise_duplicate_names_are_allowed(context):
    client, users, _ = context
    first_user, second_user = users[0], users[2]

    first = create_exercise(client, first_user, name="同名动作")
    second = create_exercise(client, first_user, name="同名动作")
    third = create_exercise(client, second_user, name="同名动作")
    assert len({first["id"], second["id"], third["id"]}) == 3


def test_custom_exercise_endpoints_require_jwt(context):
    client, _, _ = context
    exercise_id = uuid4()
    assert client.get("/training/exercises/custom").status_code == 401
    assert client.post(
        "/training/exercises/custom", json=exercise_payload()
    ).status_code == 401
    assert client.patch(
        f"/training/exercises/custom/{exercise_id}", json={"name": "x"}
    ).status_code == 401
    assert client.delete(
        f"/training/exercises/custom/{exercise_id}"
    ).status_code == 401
