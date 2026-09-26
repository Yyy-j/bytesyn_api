import secrets
import string
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from psycopg import IntegrityError

from app.auth import get_current_user_id
from app.db import connection


router = APIRouter(prefix="/pairs", tags=["pairs"])
_INVITE_ALPHABET = string.ascii_uppercase + string.digits


class PairMemberResponse(BaseModel):
    user_id: UUID
    display_name: str | None = None
    character: Literal['boy', 'girl']


class PairResponse(BaseModel):
    pair_id: UUID
    invite_code: str
    members: list[PairMemberResponse]
    created_at: datetime
    connected_at: datetime | None
    ended_at: datetime | None


class JoinPairRequest(BaseModel):
    invite_code: str = Field(min_length=1, max_length=64)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _new_invite_code() -> str:
    return "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(8))


def _pair_response(cursor, pair_id: UUID) -> PairResponse:
    cursor.execute(
        """
        SELECT p.id AS pair_id, p.invite_code, p.created_at,
               p.connected_at, p.ended_at, pm.user_id,
               u.display_name, u.character
        FROM pairs AS p
        JOIN pair_members AS pm ON pm.pair_id = p.id
        JOIN users AS u ON u.id = pm.user_id
        WHERE p.id = %s AND pm.left_at IS NULL
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
        connected_at=first["connected_at"],
        ended_at=first["ended_at"],
        members=[
            PairMemberResponse(
                user_id=row["user_id"],
                display_name=row["display_name"],
                character=row["character"] or "boy",
            )
            for row in rows
        ],
    )


def _current_pair_id(cursor, user_id: UUID) -> UUID | None:
    cursor.execute(
        """SELECT pm.pair_id FROM pair_members AS pm
        JOIN pairs AS p ON p.id = pm.pair_id
        WHERE pm.user_id = %s AND pm.left_at IS NULL AND p.ended_at IS NULL""",
        (user_id,),
    )
    row = cursor.fetchone()
    return row["pair_id"] if row else None


def _current_pair_state(cursor, user_id: UUID, *, lock: bool = False):
    lock_clause = " FOR UPDATE OF p" if lock else ""
    cursor.execute(
        """SELECT p.id, p.connected_at, p.ended_at
        FROM pairs AS p
        JOIN pair_members AS pm ON pm.pair_id = p.id
        WHERE pm.user_id = %s
          AND pm.left_at IS NULL
          AND p.ended_at IS NULL""" + lock_clause,
        (user_id,),
    )
    pair = cursor.fetchone()
    if pair is None:
        return None, []
    cursor.execute(
        """SELECT user_id FROM pair_members
        WHERE pair_id = %s AND left_at IS NULL ORDER BY user_id""",
        (pair["id"],),
    )
    members = [row["user_id"] for row in cursor.fetchall()]
    connected = (
        len(members) == 2
        and pair["connected_at"] is not None
        and pair["ended_at"] is None
    )
    return (pair["id"] if connected else None), members


def _active_pair(cursor, user_id: UUID, *, lock: bool = False):
    lock_clause = " FOR UPDATE OF p" if lock else ""
    cursor.execute(
        """SELECT p.id, p.connected_at, p.ended_at
        FROM pairs AS p
        JOIN pair_members AS pm ON pm.pair_id = p.id
        WHERE pm.user_id = %s
          AND pm.left_at IS NULL
          AND p.ended_at IS NULL""" + lock_clause,
        (user_id,),
    )
    return cursor.fetchone()


def _active_members(cursor, pair_id: UUID) -> list[UUID]:
    cursor.execute(
        """SELECT user_id FROM pair_members
        WHERE pair_id = %s AND left_at IS NULL ORDER BY user_id""",
        (pair_id,),
    )
    return [row["user_id"] for row in cursor.fetchall()]


def _replace_invite_code(cursor, pair_id: UUID) -> None:
    for _ in range(3):
        cursor.execute("SAVEPOINT invite_code_retry")
        try:
            cursor.execute(
                "UPDATE pairs SET invite_code = %s WHERE id = %s",
                (_new_invite_code(), pair_id),
            )
            cursor.execute("RELEASE SAVEPOINT invite_code_retry")
            return
        except IntegrityError:
            cursor.execute("ROLLBACK TO SAVEPOINT invite_code_retry")
            cursor.execute("RELEASE SAVEPOINT invite_code_retry")
    raise _conflict("Invite code conflict")


def _end_pair(cursor, pair_id: UUID) -> None:
    cursor.execute("SELECT now() AS stamp")
    stamp = cursor.fetchone()["stamp"]
    cursor.execute(
        "UPDATE pairs SET ended_at = %s WHERE id = %s AND ended_at IS NULL",
        (stamp, pair_id),
    )
    cursor.execute(
        """UPDATE pair_members SET left_at = %s
        WHERE pair_id = %s AND left_at IS NULL""",
        (stamp, pair_id),
    )


@router.get("/me", response_model=PairResponse)
def get_current_pair(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> PairResponse:
    with connection() as conn:
        with conn.cursor() as cursor:
            pair = _active_pair(cursor, user_id)
            if pair is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Current pair not found",
                )
            return _pair_response(cursor, pair["id"])


@router.post("", response_model=PairResponse, status_code=status.HTTP_201_CREATED)
def create_pair(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> PairResponse:
    with connection() as conn:
        with conn.cursor() as cursor:
            if _active_pair(cursor, user_id) is not None:
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
                """SELECT id, connected_at, ended_at
                FROM pairs WHERE invite_code = %s FOR UPDATE""",
                (body.invite_code,),
            )
            pair = cursor.fetchone()
            if pair is None:
                raise _conflict("Invite code conflict")
            pair_id = pair["id"]

            current_pair = _active_pair(cursor, user_id)
            if current_pair is not None:
                raise _conflict(
                    "User is already in this pair"
                    if current_pair["id"] == pair_id
                    else "User is already paired"
                )

            if pair["ended_at"] is not None or pair["connected_at"] is not None:
                raise _conflict("Pair is not available to join")

            cursor.execute(
                """SELECT count(*) AS member_count FROM pair_members
                WHERE pair_id = %s AND left_at IS NULL""",
                (pair_id,),
            )
            if cursor.fetchone()["member_count"] != 1:
                raise _conflict("Pair is full")

            try:
                cursor.execute(
                    "INSERT INTO pair_members (pair_id, user_id) VALUES (%s, %s)",
                    (pair_id, user_id),
                )
            except IntegrityError:
                raise _conflict("User is already paired") from None
            cursor.execute(
                "UPDATE pairs SET connected_at = now() WHERE id = %s",
                (pair_id,),
            )
            return _pair_response(cursor, pair_id)


@router.post("/invite-code/regenerate", response_model=PairResponse)
def regenerate_invite_code(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> PairResponse:
    with connection() as conn, conn.cursor() as cursor:
        pair = _active_pair(cursor, user_id, lock=True)
        if pair is None:
            raise _conflict("Pending pair not found")
        members = _active_members(cursor, pair["id"])
        if (pair["connected_at"] is not None or pair["ended_at"] is not None
                or members != [user_id]):
            raise _conflict("Only a pending pair can regenerate its invite code")
        _replace_invite_code(cursor, pair["id"])
        return _pair_response(cursor, pair["id"])


@router.post("/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_pair(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> Response:
    with connection() as conn, conn.cursor() as cursor:
        pair = _active_pair(cursor, user_id, lock=True)
        if pair is None:
            raise _conflict("Pending pair not found")
        members = _active_members(cursor, pair["id"])
        if pair["connected_at"] is not None or members != [user_id]:
            raise _conflict("Only a pending pair can be cancelled")
        _end_pair(cursor, pair["id"])
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/end", status_code=status.HTTP_204_NO_CONTENT)
def end_pair(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> Response:
    with connection() as conn, conn.cursor() as cursor:
        pair = _active_pair(cursor, user_id, lock=True)
        if pair is None:
            raise _conflict("Connected pair not found")
        members = _active_members(cursor, pair["id"])
        if pair["connected_at"] is None or len(members) != 2:
            raise _conflict("Only a connected pair can be ended")
        _end_pair(cursor, pair["id"])
        return Response(status_code=status.HTTP_204_NO_CONTENT)
