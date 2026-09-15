from typing import Annotated
from uuid import UUID
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth import get_current_user_id
from app.db import connection, get_user_identity


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
    goals: PatchNutritionGoals | None = None

    @field_validator('display_name')
    @classmethod
    def trim_optional_text(cls, value):
        if value is None:
            return None
        clean = value.strip()
        return clean or None


def user_response(user: dict[str, object]) -> CurrentUserResponse:
    goals = {
        name: user[column] if user[column] is not None else DEFAULT_GOALS[name]
        for name, column in GOAL_COLUMNS.items()
    }
    return CurrentUserResponse(**user, goals=goals)


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
        cursor.execute('''SELECT u.id, ai.provider, ai.email, u.display_name,
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
