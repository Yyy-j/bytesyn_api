from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db import get_connection
from conftest import headers


def item(item_id, name=None, **changes):
    value = dict(
        item_id=item_id,
        exercise_id=f"exercise-{item_id}",
        exercise_name=name or item_id.title(),
        item_type="strength",
        category="strength",
        target_sets=3,
        target_reps=10,
        target_weight=20,
        order=0,
    )
    value.update(changes)
    return value


def template(*day_zero_items):
    return {
        "days": [
            {
                "day_index": day_index,
                "exercises": list(day_zero_items) if day_index == 0 else [],
            }
            for day_index in range(7)
        ]
    }


def create_current(client, user, payload=None):
    response = client.put(
        "/training/template", headers=headers(user), json=payload or template(item("squat"))
    )
    assert response.status_code == 200, response.text
    response = client.get("/training/weeks/current", headers=headers(user))
    assert response.status_code == 200, response.text
    return response.json()["week"]


def find_item(week, item_id):
    return next(
        value
        for day in week["days"]
        for value in day["exercises"]
        if value["item_id"] == item_id
    )


def assert_final_json_contract(value):
    if isinstance(value, dict):
        assert "week_key" not in value
        assert "items" not in value
        assert "sets" not in value
        for nested in value.values():
            assert_final_json_contract(nested)
    elif isinstance(value, list):
        for nested in value:
            assert_final_json_contract(nested)


def test_training_endpoints_require_jwt(context):
    client, _, _ = context
    week_id = "2026-W01"
    calls = [
        ("get", "/training/template", None),
        ("put", "/training/template", template(),),
        ("get", "/training/weeks", None),
        ("get", "/training/weeks/current", None),
        ("get", f"/training/weeks/{week_id}", None),
        ("post", "/training/weeks/current/sync", None),
        ("post", f"/training/weeks/{week_id}/items/x/sets", {"request_id": "x"}),
        ("patch", f"/training/weeks/{week_id}/items/x/sets/x", {"reps": 1}),
        ("delete", f"/training/weeks/{week_id}/items/x/sets/x", None),
    ]
    for method, path, body in calls:
        assert client.request(method, path, json=body).status_code == 401


def test_template_crud_version_and_validation(context):
    client, users, _ = context
    user = users[3]  # Deliberately unpaired: Training must not depend on Pair.

    missing = client.get("/training/template", headers=headers(user))
    assert missing.status_code == 200
    assert missing.json() == {"template": None}

    first = client.put(
        "/training/template", headers=headers(user), json=template(item("squat"))
    )
    assert first.status_code == 200
    assert first.json()["version"] == 1
    assert [day["day_index"] for day in first.json()["days"]] == list(range(7))

    second_payload = template(item("squat", target_sets=5))
    second = client.put(
        "/training/template", headers=headers(user), json=second_payload
    )
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["version"] == 2
    fetched = client.get("/training/template", headers=headers(user)).json()["template"]
    assert fetched["version"] == 2
    assert find_item(fetched, "squat")["item_type"] == "strength"
    assert_final_json_contract(fetched)

    bad_days = {"days": [{"day_index": index, "exercises": []} for index in range(6)]}
    assert client.put("/training/template", headers=headers(user), json=bad_days).status_code == 422
    duplicate = template(item("same"), item("same"))
    assert client.put("/training/template", headers=headers(user), json=duplicate).status_code == 422


