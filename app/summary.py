"""Daily pair nutrition from persisted Meal allocations."""
from datetime import date as Date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder

from app.auth import get_current_user_id
from app.db import connection
from app.meals import MACROS, public_meal
from app.pairs import _current_pair_state

router = APIRouter(prefix='/summary', tags=['summary'])
DEFAULT_GOALS = {'calorie_goal': Decimal(2000), 'protein_goal': Decimal(90),
                 'carbs_goal': Decimal(250), 'fat_goal': Decimal(60)}


def _totals(rows):
    # Sum stored NUMERIC values before JSON conversion; never recompute base macros.
    return {macro: sum((row[macro] for row in rows), Decimal(0)) for macro in MACROS}


def _goals(member):
    return {key: member[key] if member[key] is not None else default
            for key, default in DEFAULT_GOALS.items()}


def _summary_members(cursor, user_id, pair_id):
    if pair_id is None:
        cursor.execute('''SELECT u.id AS user_id,
            COALESCE(NULLIF(BTRIM(u.display_name), ''), '未命名成员') AS display_name,
            u.character,
            u.calorie_goal, u.protein_goal, u.carbs_goal, u.fat_goal
            FROM users u WHERE u.id = %s''', (user_id,))
    else:
        cursor.execute('''SELECT u.id AS user_id,
            COALESCE(NULLIF(BTRIM(u.display_name), ''), '未命名成员') AS display_name,
            u.character,
            u.calorie_goal, u.protein_goal, u.carbs_goal, u.fat_goal
            FROM users u JOIN pair_members pm ON pm.user_id = u.id
            WHERE pm.pair_id = %s ORDER BY u.id''', (pair_id,))
    return cursor.fetchall()


@router.get('/daily')
def daily_summary(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    date: Annotated[Date, Query()],
):
    with connection() as conn, conn.cursor() as cursor:
        # Membership, names and meals share one snapshot, including during shared edits.
        cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        pair_id, _ = _current_pair_state(cursor, user_id)
        # Keep profile goals in the same repeatable-read snapshot as meal totals.
        members = _summary_members(cursor, user_id, pair_id)
        cursor.execute('''SELECT * FROM meals WHERE meal_date = %s AND (
            (%s::uuid IS NOT NULL AND pair_id = %s)
            OR (pair_id IS NULL AND user_id = %s)
        ) ORDER BY meal_time, created_at, id''', (date, pair_id, pair_id, user_id))
        rows = cursor.fetchall()
        member_data = {member['user_id']: member for member in members}
        slices = {
            member['user_id']: dict(
                user_id=member['user_id'], display_name=member['display_name'],
                character=member['character'] or 'boy', **_totals([
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


@router.get('/monthly')
def monthly_summary(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    month: Annotated[str, Query(pattern=r'^\d{4}-(?:0[1-9]|1[0-2])$')],
):
    year, month_number = (int(value) for value in month.split('-'))
    month_start = Date(year, month_number, 1)
    next_month_start = (Date(year + 1, 1, 1) if month_number == 12
                        else Date(year, month_number + 1, 1))

    with connection() as conn, conn.cursor() as cursor:
        cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        pair_id, _ = _current_pair_state(cursor, user_id)
        members = _summary_members(cursor, user_id, pair_id)
        cursor.execute('''SELECT meal_date, user_id, SUM(calories) AS calories
            FROM meals
            WHERE meal_date >= %s AND meal_date < %s AND (
                (%s::uuid IS NOT NULL AND pair_id = %s)
                OR (pair_id IS NULL AND user_id = %s)
            )
            GROUP BY meal_date, user_id
            ORDER BY meal_date, user_id''',
                       (month_start, next_month_start, pair_id, pair_id, user_id))
        totals = {(row['meal_date'], row['user_id']): row['calories']
                  for row in cursor.fetchall()}

        member_data = {member['user_id']: member for member in members}
        partner = next((member for member in members if member['user_id'] != user_id), None)
        days = []
        current_date = month_start
        while current_date < next_month_start:
            days.append({
                'date': current_date,
                'self_calories': totals.get((current_date, user_id), Decimal(0)),
                'partner_calories': (
                    totals.get((current_date, partner['user_id']), Decimal(0))
                    if partner else None
                ),
            })
            current_date = Date.fromordinal(current_date.toordinal() + 1)

        result = {
            'month': month,
            'self': {
                'user_id': user_id,
                'display_name': member_data[user_id]['display_name'],
                'character': member_data[user_id]['character'] or 'boy',
                'calorie_goal': _goals(member_data[user_id])['calorie_goal'],
            },
            'partner': ({
                'user_id': partner['user_id'],
                'display_name': partner['display_name'],
                'character': partner['character'] or 'boy',
                'calorie_goal': _goals(partner)['calorie_goal'],
            } if partner else None),
            'days': days,
        }
        return jsonable_encoder(result, custom_encoder={Decimal: float})
