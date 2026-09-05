import secrets
import string
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from psycopg import IntegrityError

from app.auth import get_current_user_id
from app.db import connection


router = APIRouter(prefix="/pairs", tags=["pairs"])
_INVITE_ALPHABET = string.ascii_uppercase + string.digits


class PairMemberResponse(BaseModel):
    user_id: UUID
    display_name: str | None = None
    avatar_url: str | None = None


class PairResponse(BaseModel):
    pair_id: UUID
    invite_code: str
    members: list[PairMemberResponse]
    created_at: datetime


class JoinPairRequest(BaseModel):
    invite_code: str = Field(min_length=1, max_length=64)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _new_invite_code() -> str:
    return "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(8))


def _pair_response(cursor, pair_id: UUID) -> PairResponse:
    cursor.execute(
        """
        SELECT p.id AS pair_id, p.invite_code, p.created_at, pm.user_id
        FROM pairs AS p
        JOIN pair_members AS pm ON pm.pair_id = p.id
        WHERE p.id = %s
        ORDER BY pm.joined_at, pm.user_id
        """,
        (pair_id,),
    )
    rows = cursor.fetchall()
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pair not found",
        )
    first = rows[0]
    return PairResponse(
        pair_id=first["pair_id"],
        invite_code=first["invite_code"],
        created_at=first["created_at"],
        members=[PairMemberResponse(user_id=row["user_id"]) for row in rows],
    )


def _current_pair_id(cursor, user_id: UUID) -> UUID | None:
    cursor.execute(
        "SELECT pair_id FROM pair_members WHERE user_id = %s",
        (user_id,),
    )
    row = cursor.fetchone()
    return row["pair_id"] if row else None


@router.get("/me", response_model=PairResponse)
def get_current_pair(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> PairResponse:
    with connection() as conn:
        with conn.cursor() as cursor:
            pair_id = _current_pair_id(cursor, user_id)
            if pair_id is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Current pair not found",
                )
            return _pair_response(cursor, pair_id)


@router.post("", response_model=PairResponse, status_code=status.HTTP_201_CREATED)
def create_pair(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> PairResponse:
    with connection() as conn:
        with conn.cursor() as cursor:
            if _current_pair_id(cursor, user_id) is not None:
                raise _conflict("User is already paired")

            pair_id = None
            for _ in range(3):
                cursor.execute(
                    """
                    INSERT INTO pairs (invite_code)
                    VALUES (%s)
                    ON CONFLICT (invite_code) DO NOTHING
                    RETURNING id
                    """,
                    (_new_invite_code(),),
                )
                row = cursor.fetchone()
                if row is not None:
                    pair_id = row["id"]
                    break
            if pair_id is None:
                raise _conflict("Invite code conflict")

            try:
                cursor.execute(
                    "INSERT INTO pair_members (pair_id, user_id) VALUES (%s, %s)",
                    (pair_id, user_id),
                )
            except IntegrityError:
                raise _conflict("User is already paired") from None
            return _pair_response(cursor, pair_id)


@router.post("/join", response_model=PairResponse)
def join_pair(
    body: JoinPairRequest,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> PairResponse:
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM pairs WHERE invite_code = %s FOR UPDATE",
                (body.invite_code,),
            )
            pair = cursor.fetchone()
            if pair is None:
                raise _conflict("Invite code conflict")
            pair_id = pair["id"]

            current_pair_id = _current_pair_id(cursor, user_id)
            if current_pair_id is not None:
                raise _conflict(
                    "User is already in this pair"
                    if current_pair_id == pair_id
                    else "User is already paired"
                )

            cursor.execute(
                "SELECT count(*) AS member_count FROM pair_members WHERE pair_id = %s",
                (pair_id,),
            )
            if cursor.fetchone()["member_count"] >= 2:
                raise _conflict("Pair is full")

            try:
                cursor.execute(
                    "INSERT INTO pair_members (pair_id, user_id) VALUES (%s, %s)",
                    (pair_id, user_id),
                )
            except IntegrityError:
                raise _conflict("User is already paired") from None
            return _pair_response(cursor, pair_id)