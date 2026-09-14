"""User-scoped training templates, weekly snapshots, and set check-ins."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from psycopg.types.json import Jsonb

from app.auth import get_current_user_id
from app.db import connection

router = APIRouter(prefix="/training", tags=["training"])
User = Annotated[UUID, Depends(get_current_user_id)]
Identifier = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
WeekId = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9]{4}-W(?:0[1-9]|[1-4][0-9]|5[0-3])$"),
]


class TemplateItem(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    item_id: Identifier
    exercise_id: Identifier | None = None
    exercise_name: Name
    item_type: Literal["strength", "duration", "cardio"] = "strength"
    category: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] = ""
    target_sets: int = Field(ge=1, le=50)
    target_reps: int = Field(ge=0, le=999)
    target_weight: float = Field(default=0, ge=0, le=10000)
    target_duration_seconds: int | None = Field(default=None, ge=1, le=86400)
    order: int = Field(default=0, ge=0, le=1000)


class TemplateDay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day_index: int = Field(ge=0, le=6)
    exercises: list[TemplateItem] = Field(default_factory=list, max_length=100)


class PutTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: list[TemplateDay] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def validate_identity(self):
        if {day.day_index for day in self.days} != set(range(7)):
            raise ValueError("days must contain each day_index from 0 through 6 exactly once")
        item_ids = [item.item_id for day in self.days for item in day.exercises]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("item_id must be unique across the template")
        return self


class CreateSet(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    request_id: Identifier
    weight: float | None = Field(default=None, ge=0, le=10000)
    reps: int | None = Field(default=None, ge=0, le=9999)
    rpe: float | None = Field(default=None, ge=1, le=10)
    duration_seconds: int | None = Field(default=None, ge=1, le=86400)
    remark: Annotated[str, StringConstraints(max_length=500)] | None = None


class PatchSet(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    weight: float | None = Field(default=None, ge=0, le=10000)
    reps: int | None = Field(default=None, ge=0, le=9999)
    rpe: float | None = Field(default=None, ge=1, le=10)
    duration_seconds: int | None = Field(default=None, ge=1, le=86400)
    remark: Annotated[str, StringConstraints(max_length=500)] | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("at least one set field is required")
        return self


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _current_week() -> tuple[str, date, date]:
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    start = today - timedelta(days=today.weekday())
    iso_year, iso_week, _ = start.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}", start, start + timedelta(days=6)


def _canonical_days(body: PutTemplate) -> list[dict]:
    data = body.model_dump(mode="json")
    return sorted(data["days"], key=lambda day: day["day_index"])


def _public_template(row):
    result = {key: row[key] for key in (
        "id", "version", "days", "created_at", "updated_at"
    )}
    result["days"] = _public_days(result["days"])
    return jsonable_encoder(result)


def _public_days(days: list[dict]) -> list[dict]:
    """Fill nullable duration keys omitted by pre-duration JSON snapshots."""
    result = deepcopy(days)
    for day in result:
        for item in day["exercises"]:
            item.setdefault("target_duration_seconds", None)
            for detail in item.get("set_details", []):
                detail.setdefault("duration_seconds", None)
    return result


def _public_set_detail(detail: dict) -> dict:
    result = deepcopy(detail)
    result.setdefault("duration_seconds", None)
    return jsonable_encoder(result)


def _public_week(row):
    result = {key: row[key] for key in (
        "id", "week_id", "week_start", "week_end", "template_version",
        "snapshot_at", "synced_at", "days", "created_at", "updated_at",
    )}
    result["days"] = _public_days(result["days"])
    return jsonable_encoder(result)


def _template(cursor, user_id: UUID, *, lock: bool = False, required: bool = True):
    query = "SELECT * FROM training_templates WHERE user_id = %s"
    if lock:
        query += " FOR UPDATE"
    cursor.execute(query, (user_id,))
    row = cursor.fetchone()
    if row is None and required:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Training template not found")
    return row


def _week(cursor, user_id: UUID, week_id: str, *, lock: bool = False):
    query = "SELECT * FROM training_weeks WHERE week_id = %s AND user_id = %s"
    if lock:
        query += " FOR UPDATE"
    cursor.execute(query, (week_id, user_id))
    row = cursor.fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Training week not found")
    return row


def _snapshot_days(template_days: list[dict], start: date) -> list[dict]:
    days = []
    for source_day in sorted(template_days, key=lambda value: value["day_index"]):
        day = deepcopy(source_day)
        day["date"] = (start + timedelta(days=day["day_index"])).isoformat()
        for item in day["exercises"]:
            item["set_details"] = []
            item["completed_sets"] = 0
            item["removed_from_template"] = False
        days.append(day)
    return days


def _empty_days(start: date) -> list[dict]:
    return [
        {
            "day_index": day_index,
            "date": (start + timedelta(days=day_index)).isoformat(),
            "exercises": [],
        }
        for day_index in range(7)
    ]


def _create_or_get_current(cursor, user_id: UUID):
    week_id, start, end = _current_week()
    template = _template(cursor, user_id, lock=True, required=False)
    cursor.execute(
        "SELECT * FROM training_weeks WHERE user_id = %s AND week_id = %s FOR UPDATE",
        (user_id, week_id),
    )
    row = cursor.fetchone()
    if row is not None:
        return row, False
    now = _now()
    cursor.execute(
        """INSERT INTO training_weeks
           (user_id, week_id, week_start, week_end, template_version,
            snapshot_at, days, created_at, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (user_id, week_id) DO NOTHING RETURNING *""",
        (user_id, week_id, start, end, template["version"] if template else None, now,
         Jsonb(_snapshot_days(template["days"], start) if template else _empty_days(start)),
         now, now),
    )
    row = cursor.fetchone()
    if row is None:
        cursor.execute(
            "SELECT * FROM training_weeks WHERE user_id = %s AND week_id = %s FOR UPDATE",
            (user_id, week_id),
        )
        row = cursor.fetchone()
        return row, False
    return row, True


def _find_item(days: list[dict], item_id: str):
    for day in days:
        for item in day["exercises"]:
            if item["item_id"] == item_id:
                return item
    return None


def _all_sets(days: list[dict]):
    for day in days:
        for item in day["exercises"]:
            for set_detail in item.get("set_details", []):
                yield item, set_detail


@router.get("/template")
def get_template(user_id: User):
    with connection() as conn, conn.cursor() as cursor:
        row = _template(cursor, user_id, required=False)
        return {"template": _public_template(row) if row else None}


@router.put("/template")
def put_template(body: PutTemplate, user_id: User):
    days = _canonical_days(body)
    now = _now()
    with connection() as conn, conn.cursor() as cursor:
        # The unique user row plus UPSERT makes first-write races version correctly.
        cursor.execute(
            """INSERT INTO training_templates (user_id, version, days, created_at, updated_at)
               VALUES (%s, 1, %s, %s, %s)
               ON CONFLICT (user_id) DO UPDATE
               SET days = EXCLUDED.days,
                   version = training_templates.version + 1,
                   updated_at = EXCLUDED.updated_at
               RETURNING *""",
            (user_id, Jsonb(days), now, now),
        )
        return _public_template(cursor.fetchone())


@router.get("/weeks")
def list_weeks(
    user_id: User,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """SELECT * FROM training_weeks WHERE user_id = %s
               ORDER BY week_start DESC, id DESC LIMIT %s OFFSET %s""",
            (user_id, limit, offset),
        )
        weeks = [_public_week(row) for row in cursor.fetchall()]
        cursor.execute("SELECT count(*) AS total FROM training_weeks WHERE user_id = %s", (user_id,))
        return {"weeks": weeks, "total": cursor.fetchone()["total"]}


@router.get("/weeks/current")
def get_current_week(user_id: User):
    with connection() as conn, conn.cursor() as cursor:
        row, created = _create_or_get_current(cursor, user_id)
        return {"week": _public_week(row), "created": created}


@router.get("/weeks/{week_id}")
def get_week(week_id: WeekId, user_id: User):
    with connection() as conn, conn.cursor() as cursor:
        return _public_week(_week(cursor, user_id, week_id))


@router.post("/weeks/current/sync")
def sync_current_week(user_id: User):
    with connection() as conn, conn.cursor() as cursor:
        week, created = _create_or_get_current(cursor, user_id)
        template = _template(cursor, user_id, lock=True, required=False)
        if created or template is None:
            return {"week": _public_week(week), "created": created, "synced": False}

        old_by_id = {
            item["item_id"]: deepcopy(item)
            for day in week["days"] for item in day["exercises"]
        }
        merged = _snapshot_days(template["days"], week["week_start"])
        current_ids = set()
        for day in merged:
            for item in day["exercises"]:
                current_ids.add(item["item_id"])
                old = old_by_id.get(item["item_id"])
                if old is not None:
                    item["set_details"] = old.get("set_details", [])
                    item["completed_sets"] = len(item["set_details"])

        # Removed empty items disappear. Removed checked-in items remain as historical facts.
        for old_day in week["days"]:
            target_day = merged[old_day["day_index"]]
            for old in old_day["exercises"]:
                if old["item_id"] not in current_ids and old.get("set_details"):
                    retained = deepcopy(old)
                    retained["completed_sets"] = len(retained["set_details"])
                    retained["removed_from_template"] = True
                    target_day["exercises"].append(retained)

        now = _now()
        cursor.execute(
            """UPDATE training_weeks SET days = %s, template_version = %s,
               synced_at = %s, updated_at = %s WHERE id = %s AND user_id = %s
               RETURNING *""",
            (Jsonb(merged), template["version"], now, now, week["id"], user_id),
        )
        return {"week": _public_week(cursor.fetchone()), "created": False, "synced": True}


@router.post("/weeks/{week_id}/items/{item_id}/sets", status_code=201)
def create_set(week_id: WeekId, item_id: str, body: CreateSet, user_id: User):
    with connection() as conn, conn.cursor() as cursor:
        week = _week(cursor, user_id, week_id, lock=True)
        days = deepcopy(week["days"])
        item = _find_item(days, item_id)
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Training item not found")

        for owner, detail in _all_sets(days):
            if detail["request_id"] == body.request_id:
                if owner["item_id"] != item_id:
                    raise HTTPException(status.HTTP_409_CONFLICT, "request_id already belongs to another item")
                return {
                    "duplicate": True,
                    "completed_sets": len(item.get("set_details", [])),
                    "target_sets": item["target_sets"],
                    "set": _public_set_detail(detail),
                }

        set_details = item.setdefault("set_details", [])
        if len(set_details) >= item["target_sets"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Target sets already completed")
        detail = body.model_dump()
        detail["set_index"] = len(set_details) + 1
        detail["completed_at"] = _now().isoformat().replace("+00:00", "Z")
        set_details.append(detail)
        item["completed_sets"] = len(set_details)
        now = _now()
        cursor.execute(
            """UPDATE training_weeks SET days = %s, updated_at = %s
               WHERE id = %s AND user_id = %s RETURNING *""",
            (Jsonb(days), now, week["id"], user_id),
        )
        cursor.fetchone()
        return {
            "duplicate": False,
            "completed_sets": len(set_details),
            "target_sets": item["target_sets"],
            "set": _public_set_detail(detail),
        }


@router.patch("/weeks/{week_id}/items/{item_id}/sets/{request_id}")
def patch_set(
    week_id: WeekId, item_id: str, request_id: str, body: PatchSet, user_id: User
):
    with connection() as conn, conn.cursor() as cursor:
        week = _week(cursor, user_id, week_id, lock=True)
        days = deepcopy(week["days"])
        item = _find_item(days, item_id)
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Training item not found")
        detail = next(
            (value for value in item.get("set_details", []) if value["request_id"] == request_id),
            None,
        )
        if detail is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Training set not found")
        detail.update(body.model_dump(exclude_unset=True))
        item["completed_sets"] = len(item.get("set_details", []))
        now = _now()
        cursor.execute(
            """UPDATE training_weeks SET days = %s, updated_at = %s
               WHERE id = %s AND user_id = %s RETURNING *""",
            (Jsonb(days), now, week["id"], user_id),
        )
        cursor.fetchone()
        return {
            "completed_sets": item["completed_sets"],
            "set": _public_set_detail(detail),
        }
