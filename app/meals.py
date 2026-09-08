"""Pair-scoped meals. Every operation uses one PostgreSQL transaction."""
from datetime import date as Date, datetime
from decimal import Decimal, ROUND_HALF_UP, localcontext
from fractions import Fraction
from typing import Annotated, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from psycopg import sql

from app.auth import get_current_user_id
from app.db import connection

router = APIRouter(prefix="/meals", tags=["meals"])
User = Annotated[UUID, Depends(get_current_user_id)]
ShareMode = Literal['solo', 'partner_only', 'shared_half', 'shared_me_one_third', 'shared_me_two_thirds']
Macro = Annotated[Decimal, Field(ge=0, le=99999999, max_digits=30, decimal_places=18)]
Portion = Annotated[Decimal, Field(gt=0, le=100, max_digits=24, decimal_places=18)]
Name = Annotated[str, Field(min_length=1, max_length=255)]
MealTime = Annotated[str, Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')]
MACROS = ('calories', 'protein', 'carbs', 'fat')
RATIOS = {'solo': Fraction(1), 'partner_only': Fraction(0), 'shared_half': Fraction(1, 2),
          'shared_me_one_third': Fraction(1, 3), 'shared_me_two_thirds': Fraction(2, 3)}
PUBLIC = ('id', 'pair_id', 'user_id', 'shared_meal_id', 'name', 'source',
          *(f'base_{m}' for m in MACROS), *MACROS, 'portion_ratio', 'share_ratio',
          'share_mode', 'meal_date', 'meal_time', 'created_at', 'updated_at')


class CreateMeal(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    name: Name
    source: Literal['manual', 'ai', 'text']
    base_calories: Macro
    base_protein: Macro
    base_carbs: Macro
    base_fat: Macro
    portion_ratio: Portion
    share_mode: ShareMode
    meal_time: MealTime

    @field_validator('name')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Name must not be blank')
        return value


class PatchMeal(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    name: Name | None = None
    base_calories: Macro | None = None
    base_protein: Macro | None = None
    base_carbs: Macro | None = None
    base_fat: Macro | None = None
    portion_ratio: Portion | None = None
    share_mode: ShareMode | None = None
    meal_time: MealTime | None = None
    expected_updated_at: datetime | None = None

    @model_validator(mode='after')
    def validate_patch(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError('Omit unchanged fields; null is not accepted')
        if self.name is not None and not self.name.strip():
            raise ValueError('Name must not be blank')
        if self.expected_updated_at is not None and self.expected_updated_at.tzinfo is None:
            raise ValueError('expected_updated_at must include a timezone')
        return self


def conflict(detail):
    raise HTTPException(409, detail)


def pair_context(cursor, user_id):
    # Serialize mutations within a pair, before reading/locking any meal rows.
    # Pair membership writes already lock pairs in app.pairs.join_pair.
    cursor.execute('SELECT p.id FROM pairs p JOIN pair_members pm ON pm.pair_id = p.id '
                   'WHERE pm.user_id = %s FOR UPDATE OF p', (user_id,))
    row = cursor.fetchone()
    if row is None:
        raise HTTPException(404, 'Current pair not found')
    cursor.execute('SELECT user_id FROM pair_members WHERE pair_id = %s ORDER BY user_id',
                   (row['id'],))
    return row['id'], [r['user_id'] for r in cursor.fetchall()]


def find_meal(cursor, pair_id, meal_id):
    cursor.execute('SELECT * FROM meals WHERE pair_id = %s AND id = %s FOR UPDATE',
                   (pair_id, meal_id))
    row = cursor.fetchone()
    if row is None:
        raise HTTPException(404, 'Meal not found')
    return row


def public_meal(row):
    # Never derive a historical baseline from rounded stored nutrition.
    if any(row.get(key) is None for key in PUBLIC if key != 'shared_meal_id'):
        conflict('Legacy meal requires explicit data reconciliation')
    if row['source'] not in ('manual', 'ai', 'text') or row['share_mode'] not in RATIOS:
        conflict('Legacy meal requires explicit data reconciliation')
    result = {key: row[key] for key in PUBLIC}
    result['meal_time'] = row['meal_time'].strftime('%H:%M')
    # Pydantic serializes Decimal as strings; Flutter requires JSON numbers.
    return jsonable_encoder(result, custom_encoder={Decimal: float})


def nutrition(data, ratio):
    result = {}
    # Exact rational arithmetic, including thirds. Round only the final macros.
    for macro in MACROS:
        exact = Fraction(data[f'base_{macro}']) * Fraction(data['portion_ratio']) * ratio
        with localcontext() as ctx:
            ctx.prec = 100
            value = (Decimal(exact.numerator) / Decimal(exact.denominator)).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP)
        if value > Decimal('99999999.99'):
            raise HTTPException(422, 'Calculated nutrition exceeds storage limit')
        result[macro] = value
    with localcontext() as ctx:
        ctx.prec = 60
        result['share_ratio'] = Decimal(ratio.numerator) / Decimal(ratio.denominator)
    return result


def allocations(data, owner, members):
    mode = data['share_mode']
    others = [m for m in members if m != owner]
    if owner not in members:
        conflict('Meal owner is no longer in the current pair')
    if mode != 'solo' and len(others) != 1:
        conflict('A partner is required for this share mode')
    if mode == 'solo':
        return [(owner, Fraction(1))]
    if mode == 'partner_only':
        return [(others[0], Fraction(1))]
    return [(owner, RATIOS[mode]), (others[0], 1 - RATIOS[mode])]


def insert_meal(cursor, values):
    keys = list(values)
    cursor.execute(sql.SQL('INSERT INTO meals ({}) VALUES ({}) RETURNING *').format(
        sql.SQL(', ').join(map(sql.Identifier, keys)),
        sql.SQL(', ').join(sql.Placeholder() for _ in keys)), list(values.values()))
    return cursor.fetchone()


def update_row(cursor, meal_id, values):
    cursor.execute(sql.SQL('UPDATE meals SET {} WHERE id = %s RETURNING *').format(
        sql.SQL(', ').join(sql.SQL('{} = %s').format(sql.Identifier(k)) for k in values)),
        [*values.values(), meal_id])
    return cursor.fetchone()


@router.post('', status_code=201)
def create_meal(body: CreateMeal, user_id: User):
    with connection() as conn, conn.cursor() as cursor:
        pair_id, members = pair_context(cursor, user_id)
        data = body.model_dump()
        slices = allocations(data, user_id, members)
        group_id = uuid4() if len(slices) == 2 else None
        data.update(pair_id=pair_id, share_owner_id=user_id, shared_meal_id=group_id,
                    meal_date=datetime.now(ZoneInfo('Asia/Tokyo')).date())
        rows = [insert_meal(cursor, dict(data, user_id=member, **nutrition(data, ratio)))
                for member, ratio in slices]
        return public_meal(rows[0])


@router.get('')
def list_meals(user_id: User, date: Annotated[Date, Query()]):
    with connection() as conn, conn.cursor() as cursor:
        pair_id, _ = pair_context(cursor, user_id)
        cursor.execute('SELECT * FROM meals WHERE pair_id = %s AND meal_date = %s '
                       'ORDER BY meal_time, created_at, id', (pair_id, date))
        return {'meals': [public_meal(row) for row in cursor.fetchall()]}


# Register before /{meal_id}: "recent" is not a UUID.
@router.get('/recent')
def recent_meals(user_id: User, limit: Annotated[int, Query(ge=1, le=10)] = 3):
    with connection() as conn, conn.cursor() as cursor:
        pair_id, _ = pair_context(cursor, user_id)
        # One reusable record per shared group; latest meals first.
        cursor.execute('''SELECT * FROM (
            SELECT DISTINCT ON (COALESCE(shared_meal_id, id)) * FROM meals
            WHERE pair_id = %s
            ORDER BY COALESCE(shared_meal_id, id), (user_id = %s) DESC, id
        ) recent ORDER BY meal_date DESC, meal_time DESC, created_at DESC, id DESC LIMIT %s''',
                       (pair_id, user_id, limit))
        return {'meals': [public_meal(row) for row in cursor.fetchall()]}


@router.get('/{meal_id}')
def get_meal(meal_id: UUID, user_id: User):
    with connection() as conn, conn.cursor() as cursor:
        pair_id, _ = pair_context(cursor, user_id)
        return public_meal(find_meal(cursor, pair_id, meal_id))


def group_rows(cursor, pair_id, row):
    if row['shared_meal_id'] is None:
        return [row]
    cursor.execute('SELECT * FROM meals WHERE shared_meal_id = %s ORDER BY id FOR UPDATE',
                   (row['shared_meal_id'],))
    rows = cursor.fetchall()
    if len(rows) != 2 or any(r['pair_id'] != pair_id for r in rows):
        conflict('Shared meal group requires data reconciliation')
    return rows


@router.patch('/{meal_id}')
def patch_meal(meal_id: UUID, body: PatchMeal, user_id: User):
    with connection() as conn, conn.cursor() as cursor:
        pair_id, members = pair_context(cursor, user_id)
        row = find_meal(cursor, pair_id, meal_id)
        rows = group_rows(cursor, pair_id, row)
        if body.expected_updated_at is not None and any(
                r['updated_at'] != body.expected_updated_at for r in rows):
            conflict('Meal was updated; refresh and retry')
        public_meal(row)
        changes = body.model_dump(exclude_unset=True, exclude={'expected_updated_at'})
        if not changes:
            return public_meal(row)
        owner = row['share_owner_id']
        if owner is None:
            if row['share_mode'] != 'solo' or row['shared_meal_id'] is not None:
                conflict('Legacy shared meal requires explicit data reconciliation')
            owner = row['user_id']
        data = {key: row[key] for key in CreateMeal.model_fields}
        data.update(changes)
        # Validate both allocations before making writes; failures still roll back.
        slices = [(member, nutrition(data, ratio)) for member, ratio in allocations(data, owner, members)]
        group_id = (row['shared_meal_id'] or uuid4()) if len(slices) == 2 else None
        cursor.execute('SELECT now() AS stamp')
        data.update(pair_id=pair_id, share_owner_id=owner, shared_meal_id=group_id,
                    meal_date=row['meal_date'], updated_at=cursor.fetchone()['stamp'])
        existing = {r['user_id']: r for r in rows}
        if len(existing) != len(rows):
            conflict('Shared meal group requires data reconciliation')
        result = []
        # Keep the addressed id across transitions to/from a single allocation.
        for member, macros in slices:
            old = existing.pop(member, None)
            if old is None and len(slices) == 1:
                old = existing.pop(row['user_id'], None)
            values = dict(data, user_id=member, **macros)
            result.append(update_row(cursor, old['id'], values) if old else insert_meal(cursor, values))
        for old in existing.values():
            cursor.execute('DELETE FROM meals WHERE id = %s AND pair_id = %s', (old['id'], pair_id))
        chosen = next((r for r in result if r['id'] == meal_id), result[0])
        return public_meal(chosen)


@router.delete('/{meal_id}', status_code=204)
def delete_meal(meal_id: UUID, user_id: User):
    with connection() as conn, conn.cursor() as cursor:
        pair_id, _ = pair_context(cursor, user_id)
        row = find_meal(cursor, pair_id, meal_id)
        rows = group_rows(cursor, pair_id, row)
        for old in rows:
            cursor.execute('DELETE FROM meals WHERE id = %s AND pair_id = %s', (old['id'], pair_id))
        return Response(status_code=204)
