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
DEFAULT_GOALS = {'calorie_goal': Decimal(2000), 'protein_goal': Decimal(90),
                 'carbs_goal': Decimal(250), 'fat_goal': Decimal(60)}


def _totals(rows):
    # Sum stored NUMERIC values before JSON conversion; never recompute base macros.
    return {macro: sum((row[macro] for row in rows), Decimal(0)) for macro in MACROS}


def _goals(member):
    return {key: member[key] if member[key] is not None else default
            for key, default in DEFAULT_GOALS.items()}


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
        # Keep profile goals in the same repeatable-read snapshot as meal totals.
        cursor.execute('''SELECT u.id AS user_id,
            COALESCE(NULLIF(BTRIM(u.display_name), ''), '未命名成员') AS display_name,
            u.calorie_goal, u.protein_goal, u.carbs_goal, u.fat_goal
            FROM users u JOIN pair_members pm ON pm.user_id = u.id
            WHERE pm.pair_id = %s ORDER BY u.id''', (pair_id,))
        members = cursor.fetchall()
        cursor.execute('SELECT * FROM meals WHERE pair_id = %s AND meal_date = %s '
                       'ORDER BY meal_time, created_at, id', (pair_id, date))
        rows = cursor.fetchall()
        member_data = {member['user_id']: member for member in members}
        slices = {
            member['user_id']: dict(
                user_id=member['user_id'], display_name=member['display_name'], **_totals([
                row for row in rows if row['user_id'] == member['user_id']
            ])) for member in members
        }
        partner = next((member for member in members if member['user_id'] != user_id), None)
        result = dict(
            date=date, **_totals(rows), meal_count=len(rows),
            meals=[public_meal(row) for row in rows],
            self_slice=slices[user_id],
            partner_slice=slices[partner['user_id']] if partner else None,
            self_goals=_goals(member_data[user_id]),
            partner_goals=_goals(partner) if partner else None,
        )
        return jsonable_encoder(result, custom_encoder={Decimal: float})
