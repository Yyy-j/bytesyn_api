from typing import Annotated, Literal
from uuid import UUID
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth import get_current_user_id
from app.db import connection, get_user_identity
from app.pairs import _active_pair, _end_pair


router = APIRouter(prefix="/users", tags=["users"])


Goal = Annotated[Decimal, Field(ge=0, max_digits=30, decimal_places=18)]
DEFAULT_GOALS = {'calories': Decimal(2000), 'protein': Decimal(90),
                 'carbs': Decimal(250), 'fat': Decimal(60)}
GOAL_COLUMNS = {'calories': 'calorie_goal', 'protein': 'protein_goal',
                'carbs': 'carbs_goal', 'fat': 'fat_goal'}


class NutritionGoals(BaseModel):
    calories: float
    protein: float
    carbs: float
    fat: float


class CurrentUserResponse(BaseModel):
    id: UUID
    email: str | None
    provider: str
    display_name: str | None
    character: Literal['boy', 'girl']
    goals: NutritionGoals


class PatchNutritionGoals(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    calories: Goal | None = None
    protein: Goal | None = None
    carbs: Goal | None = None
    fat: Goal | None = None


class PatchCurrentUser(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    display_name: str | None = Field(default=None, max_length=100)
    character: Literal['boy', 'girl'] | None = None
    goals: PatchNutritionGoals | None = None

    @field_validator('display_name')
    @classmethod
    def trim_optional_text(cls, value):
        if value is None:
            return None
        clean = value.strip()
        return clean or None

    @field_validator('character')
    @classmethod
    def reject_null_character(cls, value):
        if value is None:
            raise ValueError('character must be boy or girl')
        return value


def user_response(user: dict[str, object]) -> CurrentUserResponse:
    goals = {
        name: user[column] if user[column] is not None else DEFAULT_GOALS[name]
        for name, column in GOAL_COLUMNS.items()
    }
    response = dict(user)
    response['character'] = user.get('character') or 'boy'
    return CurrentUserResponse(**response, goals=goals)


@router.get("/me", response_model=CurrentUserResponse)
def get_me(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> CurrentUserResponse:
    user = get_user_identity(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_response(user)


@router.patch('/me', response_model=CurrentUserResponse)
def patch_me(
    body: PatchCurrentUser,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> CurrentUserResponse:
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute('''SELECT u.id, ai.provider, ai.email, u.display_name, u.character,
            u.calorie_goal, u.protein_goal, u.carbs_goal, u.fat_goal
            FROM users u JOIN auth_identities ai ON ai.user_id = u.id
            WHERE u.id = %s ORDER BY ai.created_at LIMIT 1 FOR UPDATE OF u''', (user_id,))
        user = cursor.fetchone()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Invalid authentication credentials',
                headers={'WWW-Authenticate': 'Bearer'},
            )
        changes = body.model_dump(exclude_unset=True, exclude={'goals'})
        if body.goals is not None:
            for name, value in body.goals.model_dump(exclude_unset=True).items():
                changes[GOAL_COLUMNS[name]] = value
        if changes:
            assignments = ', '.join(f'{column} = %s' for column in changes)
            cursor.execute(f'UPDATE users SET {assignments} WHERE id = %s',
                           [*changes.values(), user_id])
            user.update(changes)
        return user_response(user)


@router.delete('/me', status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> Response:
    with connection() as conn, conn.cursor() as cursor:
        # Pair-first lock ordering matches join/end/Meal mutations.
        pair = _active_pair(cursor, user_id, lock=True)
        cursor.execute('SELECT id FROM users WHERE id = %s FOR UPDATE', (user_id,))
        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Invalid authentication credentials',
                headers={'WWW-Authenticate': 'Bearer'},
            )

        if pair is not None:
            _end_pair(cursor, pair['id'])

        # Explicit ownership audit: do not rely on an unreviewed cascade chain.
        for table in (
            'auth_sessions',
            'auth_identities',
            'meal_favorites',
            'training_exercise_videos',
            'training_custom_exercises',
            'training_weeks',
            'training_templates',
        ):
            cursor.execute(f'DELETE FROM {table} WHERE user_id = %s', (user_id,))

        # Preserve a partner's allocation while removing deleted-user provenance.
        cursor.execute(
            '''UPDATE meals SET share_owner_id = NULL
            WHERE share_owner_id = %s AND user_id <> %s''',
            (user_id, user_id),
        )
        cursor.execute('DELETE FROM meals WHERE user_id = %s', (user_id,))
        cursor.execute('DELETE FROM pair_members WHERE user_id = %s', (user_id,))
        cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
        return Response(status_code=status.HTTP_204_NO_CONTENT)
