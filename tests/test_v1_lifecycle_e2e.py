from app.db import get_connection
from conftest import headers, payload


DATE = "2026-10-07"


def _training_template(name):
    return {
        "days": [
            {
                "day_index": day_index,
                "exercises": [
                    {
                        "item_id": f"{name}-item",
                        "exercise_id": name,
                        "exercise_name": name,
                        "item_type": "strength",
                        "category": "strength",
                        "target_sets": 3,
                        "target_reps": 8,
                        "target_weight": 20,
                        "order": 0,
                    }
                ]
                if day_index == 0
                else [],
            }
            for day_index in range(7)
        ]
    }


def _create_meal(client, user, **changes):
    response = client.post("/meals", headers=headers(user), json=payload(**changes))
    assert response.status_code == 201, response.text
    meal = response.json()
    with get_connection() as conn:
        if meal["shared_meal_id"]:
            conn.execute(
                "UPDATE meals SET meal_date = %s WHERE shared_meal_id = %s",
                (DATE, meal["shared_meal_id"]),
            )
        else:
            conn.execute(
                "UPDATE meals SET meal_date = %s WHERE id = %s", (DATE, meal["id"])
            )
    return meal


def _daily(client, user):
    response = client.get(
        "/summary/daily", headers=headers(user), params={"date": DATE}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_end_repair_summary_isolation_and_training_independence(context):
    client, users, _ = context
    user_a, user_b, _, user_c = users

    ab_meal = _create_meal(
        client,
        user_a,
        name="AB shared history",
        share_mode="shared_half",
        base_calories=800,
    )
    with get_connection() as conn:
        ab_rows = conn.execute(
            "SELECT id, user_id FROM meals WHERE shared_meal_id = %s",
            (ab_meal["shared_meal_id"],),
        ).fetchall()
    ab_by_user = {str(row["user_id"]): str(row["id"]) for row in ab_rows}

    training_before = {}
    for user, name in ((user_a, "a-squat"), (user_b, "b-row")):
        saved = client.put(
            "/training/template",
            headers=headers(user),
            json=_training_template(name),
        )
        assert saved.status_code == 200, saved.text
        training_before[str(user)] = client.get(
            "/training/template", headers=headers(user)
        ).json()

    assert client.post("/pairs/end", headers=headers(user_a)).status_code == 204
    pending = client.post("/pairs", headers=headers(user_a))
    assert pending.status_code == 201, pending.text
    ac_pair = pending.json()
    try:
        joined = client.post(
            "/pairs/join",
            headers=headers(user_c),
            json={"invite_code": ac_pair["invite_code"]},
        )
        assert joined.status_code == 200, joined.text

        ac_meal = _create_meal(
            client,
            user_a,
            name="AC current shared",
            share_mode="shared_half",
            base_calories=600,
        )
        b_solo = _create_meal(
            client, user_b, name="B after end", base_calories=200
        )

        summary_a = _daily(client, user_a)
        summary_b = _daily(client, user_b)
        summary_c = _daily(client, user_c)
        ids_a = {meal["id"] for meal in summary_a["meals"]}
        ids_b = {meal["id"] for meal in summary_b["meals"]}
        ids_c = {meal["id"] for meal in summary_c["meals"]}

        assert summary_a["partner_slice"]["user_id"] == str(user_c)
        assert summary_c["partner_slice"]["user_id"] == str(user_a)
        assert summary_b["partner_slice"] is None
        assert ab_by_user[str(user_b)] not in ids_a
        assert not ids_c.intersection(ab_by_user.values())
        assert ac_meal["id"] not in ids_b
        assert b_solo["id"] not in ids_a
        assert ab_by_user[str(user_a)] in ids_a
        assert ab_by_user[str(user_b)] in ids_b

        for user in (user_a, user_b):
            after = client.get("/training/template", headers=headers(user))
            assert after.status_code == 200, after.text
            assert after.json() == training_before[str(user)]
    finally:
        with get_connection() as conn:
            conn.execute("DELETE FROM pairs WHERE id = %s", (ac_pair["pair_id"],))