def test_template_duration_contract_and_boundaries(context):
    client, users, _ = context
    user = users[0]
    payload = template(
        item("strength", item_type="strength"),
        item("duration", item_type="duration", target_duration_seconds=180),
        item("cardio", item_type="cardio", target_duration_seconds=1200),
    )
    response = client.put("/training/template", headers=headers(user), json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert find_item(result, "strength")["target_duration_seconds"] is None
    assert find_item(result, "duration")["target_duration_seconds"] == 180
    assert find_item(result, "cardio")["target_duration_seconds"] == 1200

    for invalid in (0, 86401):
        invalid_response = client.put(
            "/training/template",
            headers=headers(user),
            json=template(item("invalid", target_duration_seconds=invalid)),
        )
        assert invalid_response.status_code == 422


def test_old_template_without_duration_returns_null(context):
    client, users, _ = context
    user = users[0]
    response = client.put(
        "/training/template", headers=headers(user), json=template(item("legacy"))
    )
    assert response.status_code == 200
    with get_connection() as conn:
        row = conn.execute(
            "SELECT days FROM training_templates WHERE user_id = %s", (user,)
        ).fetchone()
        days = row["days"]
        del find_item({"days": days}, "legacy")["target_duration_seconds"]
        conn.execute(
            "UPDATE training_templates SET days = %s WHERE user_id = %s",
            (Jsonb(days), user),
        )
    fetched = client.get("/training/template", headers=headers(user))
    assert fetched.status_code == 200
    assert find_item(fetched.json()["template"], "legacy")["target_duration_seconds"] is None


def test_week_is_snapshot_and_current_is_idempotent(context):
    client, users, _ = context
    user = users[0]
    week = create_current(client, user, template(item("squat", target_sets=3)))
    again = client.get("/training/weeks/current", headers=headers(user))
    assert again.status_code == 200
    assert again.json()["created"] is False
    assert again.json()["week"]["id"] == week["id"]

    update = client.put(
        "/training/template",
        headers=headers(user),
        json=template(item("squat", target_sets=9), item("bench")),
    )
    assert update.json()["version"] == 2
    historical_snapshot = client.get(
        f"/training/weeks/{week['week_id']}", headers=headers(user)
    ).json()
    assert historical_snapshot["template_version"] == 1
    assert find_item(historical_snapshot, "squat")["target_sets"] == 3
    assert all(
        value["item_id"] != "bench"
        for day in historical_snapshot["days"] for value in day["exercises"]
    )


def test_week_snapshot_and_history_preserve_template_duration(context):
    client, users, _ = context
    user = users[0]
    week = create_current(
        client,
        user,
        template(item("run", item_type="cardio", target_duration_seconds=900)),
    )
    assert find_item(week, "run")["target_duration_seconds"] == 900

    changed = client.put(
        "/training/template",
        headers=headers(user),
        json=template(item("run", item_type="cardio", target_duration_seconds=1800)),
    )
    assert changed.status_code == 200
    fetched = client.get(
        f"/training/weeks/{week['week_id']}", headers=headers(user)
    ).json()
    history = client.get("/training/weeks", headers=headers(user)).json()["weeks"][0]
    assert find_item(fetched, "run")["target_duration_seconds"] == 900
    assert find_item(history, "run")["target_duration_seconds"] == 900


def test_no_template_current_week_is_empty_and_sync_is_safe(context):
    client, users, _ = context
    user = users[3]
    response = client.get("/training/weeks/current", headers=headers(user))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["created"] is True
    week = result["week"]
    assert week["template_version"] is None
    assert len(week["days"]) == 7
    assert [day["day_index"] for day in week["days"]] == list(range(7))
    assert all(day["exercises"] == [] for day in week["days"])
    assert_final_json_contract(week)

    sync = client.post("/training/weeks/current/sync", headers=headers(user))
    assert sync.status_code == 200, sync.text
    assert sync.json()["created"] is False
    assert sync.json()["synced"] is False
    assert sync.json()["week"]["id"] == week["id"]


def test_week_history_and_get(context):
    client, users, _ = context
    user = users[0]
    current = create_current(client, user)
    past_id = uuid4()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM training_weeks WHERE id = %s AND user_id = %s",
            (current["id"], user),
        ).fetchone()
        past_start = row["week_start"] - timedelta(days=7)
        conn.execute(
            """INSERT INTO training_weeks
               (id, user_id, week_id, week_start, week_end, template_version, days)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (past_id, user, "2000-W01", past_start, past_start + timedelta(days=6),
             row["template_version"], Jsonb(row["days"])),
        )

    response = client.get("/training/weeks?limit=1&offset=0", headers=headers(user))
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert len(response.json()["weeks"]) == 1
    assert response.json()["weeks"][0]["id"] == current["id"]
    past = client.get("/training/weeks/2000-W01", headers=headers(user))
    assert past.status_code == 200
    assert past.json()["id"] == str(past_id)
    assert past.json()["week_id"] == "2000-W01"
    assert_final_json_contract(past.json())

    assert client.get("/training/weeks/not-a-week", headers=headers(user)).status_code == 422
    assert client.get("/training/weeks/2026-W54", headers=headers(user)).status_code == 422
    assert client.get("/training/weeks/1999-W52", headers=headers(user)).status_code == 404


def test_sync_merges_by_item_id_and_retains_recorded_deletions(context):
    client, users, _ = context
    user = users[0]
    original = template(item("keep", target_sets=3), item("drop-recorded"), item("drop-empty"))
    week = create_current(client, user, original)
    for target, request_id in (("keep", "keep-1"), ("drop-recorded", "drop-1")):
        response = client.post(
            f"/training/weeks/{week['week_id']}/items/{target}/sets",
            headers=headers(user),
            json={"request_id": request_id, "reps": 8},
        )
        assert response.status_code == 201, response.text

    replacement = template(
        item("keep", name="Keep renamed", target_sets=5),
        item("new", target_sets=2),
    )
    assert client.put(
        "/training/template", headers=headers(user), json=replacement
    ).json()["version"] == 2
    response = client.post("/training/weeks/current/sync", headers=headers(user))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["created"] is False and result["synced"] is True
    synced = result["week"]
    assert synced["template_version"] == 2
    kept = find_item(synced, "keep")
    assert kept["exercise_name"] == "Keep renamed"
    assert kept["completed_sets"] == 1
    assert kept["set_details"][0]["request_id"] == "keep-1"
    assert find_item(synced, "new")["completed_sets"] == 0
    removed = find_item(synced, "drop-recorded")
    assert removed["removed_from_template"] is True
    assert removed["completed_sets"] == 1
    assert not any(
        value["item_id"] == "drop-empty"
        for day in synced["days"] for value in day["exercises"]
    )
    assert_final_json_contract(synced)

    deleted = client.delete(
        f"/training/weeks/{week['week_id']}/items/drop-recorded/sets/drop-1",
        headers=headers(user),
    )
    assert deleted.status_code == 200, deleted.text
    after_delete = client.get(
        f"/training/weeks/{week['week_id']}", headers=headers(user)
    ).json()
    retained = find_item(after_delete, "drop-recorded")
    assert retained["removed_from_template"] is True
    assert retained["set_details"] == []
    assert retained["completed_sets"] == 0


def test_set_checkin_idempotency_server_count_and_update(context):
    client, users, _ = context
    user = users[0]
    week = create_current(client, user, template(item("squat", target_sets=2)))
    url = f"/training/weeks/{week['week_id']}/items/squat/sets"
    body = {"request_id": "set-request-1", "weight": 42.5, "reps": 9, "rpe": 8}
    first = client.post(url, headers=headers(user), json=body)
    assert first.status_code == 201
    assert first.json()["duplicate"] is False
    assert first.json()["completed_sets"] == 1

    duplicate = client.post(url, headers=headers(user), json=body)
    assert duplicate.status_code == 201
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["completed_sets"] == 1

    injected = client.post(
        url,
        headers=headers(user),
        json={"request_id": "set-request-2", "completed_sets": 99},
    )
    assert injected.status_code == 422

    patch = client.patch(
        f"{url}/set-request-1",
        headers=headers(user),
        json={"weight": 45, "remark": "controlled"},
    )
    assert patch.status_code == 200
    assert patch.json()["completed_sets"] == 1
    assert patch.json()["set"]["weight"] == 45
    assert patch.json()["set"]["remark"] == "controlled"
    assert patch.json()["set"]["request_id"] == "set-request-1"

    fetched = client.get(
        f"/training/weeks/{week['week_id']}", headers=headers(user)
    ).json()
    squat = find_item(fetched, "squat")
    assert squat["completed_sets"] == len(squat["set_details"]) == 1
    assert squat["item_type"] == "strength"
    assert_final_json_contract(fetched)


def test_set_duration_create_patch_clear_and_legacy_read(context):
    client, users, _ = context
    user = users[0]
    week = create_current(
        client,
        user,
        template(item("bike", item_type="duration", target_duration_seconds=600)),
    )
    url = f"/training/weeks/{week['week_id']}/items/bike/sets"
    created = client.post(
        url,
        headers=headers(user),
        json={"request_id": "duration-set", "duration_seconds": 480},
    )
    assert created.status_code == 201, created.text
    assert created.json()["set"]["duration_seconds"] == 480

    changed = client.patch(
        f"{url}/duration-set",
        headers=headers(user),
        json={"duration_seconds": 510},
    )
    assert changed.status_code == 200
    assert changed.json()["set"]["duration_seconds"] == 510
    cleared = client.patch(
        f"{url}/duration-set",
        headers=headers(user),
        json={"duration_seconds": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["set"]["duration_seconds"] is None
    assert client.patch(f"{url}/duration-set", headers=headers(user), json={}).status_code == 422

    for invalid in (0, 86401):
        assert client.post(
            url,
            headers=headers(user),
            json={"request_id": f"invalid-{invalid}", "duration_seconds": invalid},
        ).status_code == 422
        assert client.patch(
            f"{url}/duration-set",
            headers=headers(user),
            json={"duration_seconds": invalid},
        ).status_code == 422

    with get_connection() as conn:
        row = conn.execute(
            "SELECT days FROM training_weeks WHERE id = %s", (week["id"],)
        ).fetchone()
        days = row["days"]
        legacy = find_item({"days": days}, "bike")["set_details"][0]
        del legacy["duration_seconds"]
        conn.execute(
            "UPDATE training_weeks SET days = %s WHERE id = %s",
            (Jsonb(days), week["id"]),
        )
    fetched = client.get(
        f"/training/weeks/{week['week_id']}", headers=headers(user)
    ).json()
    assert find_item(fetched, "bike")["set_details"][0]["duration_seconds"] is None


def test_delete_middle_set_renumbers_preserves_fields_and_allows_next_set(context):
    client, users, _ = context
    user = users[0]
    week = create_current(client, user, template(item("squat", target_sets=3)))
    sets_url = f"/training/weeks/{week['week_id']}/items/squat/sets"
    bodies = [
        {
            "request_id": "A",
            "weight": 40,
            "reps": 10,
            "rpe": 7,
            "duration_seconds": 60,
            "remark": "first",
        },
        {
            "request_id": "B",
            "weight": 45,
            "reps": 9,
            "rpe": 8,
            "duration_seconds": 70,
            "remark": "middle",
        },
        {
            "request_id": "C",
            "weight": 50,
            "reps": 8,
            "rpe": 9,
            "duration_seconds": 80,
            "remark": "last",
        },
    ]
    created = []
    for body in bodies:
        response = client.post(sets_url, headers=headers(user), json=body)
        assert response.status_code == 201, response.text
        created.append(response.json()["set"])

    response = client.delete(f"{sets_url}/B", headers=headers(user))
    assert response.status_code == 200, response.text
    assert response.json() == {
        "deleted": True,
        "request_id": "B",
        "completed_sets": 2,
        "target_sets": 3,
    }

    fetched = client.get(
        f"/training/weeks/{week['week_id']}", headers=headers(user)
    ).json()
    remaining = find_item(fetched, "squat")["set_details"]
    assert [detail["request_id"] for detail in remaining] == ["A", "C"]
    assert [detail["set_index"] for detail in remaining] == [1, 2]
    preserved_fields = (
        "request_id",
        "weight",
        "reps",
        "rpe",
        "duration_seconds",
        "remark",
        "completed_at",
    )
    for actual, original in zip(remaining, (created[0], created[2])):
        assert {field: actual[field] for field in preserved_fields} == {
            field: original[field] for field in preserved_fields
        }

    added = client.post(
        sets_url,
        headers=headers(user),
        json={"request_id": "D", "weight": 55, "reps": 7},
    )
    assert added.status_code == 201, added.text
    assert added.json()["set"]["set_index"] == 3
    assert added.json()["completed_sets"] == 3


def test_delete_last_set_keeps_exercise(context):
    client, users, _ = context
    user = users[0]
    week = create_current(client, user, template(item("squat", target_sets=3)))
    sets_url = f"/training/weeks/{week['week_id']}/items/squat/sets"
    assert client.post(
        sets_url, headers=headers(user), json={"request_id": "A", "reps": 10}
    ).status_code == 201

    response = client.delete(f"{sets_url}/A", headers=headers(user))
    assert response.status_code == 200, response.text
    assert response.json()["completed_sets"] == 0
    assert response.json()["target_sets"] == 3

    fetched = client.get(
        f"/training/weeks/{week['week_id']}", headers=headers(user)
    ).json()
    exercise = find_item(fetched, "squat")
    assert exercise["set_details"] == []
    assert exercise["completed_sets"] == 0
    assert exercise["target_sets"] == 3


def test_delete_set_not_found_errors(context):
    client, users, _ = context
    user = users[0]
    week = create_current(client, user)
    base = f"/training/weeks/{week['week_id']}/items"

    missing_set = client.delete(
        f"{base}/squat/sets/unknown-request-id", headers=headers(user)
    )
    assert missing_set.status_code == 404
    assert missing_set.json()["detail"] == "Training set not found"

    missing_item = client.delete(
        f"{base}/unknown-item/sets/unknown-request-id", headers=headers(user)
    )
    assert missing_item.status_code == 404
    assert missing_item.json()["detail"] == "Training item not found"

    missing_week = client.delete(
        "/training/weeks/1999-W52/items/squat/sets/unknown-request-id",
        headers=headers(user),
    )
    assert missing_week.status_code == 404
    assert missing_week.json()["detail"] == "Training week not found"


def test_user_isolation_for_template_week_and_sets(context):
    client, users, _ = context
    owner, stranger = users[0], users[2]
    week = create_current(client, owner)
    assert client.get("/training/template", headers=headers(stranger)).json() == {
        "template": None
    }
    assert client.get(
        f"/training/weeks/{week['week_id']}", headers=headers(stranger)
    ).status_code == 404
    assert client.post(
        f"/training/weeks/{week['week_id']}/items/squat/sets",
        headers=headers(stranger),
        json={"request_id": "isolation-attempt"},
    ).status_code == 404
    assert client.patch(
        f"/training/weeks/{week['week_id']}/items/squat/sets/anything",
        headers=headers(stranger),
        json={"reps": 1},
    ).status_code == 404
    sets_url = f"/training/weeks/{week['week_id']}/items/squat/sets"
    assert client.post(
        sets_url, headers=headers(owner), json={"request_id": "owner-set"}
    ).status_code == 201
    assert client.delete(
        f"{sets_url}/owner-set", headers=headers(stranger)
    ).status_code == 404
    fetched = client.get(
        f"/training/weeks/{week['week_id']}", headers=headers(owner)
    ).json()
    assert [
        detail["request_id"] for detail in find_item(fetched, "squat")["set_details"]
    ] == ["owner-set"]


def test_request_id_cannot_move_between_items(context):
    client, users, _ = context
    user = users[0]
    week = create_current(client, user, template(item("first"), item("second")))
    base = f"/training/weeks/{week['week_id']}/items"
    assert client.post(
        f"{base}/first/sets", headers=headers(user), json={"request_id": "global-request"}
    ).status_code == 201
    conflict = client.post(
        f"{base}/second/sets", headers=headers(user), json={"request_id": "global-request"}
    )
    assert conflict.status_code == 409


def test_concurrent_request_id_is_counted_once(context):
    client, users, _ = context
    user = users[0]
    week = create_current(client, user, template(item("row", target_sets=10)))
    url = f"/training/weeks/{week['week_id']}/items/row/sets"

    def submit(_):
        return client.post(
            url, headers=headers(user), json={"request_id": "same-concurrent-request"}
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(submit, range(8)))
    assert all(response.status_code == 201 for response in responses)
    assert sum(not response.json()["duplicate"] for response in responses) == 1
    assert {response.json()["completed_sets"] for response in responses} == {1}
    fetched = client.get(
        f"/training/weeks/{week['week_id']}", headers=headers(user)
    ).json()
    assert len(find_item(fetched, "row")["set_details"]) == 1
