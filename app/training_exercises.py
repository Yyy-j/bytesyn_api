"""Private custom exercise catalog and teaching-video endpoints."""
from datetime import datetime, timezone
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.encoders import jsonable_encoder
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.auth import get_current_user_id
from app.db import connection

router = APIRouter(prefix="/training/exercises", tags=["training"])
User = Annotated[UUID, Depends(get_current_user_id)]
ExerciseName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Category = Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]
ItemType = Literal["strength", "duration", "cardio"]
ExerciseId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]


class CustomExerciseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    name: ExerciseName
    category: Category = ""
    item_type: ItemType = "strength"
    default_sets: int = Field(ge=1, le=50)
    default_reps: int = Field(ge=0, le=999)
    default_weight: float = Field(default=0, ge=0, le=10000)
    default_duration_seconds: int | None = Field(default=None, ge=1, le=86400)


class CustomExercisePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    name: ExerciseName | None = None
    category: Category | None = None
    item_type: ItemType | None = None
    default_sets: int | None = Field(default=None, ge=1, le=50)
    default_reps: int | None = Field(default=None, ge=0, le=999)
    default_weight: float | None = Field(default=None, ge=0, le=10000)
    default_duration_seconds: int | None = Field(default=None, ge=1, le=86400)

    @model_validator(mode="after")
    def require_non_null_change(self):
        if not self.model_fields_set:
            raise ValueError("at least one custom exercise field is required")
        if any(
            field != "default_duration_seconds" and getattr(self, field) is None
            for field in self.model_fields_set
        ):
            raise ValueError("custom exercise fields cannot be null")
        return self


class CustomExercisePublic(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    id: UUID
    name: str
    category: str
    item_type: ItemType
    default_sets: int
    default_reps: int
    default_weight: float
    default_duration_seconds: int | None
    created_at: datetime
    updated_at: datetime


class CustomExerciseList(BaseModel):
    exercises: list[CustomExercisePublic]


class ExerciseVideoPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video_url: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2048)
    ]

    @field_validator("video_url")
    @classmethod
    def validate_http_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.netloc
            or any(character.isspace() for character in value)
        ):
            raise ValueError("video_url must be an http or https URL")
        return value


class ExerciseVideoPublic(BaseModel):
    id: UUID
    exercise_id: str
    video_url: str
    created_at: datetime
    updated_at: datetime


class ExerciseVideoList(BaseModel):
    videos: list[ExerciseVideoPublic]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public_exercise(row):
    return jsonable_encoder(
        {
            key: row[key]
            for key in (
                "id",
                "name",
                "category",
                "item_type",
                "default_sets",
                "default_reps",
                "default_weight",
                "default_duration_seconds",
                "created_at",
                "updated_at",
            )
        }
    )


def _public_video(row):
    return jsonable_encoder(
        {
            key: row[key]
            for key in (
                "id",
                "exercise_id",
                "video_url",
                "created_at",
                "updated_at",
            )
        }
    )


@router.get("/custom", response_model=CustomExerciseList)
def list_custom_exercises(user_id: User):
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """SELECT * FROM training_custom_exercises
               WHERE user_id = %s
               ORDER BY updated_at DESC, created_at DESC""",
            (user_id,),
        )
        return {"exercises": [_public_exercise(row) for row in cursor.fetchall()]}


@router.post(
    "/custom",
    status_code=status.HTTP_201_CREATED,
    response_model=CustomExercisePublic,
)
def create_custom_exercise(body: CustomExerciseCreate, user_id: User):
    now = _now()
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """INSERT INTO training_custom_exercises
               (user_id, name, category, item_type, default_sets, default_reps,
                default_weight, default_duration_seconds, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING *""",
            (
                user_id,
                body.name,
                body.category,
                body.item_type,
                body.default_sets,
                body.default_reps,
                body.default_weight,
                body.default_duration_seconds,
                now,
                now,
            ),
        )
        return _public_exercise(cursor.fetchone())


@router.patch("/custom/{exercise_id}", response_model=CustomExercisePublic)
def patch_custom_exercise(
    exercise_id: UUID, body: CustomExercisePatch, user_id: User
):
    changes = body.model_dump(exclude_unset=True)
    assignments = [f"{field} = %s" for field in changes]
    now = _now()
    assignments.append("updated_at = %s")
    values = [*changes.values(), now, exercise_id, user_id]

    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            f"""UPDATE training_custom_exercises
                SET {', '.join(assignments)}
                WHERE id = %s AND user_id = %s
                RETURNING *""",
            values,
        )
        row = cursor.fetchone()
        if row is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Custom exercise not found"
            )
        return _public_exercise(row)


@router.delete("/custom/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_custom_exercise(exercise_id: UUID, user_id: User):
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """DELETE FROM training_exercise_videos
               WHERE user_id = %s AND exercise_id = %s""",
            (user_id, str(exercise_id)),
        )
        cursor.execute(
            """DELETE FROM training_custom_exercises
               WHERE id = %s AND user_id = %s
               RETURNING id""",
            (exercise_id, user_id),
        )
        if cursor.fetchone() is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Custom exercise not found"
            )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/videos", response_model=ExerciseVideoList)
def list_exercise_videos(user_id: User):
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """SELECT * FROM training_exercise_videos
               WHERE user_id = %s ORDER BY updated_at DESC, exercise_id""",
            (user_id,),
        )
        return {"videos": [_public_video(row) for row in cursor.fetchall()]}


@router.put("/{exercise_id}/video", response_model=ExerciseVideoPublic)
def put_exercise_video(exercise_id: ExerciseId, body: ExerciseVideoPut, user_id: User):
    now = _now()
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """INSERT INTO training_exercise_videos
               (user_id, exercise_id, video_url, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (user_id, exercise_id) DO UPDATE
               SET video_url = EXCLUDED.video_url, updated_at = EXCLUDED.updated_at
               RETURNING *""",
            (user_id, exercise_id, body.video_url, now, now),
        )
        return _public_video(cursor.fetchone())


@router.delete("/{exercise_id}/video", status_code=status.HTTP_204_NO_CONTENT)
def delete_exercise_video(exercise_id: ExerciseId, user_id: User):
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """DELETE FROM training_exercise_videos
               WHERE user_id = %s AND exercise_id = %s RETURNING id""",
            (user_id, exercise_id),
        )
        if cursor.fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Exercise video not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
