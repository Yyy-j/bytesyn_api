from copy import deepcopy
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
            {"day_index": day_index, "items": list(day_zero_items) if day_index == 0 else []}
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
        for value in day["items"]
        if value["item_id"] == item_id
    )


def test_training_endpoints_require_jwt(context):
    client, _, _ = context
    random_id = uuid4()
    calls = [
        ("get", "/training/template", None),
        ("put", "/training/template", template(),),
        ("get", "/training/weeks", None),
        ("get", "/training/weeks/current", None),
        ("get", f"/training/weeks/{random_id}", None),
        ("post", "/training/weeks/current/sync", None),
        ("post", f"/training/weeks/{random_id}/items/x/sets", {"request_id": "x"}),
        ("patch", f"/training/weeks/{random_id}/items/x/sets/x", {"reps": 1}),
    ]
    for method, path, body in calls:
        assert client.request(method, path, json=body).status_code == 401


def test_template_crud_version_and_validation(context):
    client, users, _ = context
    user = users[3]  # Deliberately unpaired: Training must not depend on Pair.

    missing = client.get("/training/template", headers=headers(user))
    assert missing.status_code == 404

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
    assert client.get("/training/template", headers=headers(user)).json()["version"] == 2

    bad_days = {"days": [{"day_index": index, "items": []} for index in range(6)]}
    assert client.put("/training/template", headers=headers(user), json=bad_days).status_code == 422
    duplicate = template(item("same"), item("same"))
    assert client.put("/training/template", headers=headers(user), json=duplicate).status_code == 422


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
        f"/training/weeks/{week['id']}", headers=headers(user)
    ).json()
    assert historical_snapshot["template_version"] == 1
    assert find_item(historical_snapshot, "squat")["target_sets"] == 3
    assert all(
        value["item_id"] != "bench"
        for day in historical_snapshot["days"] for value in day["items"]
    )


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
               (id, user_id, week_key, week_start, week_end, template_version, days)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (past_id, user, "2000-W01", past_start, past_start + timedelta(days=6),
             row["template_version"], Jsonb(row["days"])),
        )

    response = client.get("/training/weeks?limit=1&offset=0", headers=headers(user))
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert len(response.json()["weeks"]) == 1
    assert response.json()["weeks"][0]["id"] == current["id"]
    assert client.get(f"/training/weeks/{past_id}", headers=headers(user)).status_code == 200


def test_sync_merges_by_item_id_and_retains_recorded_deletions(context):
    client, users, _ = context
    user = users[0]
    original = template(item("keep", target_sets=3), item("drop-recorded"), item("drop-empty"))
    week = create_current(client, user, original)
    for target, request_id in (("keep", "keep-1"), ("drop-recorded", "drop-1")):
        response = client.post(
            f"/training/weeks/{week['id']}/items/{target}/sets",
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
    assert kept["sets"][0]["request_id"] == "keep-1"
    assert find_item(synced, "new")["completed_sets"] == 0
    removed = find_item(synced, "drop-recorded")
    assert removed["removed_from_template"] is True
    assert removed["completed_sets"] == 1
    assert not any(
        value["item_id"] == "drop-empty"
        for day in synced["days"] for value in day["items"]
    )


def test_set_checkin_idempotency_server_count_and_update(context):
    client, users, _ = context
    user = users[0]
    week = create_current(client, user, template(item("squat", target_sets=2)))
    url = f"/training/weeks/{week['id']}/items/squat/sets"
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

    fetched = client.get(f"/training/weeks/{week['id']}", headers=headers(user)).json()
    squat = find_item(fetched, "squat")
    assert squat["completed_sets"] == len(squat["sets"]) == 1


def test_user_isolation_for_template_week_and_sets(context):
    client, users, _ = context
    owner, stranger = users[0], users[2]
    week = create_current(client, owner)
    assert client.get("/training/template", headers=headers(stranger)).status_code == 404
    assert client.get(
        f"/training/weeks/{week['id']}", headers=headers(stranger)
    ).status_code == 404
    assert client.post(
        f"/training/weeks/{week['id']}/items/squat/sets",
        headers=headers(stranger),
        json={"request_id": "isolation-attempt"},
    ).status_code == 404
    assert client.patch(
        f"/training/weeks/{week['id']}/items/squat/sets/anything",
        headers=headers(stranger),
        json={"reps": 1},
    ).status_code == 404


def test_request_id_cannot_move_between_items(context):
    client, users, _ = context
    user = users[0]
    week = create_current(client, user, template(item("first"), item("second")))
    base = f"/training/weeks/{week['id']}/items"
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
    url = f"/training/weeks/{week['id']}/items/row/sets"

    def submit(_):
        return client.post(
            url, headers=headers(user), json={"request_id": "same-concurrent-request"}
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(submit, range(8)))
    assert all(response.status_code == 201 for response in responses)
    assert sum(not response.json()["duplicate"] for response in responses) == 1
    assert {response.json()["completed_sets"] for response in responses} == {1}
    fetched = client.get(f"/training/weeks/{week['id']}", headers=headers(user)).json()
    assert len(find_item(fetched, "row")["sets"]) == 1
