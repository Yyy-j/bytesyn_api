"""Daily pair nutrition from persisted Meal allocations."""
from datetime import date as Date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from app.auth import get_current_user_id
from app.db import connection
from app.meals import MACROS, public_meal
from app.pairs import _current_pair_id

router = APIRouter(prefix='/summary', tags=['summary'])
DEFAULT_GOALS = {'calorie_goal': 2000, 'protein_goal': 90, 'carbs_goal': 250, 'fat_goal': 60}


def _totals(rows):
    # Sum stored NUMERIC values before JSON conversion; never recompute base macros.
    return {macro: sum((row[macro] for row in rows), Decimal(0)) for macro in MACROS}


@router.get('/daily')
def daily_summary(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    date: Annotated[Date, Query()],
):
    with connection() as conn, conn.cursor() as cursor:
        # Membership, names and meals share one snapshot, including during shared edits.
        cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        pair_id = _current_pair_id(cursor, user_id)
        if pair_id is None:
            raise HTTPException(404, 'Current pair not found')
        # JSON projection tolerates minimal users schemas without display_name.
        cursor.execute('''SELECT u.id AS user_id,
            COALESCE(NULLIF(BTRIM(to_jsonb(u)->>'display_name'), ''), '未命名成员') AS display_name
            FROM users u JOIN pair_members pm ON pm.user_id = u.id
            WHERE pm.pair_id = %s ORDER BY u.id''', (pair_id,))
        members = cursor.fetchall()
        cursor.execute('SELECT * FROM meals WHERE pair_id = %s AND meal_date = %s '
                       'ORDER BY meal_time, created_at, id', (pair_id, date))
        rows = cursor.fetchall()
        slices = {
            member['user_id']: dict(member, **_totals([
                row for row in rows if row['user_id'] == member['user_id']
            ])) for member in members
        }
        partner = next((member for member in members if member['user_id'] != user_id), None)
        result = dict(
            date=date, **_totals(rows), meal_count=len(rows),
            meals=[public_meal(row) for row in rows],
            self_slice=slices[user_id],
            partner_slice=slices[partner['user_id']] if partner else None,
            self_goals=DEFAULT_GOALS.copy(),
            partner_goals=DEFAULT_GOALS.copy() if partner else None,
        )
        return jsonable_encoder(result, custom_encoder={Decimal: float})
